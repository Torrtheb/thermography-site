"""
Cal.com webhook handler — bidirectional sync between Cal.com and Wagtail.
Cal.com API integration — confirm, decline, and cancel bookings.

Handled webhook events:
  BOOKING_CREATED / BOOKING_REQUESTED → creates Client + Deposit (awaiting_review)
  BOOKING_CONFIRMED → transitions deposit to "confirmed" (owner confirmed in Cal.com)
  BOOKING_CANCELLED → forfeits the deposit
  BOOKING_REJECTED  → forfeits the deposit (owner declined in Cal.com)
  BOOKING_RESCHEDULED → updates deposit date and booking UID

Wagtail → Cal.com actions:
  "Approve & Send" → sends deposit request email (no Cal.com API call needed)
  "Mark Received & Confirm" → confirms booking via Cal.com API
  "Reject & Cancel" → declines booking via Cal.com API
  48-hour expiry cron → cancels booking via Cal.com API

Setup (one-time):
  1. In Cal.com → Settings → Developer → Webhooks, create a new webhook:
     - Subscriber URL: https://your-domain.com/api/webhooks/calcom/
     - Event triggers: Booking Created, Booking Requested, Booking Confirmed,
       Booking Cancelled, Booking Rejected, Booking Rescheduled
     - Secret: paste the value of CAL_WEBHOOK_SECRET from your env vars
  2. In Cal.com → Settings → Developer → API Keys, create a new key.
  3. Set CAL_WEBHOOK_SECRET, CAL_API_KEY, and CRON_SECRET in your env vars.

Note: When "Requires confirmation" is enabled on a Cal.com event type,
new bookings trigger BOOKING_REQUESTED (not BOOKING_CREATED).
We handle both events identically.

Security:
  - HMAC-SHA256 signature verification (x-cal-signature-256 header)
  - CSRF-exempt (external POST from Cal.com servers)
  - Returns 200 even on processing errors (prevents Cal.com retries flooding logs)
"""

import hashlib
import hmac
import json
import logging
import re
import urllib.request
import urllib.error
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

_SAFE_UID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


# ──────────────────────────────────────────────────────────
# Cal.com API helpers
# ──────────────────────────────────────────────────────────

CAL_API_VERSION = "2026-02-25"


def _calcom_api_post(path, body_dict=None):
    """
    Make an authenticated POST to the Cal.com v2 API.

    Returns (success: bool, response_body: str).
    """
    api_key = getattr(settings, "CAL_API_KEY", "")
    if not api_key:
        logger.warning("CAL_API_KEY not configured — cannot call %s", path)
        return False, ""

    if not path.startswith("/v2/"):
        logger.error("Rejecting Cal.com API call to unexpected path: %s", path)
        return False, "invalid path"

    url = f"https://api.cal.com{path}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "cal-api-version": CAL_API_VERSION,
        "User-Agent": "ThermographyClinic/1.0",
        "Accept": "application/json",
    }

    if body_dict is not None:
        body = json.dumps(body_dict).encode()
        headers["Content-Type"] = "application/json"
    else:
        body = None

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")[:500]
            logger.info("Cal.com API %s → %d: %s", path, resp.status, resp_body[:200])
            return True, resp_body
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Cal.com API %s → HTTP %d: %s", path, e.code, resp_body)
        return False, f"HTTP {e.code}: {resp_body}"
    except Exception as exc:
        logger.warning("Cal.com API %s → exception: %s", path, exc)
        return False, str(exc)


def cancel_calcom_booking(booking_uid, reason=""):
    """
    Cancel a Cal.com booking via the API.

    Returns True if successful (or booking was already cancelled),
    False if the API call failed or CAL_API_KEY is not set.
    """
    if not booking_uid or not _SAFE_UID_RE.match(booking_uid):
        return False

    ok, resp = _calcom_api_post(
        f"/v2/bookings/{booking_uid}/cancel",
        {"cancellationReason": reason or "Booking deposit not received within 48 hours."},
    )

    if ok:
        logger.info("Cal.com booking %s cancelled", booking_uid)
        return True

    if "already cancelled" in resp.lower():
        logger.info("Cal.com booking %s was already cancelled", booking_uid)
        return True

    logger.error("Cal.com cancel failed for %s: %s", booking_uid, resp)
    return False


