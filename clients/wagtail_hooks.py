"""
Wagtail hooks for the clients app.

Provides:
- A searchable, filterable Client snippet in the Wagtail admin sidebar
- A Deposit snippet for tracking booking deposit payments
- One-click "Send Deposit Request" / "Send Deposit Confirmation" email buttons
- "Send Email" menu item for composing emails to clients
- "Import CSV" / "Export CSV" for bulk client management
- Autocomplete suggestions endpoint for filter fields
"""

from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Client, Deposit
from .views import (
    approve_deposit_view,
    autocomplete_view,
    compose_email_view,
    csv_export_view,
    csv_import_view,
    deposit_export_view,
    send_deposit_request_view,
    send_deposit_confirmation_view,
)


# ──────────────────────────────────────────────────────────
# Snippet viewset — Client list in the admin
# ──────────────────────────────────────────────────────────

class ClientViewSet(SnippetViewSet):
    model = Client
    icon = "user"
    menu_label = "Clients"
    menu_name = "clients"
    menu_order = 200
    add_to_admin_menu = True
    list_display = [
        "name", "phone", "email", "clinic_location",
        "previous_visit_reason", "last_appointment_date", "created_at",
    ]
    list_filter = [
        "clinic_location",
        "previous_visit_reason",
        "last_appointment_date",
    ]
    search_fields = ["clinic_location"]
    ordering = ["-created_at"]


register_snippet(Client, viewset=ClientViewSet)


# ──────────────────────────────────────────────────────────
# Snippet viewset — Deposit tracking in the admin
# ──────────────────────────────────────────────────────────

class DepositViewSet(SnippetViewSet):
    model = Deposit
    icon = "doc-full-inverse"
    menu_label = "Deposits"
    menu_name = "deposits"
    menu_order = 199
    add_to_admin_menu = True
    list_display = [
        "__str__", "status_badge", "email_status_display",
        "payment_method", "appointment_date", "created_at",
    ]
    list_filter = [
        "status",
        "payment_method",
        "appointment_date",
        "deposit_request_sent",
    ]
    ordering = ["-created_at"]


register_snippet(Deposit, viewset=DepositViewSet)


# ──────────────────────────────────────────────────────────
# Custom admin URLs
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_urls")
def register_client_admin_urls():
    return [
        path("clients/email/", compose_email_view, name="clients_compose_email"),
        path("clients/import-csv/", csv_import_view, name="clients_csv_import"),
        path("clients/export-csv/", csv_export_view, name="clients_csv_export"),
        path("clients/autocomplete/", autocomplete_view, name="clients_autocomplete"),
        path("deposits/export-csv/", deposit_export_view, name="deposits_csv_export"),
        path("deposits/<int:deposit_id>/approve/", approve_deposit_view, name="deposit_approve"),
        path("deposits/<int:deposit_id>/send-request/", send_deposit_request_view, name="deposit_send_request"),
        path("deposits/<int:deposit_id>/send-confirmation/", send_deposit_confirmation_view, name="deposit_send_confirmation"),
    ]


# ──────────────────────────────────────────────────────────
# Sidebar menu — grouped submenus
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_menu_item")
def register_tools_menu():
    return SubmenuMenuItem(
        "Tools",
        Menu(
            register_hook_name="",
            construct_hook_name="",
            items=[
                MenuItem("Import Clients CSV", reverse("clients_csv_import"), icon_name="upload", order=100),
                MenuItem("Export Clients CSV", reverse("clients_csv_export"), icon_name="download", order=200),
                MenuItem("Export Deposits CSV", reverse("deposits_csv_export"), icon_name="download", order=300),
            ],
        ),
        icon_name="cog",
        order=300,
    )


@hooks.register("register_admin_menu_item")
def register_contact_menu():
    return SubmenuMenuItem(
        "Contact",
        Menu(
            register_hook_name="",
            construct_hook_name="",
            items=[
                MenuItem("Send Email", reverse("clients_compose_email"), icon_name="mail", order=100),
                MenuItem("Send Newsletter", reverse("newsletter_compose"), icon_name="mail", order=200),
                MenuItem("Contact Submissions", reverse("wagtailsnippets_contact_contactsubmission:list"), icon_name="form", order=300),
                MenuItem("Subscribers", reverse("wagtailsnippets_newsletter_newslettersubscriber:list"), icon_name="group", order=400),
            ],
        ),
        icon_name="mail",
        order=250,
    )
