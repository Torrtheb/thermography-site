"""
Wagtail hooks for the newsletter app.

Provides:
- Newsletter subscribers as a snippet in the admin sidebar
- Newsletter campaigns as a snippet (campaign history)
- "Send Newsletter" menu item for composing and sending newsletters
"""

from django.urls import path

from wagtail import hooks
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import NewsletterSubscriber
from .views import compose_newsletter_view


# ──────────────────────────────────────────────────────────
# Snippet viewset — Subscriber list (menu entry lives in
# the "Contact" submenu registered in clients/wagtail_hooks)
# ──────────────────────────────────────────────────────────

class NewsletterSubscriberViewSet(SnippetViewSet):
    model = NewsletterSubscriber
    icon = "group"
    menu_label = "Subscribers"
    menu_name = "newsletter_subscribers"
    menu_order = 250
    add_to_admin_menu = False
    list_display = ["email", "subscribed_at", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["email"]
    ordering = ["-subscribed_at"]


register_snippet(NewsletterSubscriber, viewset=NewsletterSubscriberViewSet)


# ──────────────────────────────────────────────────────────
# Custom admin URL for compose/send
# ──────────────────────────────────────────────────────────

@hooks.register("register_admin_urls")
def register_newsletter_urls():
    return [
        path("newsletter/compose/", compose_newsletter_view, name="newsletter_compose"),
    ]