def confirm_calcom_booking(booking_uid):
    """
    Confirm a Cal.com booking that requires manual confirmation.

    Called when the owner marks a deposit as received, so the booking
    moves from "awaiting confirmation" to "confirmed" in Cal.com
    (which sends Cal.com's own confirmation email to the client).

    Returns True if successful, False otherwise.
    """
    if not booking_uid or not _SAFE_UID_RE.match(booking_uid):
        logger.warning("confirm_calcom_booking: invalid or empty uid=%r", booking_uid)
        return False

    logger.warning("Attempting to confirm Cal.com booking uid=%s", booking_uid)

    ok, resp = _calcom_api_post(f"/v2/bookings/{booking_uid}/confirm")

    if ok:
        logger.warning("Cal.com booking %s confirmed successfully: %s", booking_uid, resp[:200])
        return True

    resp_lower = resp.lower()
    if "already confirmed" in resp_lower or "accepted" in resp_lower:
        logger.warning("Cal.com booking %s was already confirmed", booking_uid)
        return True

    logger.warning("Cal.com confirm FAILED for uid=%s — response: %s", booking_uid, resp)
    return False


def decline_calcom_booking(booking_uid, reason=""):
    """
    Decline (reject) a Cal.com booking that is awaiting confirmation.

    Called when the owner rejects a booking from Wagtail admin. This removes
    the booking from Cal.com and notifies the client via Cal.com's own email.

    Returns True if successful, False otherwise.
    """
    if not booking_uid or not _SAFE_UID_RE.match(booking_uid):
        return False

    ok, resp = _calcom_api_post(
        f"/v2/bookings/{booking_uid}/decline",
        {"reason": reason or "Booking declined by organizer."},
    )

    if ok:
        logger.info("Cal.com booking %s declined", booking_uid)
        return True

    resp_lower = resp.lower()
    if "already" in resp_lower or "rejected" in resp_lower or "cancelled" in resp_lower:
        logger.info("Cal.com booking %s was already declined/cancelled", booking_uid)
        return True

    logger.warning("Cal.com decline failed for uid=%s: %s", booking_uid, resp)
    return False


# ──────────────────────────────────────────────────────────
# Shared expiry logic — used by both cron endpoint and management command
# ──────────────────────────────────────────────────────────

def expire_pending_deposits(hours=48):
    """
    Forfeit deposits that have been pending or awaiting review for too long,
    cancel/decline their Cal.com bookings, and notify the client and owner.

    Two categories are expired:
      1. "pending" deposits — the owner approved and sent the deposit request,
         but the client didn't pay within `hours` of `approved_at`.
      2. "awaiting_review" deposits — the owner never reviewed the booking
         within `hours` of `created_at`. The client never received a deposit
         email, so only a simple cancellation email is sent.

    Returns the number of deposits forfeited.
    """
    from django.db.models import F, Q
    from django.db.models.functions import Coalesce
    from django.utils import timezone as tz
    from clients.models import Deposit
    from clients.email import send_deposit_expired_cancellation, send_owner_deposit_expiry_notice

    cutoff = tz.now() - tz.timedelta(hours=hours)

    expired_qs = Deposit.objects.filter(
        Q(status="pending") | Q(status="awaiting_review"),
    ).annotate(
        timer_start=Coalesce(F("approved_at"), F("created_at")),
    ).filter(
        timer_start__lt=cutoff,
    ).select_related("client")

    expired_list = list(expired_qs)
    if not expired_list:
        return 0

    for deposit in expired_list:
        was_awaiting = deposit.status == "awaiting_review"

        # 1. Cancel/decline the Cal.com booking
        if deposit.cal_booking_uid:
            if was_awaiting:
                decline_calcom_booking(
                    deposit.cal_booking_uid,
                    reason="Booking expired — not reviewed within 48 hours.",
                )
            else:
                cancel_calcom_booking(deposit.cal_booking_uid)

        # 2. Update deposit status
        if was_awaiting:
            reason_note = f"Auto-forfeited: owner did not review within {hours} hours."
        else:
            reason_note = f"Auto-forfeited: deposit not received within {hours} hours."
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + f"\n{reason_note}"
        deposit.save(update_fields=["status", "notes", "updated_at"])

        # 3. Email the client
        date_str = deposit.appointment_date.strftime("%B %d, %Y") if deposit.appointment_date else ""
        try:
            send_deposit_expired_cancellation(
                deposit.client,
                deposit.amount,
                appointment_date=date_str,
                service_name=deposit.service_name,
            )
        except Exception:
            logger.exception("Failed to send cancellation email for deposit pk=%s", deposit.pk)

    # 4. Email the owner a summary
    try:
        send_owner_deposit_expiry_notice(expired_list)
    except Exception:
        logger.exception("Failed to send owner expiry notice")

    logger.info("Expired %d deposit(s) older than %d hours", len(expired_list), hours)
    return len(expired_list)


