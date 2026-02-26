"""
Wagtail hooks for the newsletter app.

Provides:
- Newsletter subscribers as a snippet in the admin sidebar
- Newsletter campaigns as a snippet (campaign history)
- "Send Newsletter" menu item for composing and sending newsletters
"""

from django.urls import path, reverse

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import NewsletterCampaign, NewsletterSubscriber
from .views import compose_newsletter_view


# ──────────────────────────────────────────────────────────
# Snippet viewset — Subscriber list
# ──────────────────────────────────────────────────────────

class NewsletterSubscriberViewSet(SnippetViewSet):
    model = NewsletterSubscriber
    icon = "group"
    menu_label = "Subscribers"
    menu_name = "newsletter_subscribers"
    menu_order = 250
    add_to_admin_menu = True
    list_display = ["email", "subscribed_at", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["email"]
    ordering = ["-subscribed_at"]


register_snippet(NewsletterSubscriber, viewset=NewsletterSubscriberViewSet)


# ──────────────────────────────────────────────────────────
# Snippet viewset — Campaign history (accessible but not in sidebar)
# ──────────────────────────────────────────────────────────

class NewsletterCampaignViewSet(SnippetViewSet):
    model = NewsletterCampaign
    icon = "doc-full-inverse"
    menu_label = "Campaigns"
    menu_name = "newsletter_campaigns"
    menu_order = 252
    add_to_admin_menu = False  # accessed via Send Newsletter page instead
    list_display = ["subject", "status_badge", "sent_count", "recipients_count", "sent_at"]
    list_filter = ["status"]
    ordering = ["-created_at"]
    add_to_settings_menu = False
    inspect_view_enabled = True


register_snippet(NewsletterCampaign, viewset=NewsletterCampaignViewSet)


# ──────────────────────────────────────────────────────────
# Custom admin URL for compose/send
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_urls")
def register_newsletter_urls():
    return [
        path("newsletter/compose/", compose_newsletter_view, name="newsletter_compose"),
    ]


# ──────────────────────────────────────────────────────────
# Sidebar menu item
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_menu_item")
def register_newsletter_menu_item():
    return MenuItem(
        "Send Newsletter",
        reverse("newsletter_compose"),
        icon_name="mail",
        order=251,  # after Subscribers (250), before Campaigns (252)
    )
