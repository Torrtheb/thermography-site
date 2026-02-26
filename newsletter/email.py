"""
Email sending utilities for the newsletter app.

Uses Django's built-in email framework (Brevo SMTP in production,
console backend in development).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import NewsletterCampaign, NewsletterSubscriber

logger = logging.getLogger(__name__)


def _get_base_url() -> str:
    """Return the site's base URL from settings, e.g. https://example.com."""
    url = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
    if "localhost" in url or "127.0.0.1" in url:
        logger.warning(
            "SITE_URL is '%s' — newsletter emails will contain localhost links. "
            "Set SITE_URL to the public domain in production.",
            url,
        )
    return url


def _get_unsubscribe_url(token) -> str:
    """Build the full unsubscribe URL for a subscriber token."""
    path = reverse("newsletter:unsubscribe", kwargs={"token": str(token)})
    return f"{_get_base_url()}{path}"


def send_welcome_email(email: str) -> bool:
    """
    Send a 'thank you for subscribing' confirmation email to a new subscriber.

    Args:
        email: The subscriber's email address.

    Returns:
        True if sent successfully, False on failure.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    subject = "Welcome! Thanks for Subscribing"

    # Look up subscriber token for unsubscribe link
    try:
        subscriber = NewsletterSubscriber.objects.get(email=email)
        unsubscribe_url = _get_unsubscribe_url(subscriber.token)
    except NewsletterSubscriber.DoesNotExist:
        unsubscribe_url = ""

    context = {
        "email": email,
        "site_name": getattr(settings, "WAGTAIL_SITE_NAME", "Thermography"),
        "unsubscribe_url": unsubscribe_url,
    }

    plain_message = (
        f"Hi there!\n\n"
        f"Thank you for subscribing to the {context['site_name']} newsletter.\n\n"
        f"You'll receive wellness tips, thermography insights, and updates "
        f"straight to your inbox. We promise — no spam, just the good stuff.\n\n"
        f"To unsubscribe, visit: {unsubscribe_url}\n\n"
        f"Warm regards,\n"
        f"The {context['site_name']} Team"
    )

    # Try HTML template; fall back to plain text only
    try:
        html_message = render_to_string(
            "newsletter/emails/welcome.html", context
        )
    except Exception:
        html_message = None

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send welcome email to %s", email)
        return False


def send_newsletter(campaign: NewsletterCampaign) -> tuple[int, int]:
    """
    Send a newsletter campaign to all active subscribers.

    Uses send_mail per-recipient so failures are isolated and each
    recipient gets their own unsubscribe link.
    Returns (sent_count, failed_count).
    """
    subscribers = NewsletterSubscriber.objects.filter(is_active=True).values_list(
        "email", "token",
    )
    subscriber_list = list(subscribers)
    total = len(subscriber_list)

    if total == 0:
        campaign.status = "failed"
        campaign.recipients_count = 0
        campaign.save(update_fields=["status", "recipients_count"])
        return 0, 0

    campaign.status = "sending"
    campaign.recipients_count = total
    campaign.save(update_fields=["status", "recipients_count"])

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Thermography")

    full_body = campaign.body
    if campaign.sign_off:
        full_body = f"{campaign.body}\n\n{campaign.sign_off}"

    # Convert plain-text body to simple HTML (preserve paragraphs)
    body_html = "".join(
        f"<p>{para}</p>" for para in campaign.body.split("\n\n") if para.strip()
    )

    sent = 0
    failed = 0

    for email_addr, token in subscriber_list:
        unsubscribe_url = _get_unsubscribe_url(token)

        # Plain-text version (fallback)
        personalised_body = (
            f"{full_body}\n\n---\n"
            f"To unsubscribe, visit: {unsubscribe_url}"
        )

        # HTML version
        try:
            html_message = render_to_string(
                "newsletter/emails/campaign.html",
                {
                    "site_name": site_name,
                    "body_html": body_html,
                    "sign_off": campaign.sign_off or "",
                    "unsubscribe_url": unsubscribe_url,
                },
            )
        except Exception:
            html_message = None

        try:
            send_mail(
                subject=campaign.subject,
                message=personalised_body,
                from_email=from_email,
                recipient_list=[email_addr],
                html_message=html_message,
                fail_silently=False,
            )
            sent += 1
        except Exception:
            logger.exception("Failed to send newsletter to %s", email_addr)
            failed += 1

    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.sent_at = timezone.now()
    campaign.status = "sent" if failed == 0 else ("failed" if sent == 0 else "partial")
    campaign.save(update_fields=[
        "sent_count", "failed_count", "sent_at", "status",
    ])

    return sent, failed
