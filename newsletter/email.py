"""
Email sending utilities for the newsletter app.

Uses Django's built-in email framework (Brevo HTTP API in production,
console backend in development).

Deliverability notes (avoid spam folders):
  1. Authenticate the sending domain in Brevo (SPF + DKIM DNS records).
  2. Use a real FROM address on that domain (not noreply@).
  3. All emails include a List-Unsubscribe header (RFC 8058) so Gmail/Outlook
     show a native unsubscribe button instead of flagging as spam.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import NewsletterCampaign, NewsletterDelivery, NewsletterSubscriber

logger = logging.getLogger(__name__)

# Brevo's free plan allows 300 emails/day across the whole account. We default
# to a lower budget so welcome/transactional emails still have headroom; the
# remainder of a large list is delivered automatically over subsequent days.
DEFAULT_DAILY_SEND_LIMIT = 250


def _redact_email(email: str) -> str:
    """Mask an email for safe logging, e.g. 'j***@example.com'."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


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


def _build_message(subject, plain_body, html_body, from_email, to_email, unsubscribe_url):
    """Build an EmailMultiAlternatives with List-Unsubscribe headers."""
    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=from_email,
        to=[to_email],
    )
    if html_body:
        msg.attach_alternative(html_body, "text/html")

    if unsubscribe_url:
        msg.extra_headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg.extra_headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    return msg


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

    try:
        html_message = render_to_string("newsletter/emails/welcome.html", context)
    except Exception:
        html_message = None

    try:
        msg = _build_message(
            subject, plain_message, html_message,
            from_email, email, unsubscribe_url,
        )
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send welcome email to %s", _redact_email(email))
        return False


def enqueue_newsletter(campaign: NewsletterCampaign) -> int:
    """
    Queue a campaign for throttled, multi-day delivery.

    Snapshots the current active subscribers into NewsletterDelivery rows
    (status="pending") and marks the campaign "queued". No email is sent
    here — the ``send_pending_newsletters`` management command (run daily by
    cron) drains the queue up to the daily quota.

    Returns the number of recipients queued.
    """
    subscriber_ids = list(
        NewsletterSubscriber.objects.filter(is_active=True).values_list("id", flat=True)
    )
    total = len(subscriber_ids)

    if total == 0:
        campaign.status = "failed"
        campaign.recipients_count = 0
        campaign.save(update_fields=["status", "recipients_count"])
        return 0

    NewsletterDelivery.objects.bulk_create(
        [
            NewsletterDelivery(campaign=campaign, subscriber_id=sid, status="pending")
            for sid in subscriber_ids
        ],
        ignore_conflicts=True,
        batch_size=500,
    )

    campaign.status = "queued"
    campaign.recipients_count = total
    campaign.queued_at = timezone.now()
    campaign.save(update_fields=["status", "recipients_count", "queued_at"])

    logger.info("Newsletter campaign %s queued for %d recipients.", campaign.pk, total)
    return total


def retry_failed_deliveries(max_attempts: int = 3) -> int:
    """
    Re-queue failed deliveries so the next drain run retries them.

    Only deliveries whose attempt count is below ``max_attempts`` are reset,
    so a hard bounce that keeps failing won't be retried forever. Any campaign
    that had already been finalized is re-opened to "sending" so the drainer
    picks its rows back up.

    Returns the number of deliveries re-queued.
    """
    qs = NewsletterDelivery.objects.filter(
        status="failed", attempts__lt=max_attempts
    )
    campaign_ids = list(qs.values_list("campaign_id", flat=True).distinct())
    requeued = qs.update(status="pending", last_error="")

    if requeued:
        NewsletterCampaign.objects.filter(
            id__in=campaign_ids, status__in=["sent", "partial", "failed"]
        ).update(status="sending")
        logger.info("Re-queued %d failed deliveries for retry.", requeued)

    return requeued


def _campaign_html(campaign: NewsletterCampaign, site_name: str, unsubscribe_url: str):
    """Render the HTML body for a campaign (falls back to plain text)."""
    from django.utils.html import escape

    body_html = "".join(
        f"<p>{escape(para)}</p>"
        for para in campaign.body.split("\n\n")
        if para.strip()
    )
    try:
        return render_to_string(
            "newsletter/emails/campaign.html",
            {
                "site_name": site_name,
                "body_html": body_html,
                "sign_off": campaign.sign_off or "",
                "unsubscribe_url": unsubscribe_url,
            },
        )
    except Exception:
        return None