def _verify_signature(request):
    """Verify Cal.com webhook HMAC-SHA256 signature.

    Fail-closed: if CAL_WEBHOOK_SECRET is not set and DEBUG is off,
    reject the request. In development (DEBUG=True) the secret is
    optional so local testing works without Cal.com.
    """
    secret = getattr(settings, "CAL_WEBHOOK_SECRET", "")
    if not secret:
        if getattr(settings, "DEBUG", False):
            logger.warning("CAL_WEBHOOK_SECRET not configured — skipping verification (DEBUG mode)")
            return True
        logger.error("CAL_WEBHOOK_SECRET not configured in production — rejecting webhook")
        return False

    signature = request.headers.get("x-cal-signature-256", "")
    if not signature:
        logger.warning("Missing x-cal-signature-256 header")
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        logger.warning("Cal.com webhook signature mismatch — check CAL_WEBHOOK_SECRET")
        return False
    return True


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


def _infer_location_from_event(event_title):
    """Try to match a Cal.com event title to a Location name.

    Cal.com event types are typically named like "Full Body Scan — Nanaimo"
    or "Breast Screening — Victoria Pop-Up".  We compare against all
    Location names (case-insensitive substring match).

    Matching strategy (longest name first to avoid "Victoria" matching
    before "Victoria Pop-Up"):
      1. Full location name found as substring in the event title.
      2. No word-level fallback — too prone to false positives with
         generic words like "Main" or "Clinic".

    Returns the Location.name string if matched, or "" if no match.
    """
    if not event_title:
        return ""
    try:
        from booking.models import Location
        title_lower = event_title.lower()
        locations = list(Location.objects.all())
        # Sort longest name first so "Victoria Pop-Up" matches before "Victoria"
        locations.sort(key=lambda loc: len(loc.name), reverse=True)
        for loc in locations:
            if loc.name.lower() in title_lower:
                return loc.name
    except Exception:
        logger.debug("Could not look up location from event title", exc_info=True)
    return ""


def _infer_visit_reason(event_title):
    """Map a Cal.com event title to a VISIT_REASON_CHOICES key.

    Uses case-insensitive keyword matching against the event title.
    Order matters — more specific phrases are checked first to avoid
    "Breast Screening" matching the generic "screening" keyword.
    Returns "" if no confident match (never guesses).
    """
    if not event_title:
        return ""
    title_lower = event_title.lower()

    # Ordered most-specific first. Each keyword maps to a VISIT_REASON_CHOICES key.
    keyword_map = [
        ("breast", "breast_health"),
        ("full body", "full_body"),
        ("full-body", "full_body"),
        ("pain", "pain_inflammation"),
        ("inflammation", "pain_inflammation"),
        ("injury", "pain_inflammation"),
        ("sport", "pain_inflammation"),
        ("follow up", "follow_up"),
        ("follow-up", "follow_up"),
        ("followup", "follow_up"),
    ]
    for keyword, reason in keyword_map:
        if keyword in title_lower:
            return reason
    # "upper body" and other unrecognised services → leave blank
    # rather than guessing. The owner can set it manually.
    return ""


