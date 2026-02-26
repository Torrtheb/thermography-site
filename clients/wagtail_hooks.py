"""
Wagtail hooks for the clients app.

Provides:
- A searchable, filterable Client snippet in the Wagtail admin sidebar
- A "Send Email" menu item for composing emails to clients

NOTE: ClientReport management has been intentionally removed from the admin
interface. Reports contain personal health details that should not be
accessible through the web UI.
"""

from django.urls import path, reverse

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Client
from .views import compose_email_view


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
    list_display = ["name", "phone", "email", "clinic_location", "previous_visit_reason", "last_appointment_date", "created_at"]
    list_filter = ["clinic_location", "previous_visit_reason"]
    search_fields = ["clinic_location"]
    ordering = ["-created_at"]


register_snippet(Client, viewset=ClientViewSet)


# NOTE: ClientReport model still exists in the database but is intentionally
# excluded from the Wagtail admin interface. Reports contain personal health
# details that should not be accessible through the web UI.


# ──────────────────────────────────────────────────────────
# Custom admin URLs
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_urls")
def register_email_url():
    return [
        path("clients/email/", compose_email_view, name="clients_compose_email"),
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
        order=201,  # right after the Clients item (200)
    )