def _send_delivery(delivery: NewsletterDelivery, from_email: str, site_name: str) -> str:
    """
    Attempt to send one queued delivery. Updates the row in place.

    Returns the resulting status: "sent", "failed", or "skipped".
    """
    subscriber = delivery.subscriber

    # Respect unsubscribes that happened after the campaign was queued.
    if not subscriber.is_active:
        delivery.status = "skipped"
        delivery.save(update_fields=["status"])
        return "skipped"

    campaign = delivery.campaign
    unsubscribe_url = _get_unsubscribe_url(subscriber.token)

    full_body = campaign.body
    if campaign.sign_off:
        full_body = f"{campaign.body}\n\n{campaign.sign_off}"
    personalised_body = f"{full_body}\n\n---\nTo unsubscribe, visit: {unsubscribe_url}"

    html_message = _campaign_html(campaign, site_name, unsubscribe_url)

    delivery.attempts += 1
    try:
        msg = _build_message(
            campaign.subject, personalised_body, html_message,
            from_email, subscriber.email, unsubscribe_url,
        )
        msg.send(fail_silently=False)
        delivery.status = "sent"
        delivery.sent_at = timezone.now()
        delivery.last_error = ""
        delivery.save(update_fields=["status", "sent_at", "attempts", "last_error"])
        return "sent"
    except Exception as exc:
        logger.exception(
            "Failed to send newsletter to %s", _redact_email(subscriber.email)
        )
        delivery.status = "failed"
        delivery.last_error = str(exc)[:500]
        delivery.save(update_fields=["status", "attempts", "last_error"])
        return "failed"


def _refresh_campaign_counts(campaign: NewsletterCampaign) -> None:
    """Recompute a campaign's aggregate counts and finalize its status."""
    from django.db.models import Count, Q

    agg = campaign.deliveries.aggregate(
        sent=Count("pk", filter=Q(status="sent")),
        failed=Count("pk", filter=Q(status="failed")),
        pending=Count("pk", filter=Q(status="pending")),
    )
    campaign.sent_count = agg["sent"]
    campaign.failed_count = agg["failed"]

    update_fields = ["sent_count", "failed_count"]

    if agg["pending"] == 0:
        # Queue fully drained — finalize status.
        if agg["sent"] and not agg["failed"]:
            campaign.status = "sent"
        elif agg["sent"]:
            campaign.status = "partial"
        else:
            campaign.status = "failed"
        campaign.sent_at = timezone.now()
        update_fields += ["status", "sent_at"]
    elif campaign.status != "sending":
        campaign.status = "sending"
        update_fields.append("status")

    campaign.save(update_fields=update_fields)


def send_pending_newsletters(daily_limit: int | None = None, on_event=None) -> dict:
    """
    Drain queued newsletter deliveries, respecting the daily send budget.

    Sends up to ``daily_limit`` emails today *in total* (counting anything
    already sent today, so the command is safe to run multiple times per day).
    Processes the oldest queued campaign first. Returns a summary dict.

    ``on_event`` is an optional callable(str) used for logging progress
    (e.g. the management command's stdout writer).
    """
    if daily_limit is None:
        daily_limit = getattr(
            settings, "NEWSLETTER_DAILY_SEND_LIMIT", DEFAULT_DAILY_SEND_LIMIT
        )

    def emit(msg):
        logger.info(msg)
        if on_event:
            on_event(msg)

    today = timezone.localdate()
    already_sent_today = NewsletterDelivery.objects.filter(
        status="sent", sent_at__date=today
    ).count()
    budget = max(0, daily_limit - already_sent_today)

    summary = {
        "daily_limit": daily_limit,
        "already_sent_today": already_sent_today,
        "budget": budget,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "campaigns": [],
    }

    if budget == 0:
        emit(
            f"Daily send budget exhausted ({already_sent_today}/{daily_limit} "
            f"already sent today). Nothing to do."
        )
        return summary

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Thermography")

    campaigns = NewsletterCampaign.objects.filter(
        status__in=["queued", "sending"]
    ).order_by("created_at")

    for campaign in campaigns:
        if budget <= 0:
            break

        # Mark as in-progress as soon as we start sending.
        if campaign.status == "queued":
            campaign.status = "sending"
            campaign.save(update_fields=["status"])

        pending = (
            campaign.deliveries.filter(status="pending")
            .select_related("subscriber")
            .order_by("pk")[:budget]
        )

        c_sent = c_failed = c_skipped = 0
        for delivery in pending:
            if budget <= 0:
                break
            result = _send_delivery(delivery, from_email, site_name)
            if result == "sent":
                c_sent += 1
                budget -= 1  # skips/failures don't consume Brevo quota
            elif result == "failed":
                c_failed += 1
                budget -= 1  # a failed attempt still hit the API
            else:
                c_skipped += 1

        _refresh_campaign_counts(campaign)
        campaign.refresh_from_db(fields=["status"])

        summary["sent"] += c_sent
        summary["failed"] += c_failed
        summary["skipped"] += c_skipped
        summary["campaigns"].append(
            {
                "id": campaign.pk,
                "subject": campaign.subject,
                "sent": c_sent,
                "failed": c_failed,
                "skipped": c_skipped,
                "status": campaign.status,
                "remaining": campaign.pending_count,
            }
        )
        emit(
            f"Campaign #{campaign.pk} '{campaign.subject}': "
            f"sent {c_sent}, failed {c_failed}, skipped {c_skipped}, "
            f"remaining {campaign.pending_count} (status={campaign.status})."
        )

    emit(
        f"Done. Sent {summary['sent']} this run "
        f"({already_sent_today + summary['sent']}/{daily_limit} today)."
    )
    return summary