def _handle_booking_created(payload):
    """Auto-create a Client (or find existing) and Deposit in 'awaiting_review' status.

    The deposit request email is NOT sent automatically — the owner must
    review the client info in Wagtail admin and click "Approve & Send
    Deposit Request" to validate the client and trigger the email.

    Auto-populates on the Client record (only when real data is available):
      - last_appointment_date  (from startTime)
      - clinic_location        (inferred from eventTitle ↔ Location names)
      - previous_visit_reason  (inferred from eventTitle keywords)
    """
    from clients.models import Client, Deposit

    attendees = payload.get("attendees", [])
    if not attendees:
        logger.info("BOOKING_CREATED webhook: no attendees — skipping")
        return

    attendee = attendees[0]
    client_email = attendee.get("email", "").strip()
    client_name = attendee.get("name", "").strip()
    booking_uid = payload.get("uid", "")
    reschedule_uid = payload.get("rescheduleUid", "") or payload.get("rescheduleuid", "")
    start_time = payload.get("startTime", "")
    event_title = payload.get("eventTitle", "") or payload.get("title", "")
    appointment_date = _parse_appointment_date(start_time)

    if not client_email:
        logger.warning("BOOKING_CREATED webhook: no attendee email — skipping")
        return

    # If this is a reschedule, don't create a new deposit — the
    # BOOKING_RESCHEDULED handler updates the existing one.
    if reschedule_uid:
        logger.info(
            "BOOKING_CREATED webhook: reschedule detected (rescheduleUid=%s) — skipping, "
            "BOOKING_RESCHEDULED handler will update the existing deposit",
            reschedule_uid,
        )
        return

    if booking_uid and Deposit.objects.filter(cal_booking_uid=booking_uid).exists():
        logger.info("BOOKING_CREATED webhook: deposit already exists for uid=%s", booking_uid)
        return

    # Infer visit details from the event title (blank if no match)
    inferred_location = _infer_location_from_event(event_title)
    inferred_reason = _infer_visit_reason(event_title)

    # Find existing client by email hash (O(1) indexed lookup)
    client = Client.find_by_email(client_email)

    if client is None:
        create_kwargs = {"name": client_name, "email": client_email}
        if appointment_date:
            create_kwargs["last_appointment_date"] = appointment_date
        if inferred_location:
            create_kwargs["clinic_location"] = inferred_location
        if inferred_reason:
            create_kwargs["previous_visit_reason"] = inferred_reason

        client = Client.objects.create(**create_kwargs)
        logger.info("Created new client pk=%s from Cal.com booking", client.pk)
    else:
        update_fields = ["updated_at"]
        if client_name and client_name != client.name:
            client.name = client_name
            update_fields.append("name")
        if appointment_date:
            client.last_appointment_date = appointment_date
            update_fields.append("last_appointment_date")
        if inferred_location:
            client.clinic_location = inferred_location
            update_fields.append("clinic_location")
        if inferred_reason:
            client.previous_visit_reason = inferred_reason
            update_fields.append("previous_visit_reason")

        if len(update_fields) > 1:
            client.save(update_fields=update_fields)
            logger.info(
                "Updated client pk=%s from new booking: %s",
                client.pk, ", ".join(f for f in update_fields if f != "updated_at"),
            )

    deposit_amount = _get_deposit_amount()

    deposit = Deposit.objects.create(
        client=client,
        amount=deposit_amount,
        appointment_date=appointment_date,
        service_name=event_title,
        cal_booking_uid=booking_uid,
        status="awaiting_review",
    )
    logger.warning(
        "Created deposit pk=%s (awaiting_review) for client pk=%s (cal uid=%s)",
        deposit.pk, client.pk, booking_uid,
    )

    # Notify the owner so they know to review and approve
    from clients.email import send_owner_new_booking_notice
    try:
        send_owner_new_booking_notice(client, deposit)
    except Exception:
        logger.exception("Failed to send owner new-booking notice for deposit pk=%s", deposit.pk)


def _handle_booking_confirmed(payload):
    """Update deposit status when the owner confirms a booking in Cal.com."""
    from clients.models import Deposit

    booking_uid = payload.get("uid", "")
    if not booking_uid:
        logger.info("BOOKING_CONFIRMED webhook: no booking uid — skipping")
        return

    try:
        deposit = Deposit.objects.get(cal_booking_uid=booking_uid)
    except Deposit.DoesNotExist:
        logger.info("BOOKING_CONFIRMED webhook: no deposit found for uid=%s", booking_uid)
        return

    if deposit.status in ("awaiting_review", "pending", "received"):
        deposit.status = "confirmed"
        deposit.deposit_confirmed_sent = True
        deposit.notes = (deposit.notes or "") + "\nBooking confirmed via Cal.com."
        deposit.save(update_fields=["status", "deposit_confirmed_sent", "notes", "updated_at"])
        logger.info("Deposit pk=%s → confirmed (via Cal.com webhook)", deposit.pk)


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

    reason_map = {
        "awaiting_review": "client cancelled before owner reviewed",
        "pending": "client cancelled before paying deposit",
        "received": "client cancelled after paying deposit",
        "confirmed": "client cancelled after booking was confirmed",
    }
    reason = reason_map.get(deposit.status)
    if reason:
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + f"\nAuto-forfeited: {reason}."
        deposit.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Deposit pk=%s forfeited (%s)", deposit.pk, reason)


