"""
Cal.com webhook handler — auto-creates Client + Deposit records on new bookings.

Setup (one-time):
  1. In Cal.com → Settings → Developer → Webhooks, create a new webhook:
     - Subscriber URL: https://your-domain.com/api/webhooks/calcom/
     - Event triggers: Booking Created, Booking Cancelled
     - Secret: paste the value of CAL_WEBHOOK_SECRET from your env vars
  2. Set CAL_WEBHOOK_SECRET in your Railway env vars (or .env for local dev).

Security:
  - HMAC-SHA256 signature verification (x-cal-signature-256 header)
  - CSRF-exempt (external POST from Cal.com servers)
  - Returns 200 even on processing errors (prevents Cal.com retries flooding logs)
"""

import hashlib
import hmac
import json
import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _verify_signature(request):
    """Verify Cal.com webhook HMAC-SHA256 signature."""
    secret = getattr(settings, "CAL_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("CAL_WEBHOOK_SECRET not configured — skipping signature verification")
        return True

    signature = request.headers.get("x-cal-signature-256", "")
    if not signature:
        logger.warning("Missing x-cal-signature-256 header")
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def _get_deposit_amount():
    """Fetch the configured deposit amount from SiteSettings."""
    try:
        from wagtail.models import Site
        from home.models import SiteSettings
        site = Site.objects.get(is_default_site=True)
        return SiteSettings.for_site(site).deposit_amount or Decimal("25.00")
    except Exception:
        return Decimal("25.00")


def _parse_appointment_date(start_time_str):
    """Parse a Cal.com startTime ISO string into a date object."""
    if not start_time_str:
        return None
    try:
        return date.fromisoformat(start_time_str[:10])
    except (ValueError, TypeError):
        return None


def _handle_booking_created(payload):
    """Auto-create a Client (or find existing) and Deposit, then send deposit request email."""
    from clients.models import Client, Deposit
    from clients.email import send_deposit_request

    attendees = payload.get("attendees", [])
    if not attendees:
        logger.info("BOOKING_CREATED webhook: no attendees — skipping")
        return

    attendee = attendees[0]
    client_email = attendee.get("email", "").strip()
    client_name = attendee.get("name", "").strip()
    booking_uid = payload.get("uid", "")
    start_time = payload.get("startTime", "")
    event_title = payload.get("eventTitle", "") or payload.get("title", "")
    appointment_date = _parse_appointment_date(start_time)

    if not client_email:
        logger.info("BOOKING_CREATED webhook: no attendee email — skipping")
        return

    if booking_uid and Deposit.objects.filter(cal_booking_uid=booking_uid).exists():
        logger.info("BOOKING_CREATED webhook: deposit already exists for uid=%s", booking_uid)
        return

    # Find or create client (match by email — iterate because email is encrypted)
    client = None
    for c in Client.objects.all().iterator():
        if c.email and c.email.lower() == client_email.lower():
            client = c
            break

    if client is None:
        client = Client.objects.create(
            name=client_name,
            email=client_email,
        )
        logger.info("Created new client pk=%s from Cal.com booking", client.pk)
    else:
        if appointment_date:
            client.last_appointment_date = appointment_date
            client.save(update_fields=["last_appointment_date", "updated_at"])

    deposit_amount = _get_deposit_amount()

    date_str = ""
    if appointment_date:
        date_str = appointment_date.strftime("%B %d, %Y")

    deposit = Deposit.objects.create(
        client=client,
        amount=deposit_amount,
        appointment_date=appointment_date,
        service_name=event_title,
        cal_booking_uid=booking_uid,
        status="pending",
    )
    logger.info("Created deposit pk=%s for client pk=%s (cal uid=%s)", deposit.pk, client.pk, booking_uid)

    try:
        send_deposit_request(client, deposit_amount, appointment_date=date_str)
        deposit.deposit_request_sent = True
        deposit.save(update_fields=["deposit_request_sent", "updated_at"])
        logger.info("Deposit request email sent for deposit pk=%s", deposit.pk)
    except Exception:
        logger.exception("Failed to send deposit request email for deposit pk=%s", deposit.pk)


def _handle_booking_cancelled(payload):
    """Auto-forfeit the deposit when a Cal.com booking is cancelled."""
    from clients.models import Deposit

    booking_uid = payload.get("uid", "")
    if not booking_uid:
        logger.info("BOOKING_CANCELLED webhook: no booking uid — skipping")
        return

    try:
        deposit = Deposit.objects.get(cal_booking_uid=booking_uid)
    except Deposit.DoesNotExist:
        logger.info("BOOKING_CANCELLED webhook: no deposit found for uid=%s", booking_uid)
        return

    if deposit.status == "received":
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + "\nAuto-forfeited: client cancelled via Cal.com."
        deposit.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Deposit pk=%s forfeited (client cancelled, had paid)", deposit.pk)
    elif deposit.status == "pending":
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + "\nAuto-forfeited: client cancelled before paying deposit."
        deposit.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Deposit pk=%s forfeited (client cancelled, never paid)", deposit.pk)


@csrf_exempt
@require_POST
def calcom_webhook_view(request):
    """Receive and process Cal.com webhook events."""
    if not _verify_signature(request):
        return JsonResponse({"error": "invalid signature"}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid json"}, status=400)

    trigger = data.get("triggerEvent", "")
    payload = data.get("payload", {})

    if trigger == "BOOKING_CREATED":
        try:
            _handle_booking_created(payload)
        except Exception:
            logger.exception("Error handling BOOKING_CREATED webhook")
    elif trigger == "BOOKING_CANCELLED":
        try:
            _handle_booking_cancelled(payload)
        except Exception:
            logger.exception("Error handling BOOKING_CANCELLED webhook")
    else:
        logger.info("Ignoring Cal.com webhook trigger: %s", trigger)

    return JsonResponse({"ok": True})


# ──────────────────────────────────────────────────────────
# Cron endpoint — expire unpaid deposits every hour
# ──────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def cron_expire_deposits_view(request):
    """
    HTTP-callable endpoint for the 48-hour deposit expiry rule.

    Protected by CRON_SECRET — an external cron service (e.g. cron-job.org)
    POSTs to this URL every hour with the secret in the Authorization header.

    Header format:  Authorization: Bearer <CRON_SECRET>
    """
    expected_secret = getattr(settings, "CRON_SECRET", "")
    if not expected_secret:
        return JsonResponse({"error": "CRON_SECRET not configured"}, status=500)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JsonResponse({"error": "unauthorized"}, status=403)

    token = auth_header[7:]
    if not hmac.compare_digest(token, expected_secret):
        return JsonResponse({"error": "unauthorized"}, status=403)

    from django.utils import timezone as tz
    from clients.models import Deposit

    cutoff = tz.now() - tz.timedelta(hours=48)
    expired = Deposit.objects.filter(status="pending", created_at__lt=cutoff)
    count = expired.count()

    if count > 0:
        pks = list(expired.values_list("pk", flat=True))
        expired.update(status="forfeited", updated_at=tz.now())

        for deposit in Deposit.objects.filter(pk__in=pks):
            deposit.notes = (
                (deposit.notes or "") +
                "\nAuto-forfeited: deposit not received within 48 hours of booking."
            )
            deposit.save(update_fields=["notes", "updated_at"])

        logger.info("Cron: forfeited %d expired deposit(s)", count)

    return JsonResponse({"ok": True, "forfeited": count})
