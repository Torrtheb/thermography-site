import logging

from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_POST

from wagtail.admin.auth import require_admin_access

from .brevo import add_contact_to_brevo, remove_contact_from_brevo, unblock_contact_in_brevo
from .forms import ComposeNewsletterForm, NewsletterForm
from .models import NewsletterCampaign, NewsletterSubscriber, SubscribeRateLimit
from .email import send_newsletter, send_welcome_email

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    """Extract client IP, using the rightmost X-Forwarded-For value.

    Behind a single trusted proxy (Railway, Cloud Run), the proxy appends
    the real client IP as the last entry.  An attacker can prepend fake
    values, but cannot control the last one.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


@require_POST
def subscribe(request):
    """AJAX endpoint to subscribe an email to the newsletter."""
    ip = _get_client_ip(request)

    honeypot_val = request.POST.get("website", "")
    if honeypot_val:
        return JsonResponse({"ok": True, "message": "Thank you for subscribing!"})

    is_limited, ip_hash = SubscribeRateLimit.check_and_increment(ip)
    if is_limited:
        return JsonResponse(
            {"ok": False, "error": "Too many attempts. Please try again later."},
            status=429,
        )

    form = NewsletterForm(request.POST)

    raw_email = (request.POST.get("email") or "").lower().strip()

    if raw_email:
        existing = NewsletterSubscriber.objects.filter(email=raw_email).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.ip_hash = ip_hash
                existing.save(update_fields=["is_active", "ip_hash"])
                unblock_contact_in_brevo(raw_email)
                add_contact_to_brevo(raw_email)
                send_welcome_email(raw_email)
                return JsonResponse(
                    {"ok": True, "message": "Welcome back! You've been re-subscribed."}
                )
            return JsonResponse(
                {"ok": True, "message": "You're already subscribed — thank you!"}
            )

    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0]
        return JsonResponse({"ok": False, "error": first_error}, status=400)

    email = form.cleaned_data["email"]

    try:
        NewsletterSubscriber.objects.create(email=email, ip_hash=ip_hash)
    except IntegrityError:
        logger.info("Duplicate subscriber race handled for email hash")
        return JsonResponse(
            {"ok": True, "message": "Thank you for subscribing!"}
        )

    add_contact_to_brevo(email)
    send_welcome_email(email)
    return JsonResponse(
        {"ok": True, "message": "Thank you for subscribing!"}
    )


def unsubscribe(request, token):
    """One-click unsubscribe via unique token in email footer."""
    subscriber = get_object_or_404(NewsletterSubscriber, token=token)

    if request.method == "POST":
        subscriber.is_active = False
        subscriber.save(update_fields=["is_active"])
        remove_contact_from_brevo(subscriber.email)  # sync to Brevo list
        return render(request, "newsletter/unsubscribed.html", {
            "email": subscriber.email,
        })

    # GET → show confirmation page
    return render(request, "newsletter/unsubscribe_confirm.html", {
        "email": subscriber.email,
        "token": token,
    })


# ──────────────────────────────────────────────────────────
# Wagtail admin: Compose & Send Newsletter
# ──────────────────────────────────────────────────────────

class ComposeNewsletterView(View):
    """
    Wagtail admin view for composing and sending a newsletter
    to all active subscribers.
    """

    template_name = "newsletter/admin/compose_newsletter.html"

    def _get_context(self, form):
        active_count = NewsletterSubscriber.objects.filter(is_active=True).count()
        recent_campaigns = NewsletterCampaign.objects.all()[:10]
        return {
            "form": form,
            "page_title": "Send Newsletter",
            "active_subscriber_count": active_count,
            "recent_campaigns": recent_campaigns,
        }

    def get(self, request):
        form = ComposeNewsletterForm()
        return render(request, self.template_name, self._get_context(form))

    def post(self, request):
        form = ComposeNewsletterForm(request.POST)
        if form.is_valid():
            campaign = NewsletterCampaign.objects.create(
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                sign_off=form.cleaned_data["sign_off"],
            )

            sent, failed = send_newsletter(campaign)

            if sent:
                messages.success(
                    request,
                    f"Newsletter sent to {sent} subscriber(s)!"
                    + (f" ({failed} failed)" if failed else ""),
                )
            elif failed:
                messages.error(
                    request,
                    f"Newsletter sending failed for all {failed} recipient(s).",
                )
            else:
                messages.warning(request, "No active subscribers to send to.")

            return redirect(reverse("newsletter_compose"))

        return render(request, self.template_name, self._get_context(form))


compose_newsletter_view = require_admin_access(ComposeNewsletterView.as_view())
