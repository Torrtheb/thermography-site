"""
Custom Wagtail admin views for the clients app.

Provides:
  - ComposeEmailView: compose and send emails to filtered clients
  - CSVImportView: upload a CSV of client records
  - csv_export_view: download all clients as CSV
  - autocomplete_view: JSON suggestions for filter fields

Security: Avoid putting client names or emails in flash messages or logs
in production; failure messages use client ids only.
"""

import csv
import io
import json
import logging
from datetime import date

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib import messages
from django.views import View
from django.views.decorators.http import require_POST

from wagtail.admin.auth import require_admin_access

from .forms import ClientFilterForm, ComposeEmailForm, CSVImportForm
from .models import Client, Deposit, VISIT_REASON_CHOICES
from .email import send_custom_email, send_deposit_request

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


# ──────────────────────────────────────────────────────────
# Autocomplete suggestions for filter fields
# ──────────────────────────────────────────────────────────

def _autocomplete(request):
    """Return JSON suggestions for a given field and prefix.

    Query params:
      field  – one of: clinic_location, name, email, phone
      q      – the prefix to match (case-insensitive)
    """
    field = request.GET.get("field", "")
    q = (request.GET.get("q") or "").strip().lower()
    if not q or len(q) < 1:
        return JsonResponse([], safe=False)

    MAX_SUGGESTIONS = 10

    if field == "clinic_location":
        values = (
            Client.objects.filter(clinic_location__icontains=q)
            .values_list("clinic_location", flat=True)
            .distinct()[:MAX_SUGGESTIONS]
        )
        return JsonResponse(list(values), safe=False)

    if field in ("name", "email", "phone"):
        seen = set()
        results = []
        for client in Client.objects.all().only(
            "pk", "name", "email", "email_hash", "phone",
        ).iterator():
            val = getattr(client, field, "") or ""
            if not val:
                continue
            low = val.lower()
            if q in low and low not in seen:
                seen.add(low)
                results.append(val)
                if len(results) >= MAX_SUGGESTIONS:
                    break
        return JsonResponse(results, safe=False)

    return JsonResponse([], safe=False)


autocomplete_view = require_admin_access(_autocomplete)


# ──────────────────────────────────────────────────────────
# Deposit CSV Export
# ──────────────────────────────────────────────────────────

def _deposit_export(request):
    """Download all deposit records as a CSV file."""
    deposits = Deposit.objects.select_related("client").order_by("-created_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="deposits_export_{date.today().isoformat()}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        "client_name", "client_email", "amount", "appointment_date",
        "status", "payment_method", "received_date", "reference",
        "notes", "created_at",
    ])
    for d in deposits:
        writer.writerow([
            d.client.name if d.client_id else "",
            d.client.email if d.client_id else "",
            str(d.amount),
            d.appointment_date.isoformat() if d.appointment_date else "",
            d.get_status_display(),
            d.get_payment_method_display() if d.payment_method else "",
            d.received_date.isoformat() if d.received_date else "",
            d.reference,
            d.notes,
            d.created_at.isoformat() if d.created_at else "",
        ])

    return response


deposit_export_view = require_admin_access(_deposit_export)


# ──────────────────────────────────────────────────────────
# One-click deposit email actions
# ──────────────────────────────────────────────────────────

