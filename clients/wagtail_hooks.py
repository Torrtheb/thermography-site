"""
Wagtail hooks for the clients app.

Provides:
- A searchable, filterable Client snippet in the Wagtail admin sidebar
- A Deposit snippet for tracking booking deposit payments
- One-click "Send Deposit Request" / "Send Deposit Confirmation" email buttons
- "Send Email" menu item for composing emails to clients
- "Import CSV" / "Export CSV" for bulk client management
- Autocomplete suggestions endpoint for filter fields
- Dashboard panel showing deposits that need attention
"""

from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.ui.components import Component
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
    mark_received_view,
    reject_deposit_view,
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
        "client_name_display", "client_email_display", "status_badge",
        "email_status_display", "service_name", "appointment_date", "created_at",
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
        path("deposits/<int:deposit_id>/reject/", reject_deposit_view, name="deposit_reject"),
        path("deposits/<int:deposit_id>/mark-received/", mark_received_view, name="deposit_mark_received"),
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


# ──────────────────────────────────────────────────────────
# Dashboard panel — deposits needing attention
# ──────────────────────────────────────────────────────────

class ActionRequiredPanel(Component):
    name = "action_required"
    template_name = "clients/admin/action_required_panel.html"
    order = 50

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        needs_review = list(
            Deposit.objects.filter(status="awaiting_review")
            .select_related("client")
            .order_by("-created_at")[:20]
        )
        needs_confirmation = list(
            Deposit.objects.filter(status="received", deposit_confirmed_sent=False)
            .select_related("client")
            .order_by("-created_at")[:20]
        )
        context["needs_review"] = needs_review
        context["needs_confirmation"] = needs_confirmation
        context["total_count"] = len(needs_review) + len(needs_confirmation)
        return context


@hooks.register("construct_homepage_panels")
def add_action_required_panel(request, panels):
    panels.insert(0, ActionRequiredPanel())


# ──────────────────────────────────────────────────────────
# Global admin notification banner (all pages)
# ──────────────────────────────────────────────────────────

@hooks.register("insert_global_admin_js")
def deposit_action_csrf_fill():
    """Fill CSRF tokens into deposit action POST forms rendered by Deposit.email_status_display().

    The model method can't access the request, so it renders placeholder tokens.
    This script reads the csrftoken cookie and fills them in client-side.
    """
    from django.utils.html import format_html
    return format_html(
        '<script>'
        '(function(){{'
        '  var c=document.cookie.match(/csrftoken=([^;]+)/);'
        '  if(!c)return;'
        '  document.querySelectorAll(".js-csrf-token-placeholder")'
        '    .forEach(function(el){{el.value=c[1];}});'
        '}})();'
        '</script>'
    )


@hooks.register("insert_global_admin_js")
def deposit_notification_banner():
    from django.utils.html import format_html

    review_count = Deposit.objects.filter(status="awaiting_review").count()
    confirm_count = Deposit.objects.filter(
        status="received", deposit_confirmed_sent=False
    ).count()
    total = review_count + confirm_count

    if total == 0:
        return ""

    parts = []
    if review_count:
        parts.append(f"{review_count} new booking{'s' if review_count != 1 else ''} to review")
    if confirm_count:
        parts.append(f"{confirm_count} confirmation{'s' if confirm_count != 1 else ''} to send")
    message = " &middot; ".join(parts)

    return format_html(
        '<script>'
        '(function(){{'
        '  if(document.getElementById("deposit-notify"))return;'
        '  var b=document.createElement("div");'
        '  b.id="deposit-notify";'
        '  b.innerHTML=\'<a href="/admin/snippets/clients/deposit/?status=awaiting_review" '
        '    style="display:flex;align-items:center;justify-content:center;gap:.5rem;'
        '    background:#fef3c7;border-bottom:2px solid #f59e0b;padding:.6rem 1rem;'
        '    font-size:.85rem;font-weight:600;color:#92400e;text-decoration:none;">'
        '    ⚠️ Action Required: {} — Click here to view</a>\';'
        '  var main=document.querySelector("main")||document.body;'
        '  main.parentNode.insertBefore(b,main);'
        '}})();'
        '</script>',
        message,
    )
