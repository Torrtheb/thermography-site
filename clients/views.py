"""
Custom Wagtail admin views for the clients app.

Provides:
  - ClientSearchView: searchable/filterable client list (works on encrypted fields)
  - ComposeEmailView: compose and send emails to filtered clients
  - CSVImportView: upload a CSV of client records
  - csv_export_view: download all clients as CSV

Security: Avoid putting client names or emails in flash messages or logs
in production; failure messages use client ids only.
"""

import csv
import io
import logging
from datetime import date

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib import messages
from django.views import View

from wagtail.admin.auth import require_admin_access

from .forms import ClientFilterForm, ComposeEmailForm, CSVImportForm
from .models import Client, VISIT_REASON_CHOICES
from .email import send_custom_email

logger = logging.getLogger(__name__)

VALID_VISIT_REASONS = {slug for slug, _ in VISIT_REASON_CHOICES}

CLIENTS_PER_PAGE = 50


def _paginate(request, items, per_page=CLIENTS_PER_PAGE):
    """Return a Page object from a list of items."""
    paginator = Paginator(items, per_page)
    page_num = request.GET.get("page", 1)
    try:
        return paginator.page(page_num)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# ──────────────────────────────────────────────────────────
# Shared filtering helper
# ──────────────────────────────────────────────────────────

def _filter_clients(request):
    """Apply filters from GET params and return (queryset_or_list, filter_form, sort_key).

    DB-level filters are applied to the queryset first. Then, because
    encrypted fields (name, email, phone) can't be filtered at the DB level,
    text search is done in Python after decryption.
    """
    filter_form = ClientFilterForm(request.GET)
    filter_form.is_valid()
    cd = filter_form.cleaned_data

    qs = Client.objects.all()

    # DB-level filters (non-encrypted fields)
    if cd.get("clinic_location"):
        qs = qs.filter(clinic_location__icontains=cd["clinic_location"])
    if cd.get("previous_visit_reason"):
        qs = qs.filter(previous_visit_reason=cd["previous_visit_reason"])
    if cd.get("appt_from"):
        qs = qs.filter(last_appointment_date__gte=cd["appt_from"])
    if cd.get("appt_to"):
        qs = qs.filter(last_appointment_date__lte=cd["appt_to"])

    # Sorting
    sort = request.GET.get("sort", "-last_appointment_date")
    DB_SORT_FIELDS = {
        "clinic_location", "-clinic_location",
        "previous_visit_reason", "-previous_visit_reason",
        "last_appointment_date", "-last_appointment_date",
    }
    PYTHON_SORT_FIELDS = {
        "name": lambda c: (c.name or "").lower(),
        "-name": lambda c: (c.name or "").lower(),
    }
    ALL_SORT_KEYS = DB_SORT_FIELDS | set(PYTHON_SORT_FIELDS.keys())

    if sort not in ALL_SORT_KEYS:
        sort = "-last_appointment_date"

    if sort in DB_SORT_FIELDS:
        clients = list(qs.order_by(sort))
    else:
        key_func = PYTHON_SORT_FIELDS[sort]
        clients = sorted(qs, key=key_func, reverse=sort.startswith("-"))

    # Python-level search on encrypted fields
    search_q = (cd.get("search") or "").strip().lower()
    if search_q:
        clients = [
            c for c in clients
            if search_q in (c.name or "").lower()
            or search_q in (c.email or "").lower()
            or search_q in (c.phone or "").lower()
        ]

    return clients, filter_form, sort


# ──────────────────────────────────────────────────────────
# Client Search (works on encrypted fields)
# ──────────────────────────────────────────────────────────

class ClientSearchView(View):
    """
    Searchable, filterable client list that works on encrypted fields.

    Wagtail's built-in snippet search can only query DB-level columns,
    so encrypted name/email/phone are invisible to it. This view decrypts
    in Python and filters client-side, giving the owner full search
    across all fields.
    """

    template_name = "clients/admin/client_search.html"

    def get(self, request):
        clients, filter_form, current_sort = _filter_clients(request)
        page_obj = _paginate(request, clients)
        return render(request, self.template_name, {
            "page_title": "Client Search",
            "clients": page_obj,
            "filter_form": filter_form,
            "current_sort": current_sort,
            "total_count": Client.objects.count(),
            "filtered_count": len(clients),
        })


client_search_view = require_admin_access(ClientSearchView.as_view())


# ──────────────────────────────────────────────────────────
# Compose & Send Email
# ──────────────────────────────────────────────────────────