def _send_deposit_request_action(request, deposit_id):
    """One-click: send deposit request email for a specific deposit."""
    try:
        deposit = Deposit.objects.select_related("client").get(pk=deposit_id)
    except Deposit.DoesNotExist:
        messages.error(request, "Deposit not found.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    client = deposit.client
    if not client.email:
        messages.error(request, f"Client has no email on file — cannot send deposit request.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    date_str = ""
    if deposit.appointment_date:
        date_str = deposit.appointment_date.strftime("%B %d, %Y")

    try:
        send_deposit_request(client, deposit.amount, appointment_date=date_str)
        deposit.deposit_request_sent = True
        deposit.save(update_fields=["deposit_request_sent", "updated_at"])
        messages.success(request, f"Deposit request email sent to {client.name}.")
    except Exception as e:
        logger.exception("Failed to send deposit request for deposit pk=%s", deposit.pk)
        messages.error(request, f"Failed to send email: {e}")

    return redirect(reverse("wagtailsnippets_clients_deposit:list"))


send_deposit_request_view = require_POST(require_admin_access(_send_deposit_request_action))


def _send_deposit_confirmation_action(request, deposit_id):
    """Confirm the Cal.com booking (fallback for deposits manually set to 'received').

    Cal.com's own confirmation email serves as the client notification,
    so no separate email is sent from this site.
    """
    try:
        deposit = Deposit.objects.select_related("client").get(pk=deposit_id)
    except Deposit.DoesNotExist:
        messages.error(request, "Deposit not found.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    client_name = deposit.client.name if deposit.client_id else "Unknown"

    deposit.deposit_confirmed_sent = True
    deposit.save(update_fields=["deposit_confirmed_sent", "updated_at"])

    if deposit.cal_booking_uid:
        from booking.webhooks import confirm_calcom_booking
        try:
            confirmed = confirm_calcom_booking(deposit.cal_booking_uid)
            if confirmed:
                messages.success(request, f"Cal.com booking confirmed for {client_name}.")
            else:
                messages.warning(request, f"Could not auto-confirm in Cal.com for {client_name} — please confirm manually.")
        except Exception:
            logger.exception("Failed to auto-confirm Cal.com booking for deposit pk=%s", deposit.pk)
            messages.warning(request, f"Could not auto-confirm in Cal.com for {client_name} — please confirm manually.")
    else:
        messages.success(request, f"Deposit for {client_name} marked as confirmed.")

    return redirect(reverse("wagtailsnippets_clients_deposit:list"))


send_deposit_confirmation_view = require_POST(require_admin_access(_send_deposit_confirmation_action))


# ──────────────────────────────────────────────────────────
# Approve booking & send deposit request (owner review gate)
# ──────────────────────────────────────────────────────────

def _approve_deposit_action(request, deposit_id):
    """Owner reviews the client, approves, and sends the deposit request email.

    Transitions the deposit from 'awaiting_review' → 'pending' and sends
    the deposit request email in one click.
    """
    try:
        deposit = Deposit.objects.select_related("client").get(pk=deposit_id)
    except Deposit.DoesNotExist:
        messages.error(request, "Deposit not found.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    if deposit.status != "awaiting_review":
        messages.warning(request, "This deposit has already been reviewed.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    client = deposit.client
    if not client.email:
        messages.error(request, "Client has no email on file — cannot send deposit request.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    date_str = ""
    if deposit.appointment_date:
        date_str = deposit.appointment_date.strftime("%B %d, %Y")

    from django.utils import timezone

    try:
        send_deposit_request(client, deposit.amount, appointment_date=date_str)
        deposit.status = "pending"
        deposit.deposit_request_sent = True
        deposit.approved_at = timezone.now()
        deposit.save(update_fields=["status", "deposit_request_sent", "approved_at", "updated_at"])
        messages.success(request, f"Approved! Deposit request email sent to {client.name}.")
    except Exception as e:
        logger.exception("Failed to send deposit request for deposit pk=%s", deposit.pk)
        messages.error(request, f"Failed to send email: {e}")

    return redirect(reverse("wagtailsnippets_clients_deposit:list"))


approve_deposit_view = require_POST(require_admin_access(_approve_deposit_action))


# ──────────────────────────────────────────────────────────
# Mark deposit received + send confirmation + confirm Cal.com
# ──────────────────────────────────────────────────────────

def _mark_received_action(request, deposit_id):
    """One-click: mark deposit as received and confirm the Cal.com booking.

    Transitions the deposit from 'pending' → 'received' and confirms the
    booking in Cal.com (which sends Cal.com's own confirmation email to
    the client). No separate confirmation email is sent from the site to
    avoid duplicate "booking confirmed" emails.
    """
    try:
        deposit = Deposit.objects.select_related("client").get(pk=deposit_id)
    except Deposit.DoesNotExist:
        messages.error(request, "Deposit not found.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    if deposit.status != "pending":
        messages.warning(request, "This deposit is not in 'pending' status.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    from django.utils import timezone

    deposit.status = "received"
    deposit.received_date = timezone.localdate()
    deposit.deposit_confirmed_sent = True
    deposit.save(update_fields=["status", "received_date", "deposit_confirmed_sent", "updated_at"])

    client_name = deposit.client.name if deposit.client_id else "Unknown"

    if deposit.cal_booking_uid:
        from booking.webhooks import confirm_calcom_booking
        try:
            confirmed = confirm_calcom_booking(deposit.cal_booking_uid)
            if confirmed:
                messages.success(request, f"Deposit received! Cal.com booking confirmed for {client_name}.")
            else:
                messages.warning(request, f"Deposit received for {client_name}, but could not auto-confirm in Cal.com — please confirm manually.")
        except Exception:
            logger.exception("Failed to auto-confirm Cal.com booking for deposit pk=%s", deposit.pk)
            messages.warning(request, f"Deposit received for {client_name}, but could not auto-confirm in Cal.com — please confirm manually.")
    else:
        messages.success(request, f"Deposit received for {client_name}.")

    return redirect(reverse("wagtailsnippets_clients_deposit:list"))


mark_received_view = require_POST(require_admin_access(_mark_received_action))


# ──────────────────────────────────────────────────────────
# Reject booking — decline in Cal.com + forfeit deposit
# ──────────────────────────────────────────────────────────

def _reject_deposit_action(request, deposit_id):
    """Owner rejects a booking: forfeit the deposit and decline/cancel in Cal.com.

    Works for deposits in 'awaiting_review' (decline) or 'pending' (cancel).
    """
    try:
        deposit = Deposit.objects.select_related("client").get(pk=deposit_id)
    except Deposit.DoesNotExist:
        messages.error(request, "Deposit not found.")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    if deposit.status not in ("awaiting_review", "pending"):
        messages.warning(request, "This deposit cannot be rejected (already processed).")
        return redirect(reverse("wagtailsnippets_clients_deposit:list"))

    old_status = deposit.status
    deposit.status = "forfeited"
    deposit.notes = (deposit.notes or "") + f"\nRejected by owner from Wagtail (was {old_status})."
    deposit.save(update_fields=["status", "notes", "updated_at"])

    client_name = deposit.client.name if deposit.client_id else "Unknown"

    if deposit.cal_booking_uid:
        from booking.webhooks import decline_calcom_booking, cancel_calcom_booking
        try:
            if old_status == "awaiting_review":
                ok = decline_calcom_booking(deposit.cal_booking_uid, reason="Booking declined by organizer.")
            else:
                ok = cancel_calcom_booking(deposit.cal_booking_uid, reason="Booking cancelled by organizer.")
            if ok:
                messages.success(request, f"Rejected! Booking for {client_name} has been cancelled in Cal.com.")
            else:
                messages.warning(request, f"Deposit forfeited, but could not update Cal.com — please cancel/decline manually.")
        except Exception:
            logger.exception("Failed to decline/cancel Cal.com booking for deposit pk=%s", deposit.pk)
            messages.warning(request, f"Deposit forfeited, but could not update Cal.com — please cancel/decline manually.")
    else:
        messages.success(request, f"Deposit for {client_name} has been forfeited.")

    return redirect(reverse("wagtailsnippets_clients_deposit:list"))


reject_deposit_view = require_POST(require_admin_access(_reject_deposit_action))
