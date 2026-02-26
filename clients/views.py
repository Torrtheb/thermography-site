"""
Custom Wagtail admin views for the clients app.
"""

from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib import messages
from django.views import View

from wagtail.admin.auth import require_admin_access

from .forms import ComposeEmailForm
from .models import Client
from .email import send_custom_email


class ComposeEmailView(View):
    """
    Wagtail admin view for composing and sending emails to clients.

    Accessible from the admin sidebar under "Send Email",
    or via ?client_id=N to pre-select a client.
    """

    template_name = "clients/admin/compose_email.html"

    # Fields that can be sorted at the DB level (not encrypted)
    DB_SORT_FIELDS = {
        "clinic_location", "-clinic_location",
        "previous_visit_reason", "-previous_visit_reason",
        "last_appointment_date", "-last_appointment_date",
    }

    # Fields that require Python-level sorting (encrypted columns)
    PYTHON_SORT_FIELDS = {
        "name": lambda c: (c.name or "").lower(),
        "-name": lambda c: (c.name or "").lower(),
    }

    ALL_SORT_KEYS = DB_SORT_FIELDS | set(PYTHON_SORT_FIELDS.keys())

    def _get_clients(self, request):
        sort = request.GET.get("sort", "-last_appointment_date")
        if sort not in self.ALL_SORT_KEYS:
            sort = "-last_appointment_date"

        qs = Client.objects.all()

        if sort in self.DB_SORT_FIELDS:
            return qs.order_by(sort), sort

        # Python-level sort for encrypted fields
        key_func = self.PYTHON_SORT_FIELDS[sort]
        reverse = sort.startswith("-")
        clients = sorted(qs, key=key_func, reverse=reverse)
        return clients, sort

    def _get_context(self, request, form, selected_ids=None):
        clients, current_sort = self._get_clients(request)
        return {
            "form": form,
            "page_title": "Send Email to Clients",
            "clients": clients,
            "selected_ids": selected_ids or set(),
            "current_sort": current_sort,
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
                    first_name = client.name.split()[0] if client.name else "there"
                    personalised_body = f"Hi {first_name},\n\n{body}\n\n{sign_off}"
                    send_custom_email(client, subject, personalised_body)
                    sent += 1
                except Exception as e:
                    failed.append(f"{client.name}: {e}")

            if sent:
                messages.success(request, f"Email sent successfully to {sent} client(s).")
            if failed:
                messages.error(request, f"Failed to send to: {'; '.join(failed)}")

            return redirect(reverse("clients_compose_email"))

        # On validation error, preserve the selected checkboxes
        selected_ids = set()
        try:
            selected_ids = {int(v) for v in request.POST.getlist("recipients")}
        except (ValueError, TypeError):
            pass
        return render(request, self.template_name, self._get_context(request, form, selected_ids))


compose_email_view = require_admin_access(ComposeEmailView.as_view())


# NOTE: SendReportView was removed — private client reports are no longer
# stored on or sent from this website. Reports are delivered via a separate
# secure channel outside the application.
