"""
Wagtail hooks for the clients app.

Provides:
- A searchable, filterable Client snippet in the Wagtail admin sidebar
- "Send Email" menu item for composing emails to clients
- "Import CSV" / "Export CSV" for bulk client management
- Autocomplete suggestions endpoint for filter fields
"""

from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Client
from .views import (
    autocomplete_view,
    compose_email_view,
    csv_export_view,
    csv_import_view,
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
# Custom admin URLs
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_urls")
def register_client_admin_urls():
    return [
        path("clients/email/", compose_email_view, name="clients_compose_email"),
        path("clients/import-csv/", csv_import_view, name="clients_csv_import"),
        path("clients/export-csv/", csv_export_view, name="clients_csv_export"),
        path("clients/autocomplete/", autocomplete_view, name="clients_autocomplete"),
    ]


# ──────────────────────────────────────────────────────────
# Sidebar menu items
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_menu_item")
def register_email_menu_item():
    return MenuItem(
        "Send Email",
        reverse("clients_compose_email"),
        icon_name="mail",
        order=201,
    )


@hooks.register("register_admin_menu_item")
def register_import_menu_item():
    return MenuItem(
        "Import Clients CSV",
        reverse("clients_csv_import"),
        icon_name="upload",
        order=202,
    )


@hooks.register("register_admin_menu_item")
def register_export_menu_item():
    return MenuItem(
        "Export Clients CSV",
        reverse("clients_csv_export"),
        icon_name="download",
        order=203,
    )