class ComposeEmailView(View):
    """
    Wagtail admin view for composing and sending emails to clients.

    Accessible from the admin sidebar under "Send Email",
    or via ?client_id=N to pre-select a client.
    """

    template_name = "clients/admin/compose_email.html"

    def _get_context(self, request, form, selected_ids=None):
        clients, filter_form, current_sort = _filter_clients(request)
        page_obj = _paginate(request, clients)
        return {
            "form": form,
            "page_title": "Send Email to Clients",
            "clients": page_obj,
            "selected_ids": selected_ids or set(),
            "current_sort": current_sort,
            "filter_form": filter_form,
            "filtered_count": len(clients),
        }

    def get(self, request):
        initial = {}
        selected_ids = set()
        client_id = request.GET.get("client_id")
        if client_id:
            try:
                cid = int(client_id)
                if Client.objects.filter(pk=cid).exists():
                    initial["recipients"] = Client.objects.filter(pk=cid)
                    selected_ids = {cid}
            except (ValueError, TypeError):
                pass

        form = ComposeEmailForm(initial=initial)
        return render(request, self.template_name, self._get_context(request, form, selected_ids))

    def post(self, request):
        form = ComposeEmailForm(request.POST)
        if form.is_valid():
            recipients = form.cleaned_data["recipients"]
            subject = form.cleaned_data["subject"]
            body = form.cleaned_data["body"]

            sent = 0
            failed = []
            sign_off = form.cleaned_data["sign_off"]

            for client in recipients:
                try:
                    first_name = (client.name.split()[0] if client.name and client.name.strip() else "there")
                    personalised_body = f"Hi {first_name},\n\n{body}\n\n{sign_off}"
                    send_custom_email(client, subject, personalised_body)
                    sent += 1
                except Exception as e:
                    failed.append(client.pk)
                    logger.warning(
                        "Send email failed for client_id=%s: %s",
                        client.pk,
                        e,
                        exc_info=True,
                    )

            if sent:
                messages.success(request, f"Email sent successfully to {sent} client(s).")
            if failed:
                messages.error(
                    request,
                    f"Failed to send to {len(failed)} client(s) (IDs: {', '.join(str(pk) for pk in failed)}). "
                    "Check server logs for details. You can retry from the Clients list.",
                )

            return redirect(reverse("clients_compose_email"))

        selected_ids = set()
        try:
            selected_ids = {int(v) for v in request.POST.getlist("recipients")}
        except (ValueError, TypeError):
            pass
        return render(request, self.template_name, self._get_context(request, form, selected_ids))


compose_email_view = require_admin_access(ComposeEmailView.as_view())


# ──────────────────────────────────────────────────────────
# CSV Export
# ──────────────────────────────────────────────────────────

def _csv_export(request):
    """Download all clients as a CSV file (decrypted)."""
    clients = Client.objects.all().order_by("pk")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="clients_export_{date.today().isoformat()}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        "name", "email", "phone", "clinic_location",
        "previous_visit_reason", "last_appointment_date", "notes",
    ])
    for c in clients:
        writer.writerow([
            c.name,
            c.email,
            c.phone,
            c.clinic_location,
            c.previous_visit_reason,
            c.last_appointment_date.isoformat() if c.last_appointment_date else "",
            c.notes,
        ])

    return response


csv_export_view = require_admin_access(_csv_export)


# ──────────────────────────────────────────────────────────
# CSV Import
# ──────────────────────────────────────────────────────────

EXPECTED_HEADERS = {"name", "email", "phone", "clinic_location",
                    "previous_visit_reason", "last_appointment_date", "notes"}


class CSVImportView(View):
    """Upload a CSV to bulk-create client records."""

    template_name = "clients/admin/csv_import.html"

    def get(self, request):
        return render(request, self.template_name, {
            "form": CSVImportForm(),
            "page_title": "Import Clients from CSV",
        })

    def post(self, request):
        form = CSVImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form": form,
                "page_title": "Import Clients from CSV",
            })

        csv_file = form.cleaned_data["csv_file"]
        try:
            decoded = csv_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "Could not read file. Ensure it is UTF-8 encoded.")
            return render(request, self.template_name, {
                "form": CSVImportForm(),
                "page_title": "Import Clients from CSV",
            })

        reader = csv.DictReader(io.StringIO(decoded))

        if not reader.fieldnames:
            messages.error(request, "CSV file appears empty or has no header row.")
            return render(request, self.template_name, {
                "form": CSVImportForm(),
                "page_title": "Import Clients from CSV",
            })

        normalised_headers = {h.strip().lower() for h in reader.fieldnames}
        if "name" not in normalised_headers:
            messages.error(
                request,
                f"CSV must have a 'name' column. Found: {', '.join(reader.fieldnames)}",
            )
            return render(request, self.template_name, {
                "form": CSVImportForm(),
                "page_title": "Import Clients from CSV",
            })

        created = 0
        skipped = 0
        errors = []

        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}

                name = row.get("name", "").strip()
                if not name:
                    skipped += 1
                    continue

                last_appt = None
                raw_date = row.get("last_appointment_date", "").strip()
                if raw_date:
                    try:
                        last_appt = date.fromisoformat(raw_date)
                    except ValueError:
                        errors.append(f"Row {row_num}: invalid date '{raw_date}' — skipped date field.")

                visit_reason = row.get("previous_visit_reason", "").strip()
                if visit_reason and visit_reason not in VALID_VISIT_REASONS:
                    errors.append(f"Row {row_num}: unknown visit reason '{visit_reason}' — cleared.")
                    visit_reason = ""

                Client.objects.create(
                    name=name,
                    email=row.get("email", "").strip(),
                    phone=row.get("phone", "").strip(),
                    clinic_location=row.get("clinic_location", "").strip(),
                    previous_visit_reason=visit_reason,
                    last_appointment_date=last_appt,
                    notes=row.get("notes", "").strip(),
                )
                created += 1

        msg = f"Imported {created} client(s)."
        if skipped:
            msg += f" Skipped {skipped} row(s) with no name."
        if errors:
            msg += f" {len(errors)} warning(s): " + "; ".join(errors[:5])
            if len(errors) > 5:
                msg += f" … and {len(errors) - 5} more."

        messages.success(request, msg)
        return redirect(reverse("wagtailsnippets_clients_client:list"))


csv_import_view = require_admin_access(CSVImportView.as_view())