def _handle_booking_rejected(payload):
    """Auto-forfeit the deposit when the owner rejects a booking in Cal.com."""
    from clients.models import Deposit

    booking_uid = payload.get("uid", "")
    if not booking_uid:
        logger.info("BOOKING_REJECTED webhook: no booking uid — skipping")
        return

    try:
        deposit = Deposit.objects.get(cal_booking_uid=booking_uid)
    except Deposit.DoesNotExist:
        logger.info("BOOKING_REJECTED webhook: no deposit found for uid=%s", booking_uid)
        return

    if deposit.status in ("awaiting_review", "pending", "received", "confirmed"):
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + "\nAuto-forfeited: booking rejected by owner in Cal.com."
        deposit.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Deposit pk=%s forfeited (rejected in Cal.com)", deposit.pk)


def _handle_booking_rescheduled(payload):
    """Update the deposit when a Cal.com booking is rescheduled."""
    from clients.models import Deposit

    booking_uid = payload.get("uid", "")
    reschedule_uid = payload.get("rescheduleUid", "")
    if not booking_uid:
        logger.info("BOOKING_RESCHEDULED webhook: no booking uid — skipping")
        return

    new_start = payload.get("startTime", "")
    new_date = _parse_appointment_date(new_start)
    new_title = payload.get("eventTitle", "") or payload.get("title", "")

    # The rescheduled booking gets a new UID; find the deposit by the old UID
    # Cal.com sends the *new* booking's uid in "uid" and sometimes the old one
    # in "rescheduleUid". Try the reschedule UID first (old booking), then new.
    deposit = None
    for uid in (reschedule_uid, booking_uid):
        if uid:
            try:
                deposit = Deposit.objects.get(cal_booking_uid=uid)
                break
            except Deposit.DoesNotExist:
                continue

    if deposit is None:
        logger.info("BOOKING_RESCHEDULED webhook: no deposit found for uid=%s / rescheduleUid=%s",
                     booking_uid, reschedule_uid)
        return

    update_fields = ["updated_at"]

    # Update the UID to the new booking's UID so future webhooks match
    if booking_uid and deposit.cal_booking_uid != booking_uid:
        deposit.cal_booking_uid = booking_uid
        update_fields.append("cal_booking_uid")

    if new_date and deposit.appointment_date != new_date:
        old_date = deposit.appointment_date
        deposit.appointment_date = new_date
        update_fields.append("appointment_date")
        deposit.notes = (deposit.notes or "") + (
            f"\nRescheduled: {old_date} → {new_date}."
        )
        update_fields.append("notes")

    if new_title and new_title != deposit.service_name:
        deposit.service_name = new_title
        update_fields.append("service_name")

    deposit.save(update_fields=update_fields)
    logger.info("Deposit pk=%s updated from BOOKING_RESCHEDULED (new uid=%s, date=%s)",
                deposit.pk, booking_uid, new_date)

    # Keep the Client record in sync with the latest appointment date
    if new_date and deposit.client:
        client = deposit.client
        if client.last_appointment_date != new_date:
            client.last_appointment_date = new_date
            client.save(update_fields=["last_appointment_date", "updated_at"])


@csrf_exempt
@require_POST
def calcom_webhook_view(request):
    """Receive and process Cal.com webhook events."""
    logger.warning("Cal.com webhook received (%d bytes)", len(request.body))

    if not _verify_signature(request):
        return JsonResponse({"error": "invalid signature"}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Cal.com webhook: invalid JSON body")
        return JsonResponse({"error": "invalid json"}, status=400)

    trigger = data.get("triggerEvent", "")
    payload = data.get("payload", {})
    logger.warning("Cal.com webhook trigger=%s", trigger)

    handlers = {
        "BOOKING_CREATED": _handle_booking_created,
        "BOOKING_REQUESTED": _handle_booking_created,
        "BOOKING_CONFIRMED": _handle_booking_confirmed,
        "BOOKING_CANCELLED": _handle_booking_cancelled,
        "BOOKING_REJECTED": _handle_booking_rejected,
        "BOOKING_RESCHEDULED": _handle_booking_rescheduled,
    }

    handler = handlers.get(trigger)
    if handler:
        try:
            handler(payload)
        except Exception:
            logger.exception("Error handling %s webhook", trigger)
    else:
        logger.warning("Ignoring Cal.com webhook trigger: %s", trigger)

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

    What happens when this runs:
      1. Finds all deposits still "pending" after 48 hours.
      2. Cancels their Cal.com bookings (frees the slot).
      3. Emails each client about the cancellation.
      4. Emails the owner a summary.
      5. Marks the deposits as "forfeited".

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

    count = expire_pending_deposits(hours=48)

    return JsonResponse({"ok": True, "forfeited": count})
