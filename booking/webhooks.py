"""
Cal.com webhook handler — bidirectional sync between Cal.com and Wagtail.
Cal.com API integration — confirm, decline, and cancel bookings.

Handled webhook events:
  BOOKING_REQUESTED → creates Client + Deposit (awaiting_review)
                      + creates placeholder bookings on sibling event types
                        to prevent cross-service double-booking
  BOOKING_CREATED   → creates deposit for new bookings, OR confirms existing
                      deposit when owner confirms a requested booking in Cal.com
                      + cancels placeholder bookings (slot now confirmed)
  BOOKING_CANCELLED → forfeits the deposit + cancels placeholders
  BOOKING_REJECTED  → forfeits the deposit + cancels placeholders
  BOOKING_RESCHEDULED → updates deposit date and booking UID
                        + cancels old placeholders, creates new ones

Wagtail → Cal.com actions:
  "Approve & Send" → sends deposit request email (no Cal.com API call needed)
  "Mark Received & Confirm" → confirms booking via Cal.com API + cancels placeholders
  "Reject & Cancel" → declines booking via Cal.com API + cancels placeholders
  48-hour expiry cron → cancels booking via Cal.com API + cancels placeholders

Cross-event-type slot blocking:
  Cal.com has a known bug (#23069) where unconfirmed bookings only block
  slots within the same event type. To work around this, when a
  BOOKING_REQUESTED webhook arrives, we create placeholder bookings on all
  sibling event types at the same location for the same time slot. These
  are automatically cancelled when the original booking is resolved.

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
import threading
import urllib.error
import urllib.parse
import urllib.request
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
            resp_body = resp.read().decode("utf-8", errors="replace")[:2000]
            logger.info("Cal.com API %s → %d: %s", path, resp.status, resp_body[:200])
            return True, resp_body
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Cal.com API %s → HTTP %d: %s", path, e.code, resp_body)
        return False, f"HTTP {e.code}: {resp_body}"
    except Exception as exc:
        logger.warning("Cal.com API %s → exception: %s", path, exc)
        return False, str(exc)


def _calcom_api_get(path, params=None):
    """
    Make an authenticated GET to the Cal.com v2 API.

    Returns (success: bool, parsed_json: dict | None).
    """
    api_key = getattr(settings, "CAL_API_KEY", "")
    if not api_key:
        logger.warning("CAL_API_KEY not configured — cannot call %s", path)
        return False, None

    if not path.startswith("/v2/"):
        logger.error("Rejecting Cal.com API call to unexpected path: %s", path)
        return False, None

    url = f"https://api.cal.com{path}"
    if params:
        url += "?" + "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in params.items())

    headers = {
        "Authorization": f"Bearer {api_key}",
        "cal-api-version": "2024-06-14",
        "User-Agent": "ThermographyClinic/1.0",
        "Accept": "application/json",
    }

    req = urllib.request.Request(url, method="GET", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(resp_body)
            return True, data
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Cal.com API GET %s → HTTP %d: %s", path, e.code, resp_body)
        return False, None
    except Exception as exc:
        logger.warning("Cal.com API GET %s → exception: %s", path, exc)
        return False, None


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
# Cross-event-type slot blocking via placeholder bookings
# ──────────────────────────────────────────────────────────

_PLACEHOLDER_ATTENDEE_NAME = "SLOT HOLD"
_PLACEHOLDER_TIMEZONE = "America/Vancouver"


def _parse_cal_url(cal_booking_url):
    """Extract (username, event_slug) from a Cal.com URL.

    Expects URLs like https://cal.com/username/event-slug
    Returns (username, event_slug) or (None, None) on failure.
    """
    if not cal_booking_url:
        return None, None
    try:
        path = urllib.parse.urlparse(cal_booking_url).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return None, None


def _get_sibling_event_slugs(event_title, inferred_location):
    """Find Cal.com event slugs for other services at the same location.

    Uses the LocationServiceLink table — no API call needed.
    Returns a list of (username, event_slug) tuples, excluding the
    event type that matches the current booking's event title.
    """
    from booking.models import Location, LocationServiceLink

    if not inferred_location:
        return []

    location = Location.objects.filter(name=inferred_location).first()
    if not location:
        return []

    title_lower = (event_title or "").lower()
    siblings = []
    for link in LocationServiceLink.objects.filter(location=location).select_related("service"):
        username, slug = _parse_cal_url(link.cal_booking_url)
        if not username or not slug:
            continue
        if link.service.title.lower() in title_lower or title_lower in link.service.title.lower():
            continue
        siblings.append((username, slug))

    return siblings


def _create_placeholder_bookings(booking_uid, start_time, event_title, inferred_location):
    """Create placeholder bookings on sibling event types to block the time slot.

    Called in a background thread from the BOOKING_REQUESTED handler.
    """
    from booking.models import PlaceholderBooking

    if not booking_uid or not start_time:
        return

    siblings = _get_sibling_event_slugs(event_title, inferred_location)
    if not siblings:
        logger.info("No sibling event types found for '%s' — no placeholders needed", event_title)
        return

    placeholder_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")

    created_count = 0
    for username, slug in siblings:
        body = {
            "start": start_time,
            "eventTypeSlug": slug,
            "username": username,
            "attendee": {
                "name": _PLACEHOLDER_ATTENDEE_NAME,
                "email": placeholder_email,
                "timeZone": _PLACEHOLDER_TIMEZONE,
                "language": "en",
            },
            "metadata": {
                "placeholder": "true",
                "originalBookingUid": booking_uid,
            },
        }

        ok, resp_body = _calcom_api_post("/v2/bookings", body)
        if not ok:
            logger.warning(
                "Failed to create placeholder on %s/%s for booking %s: %s",
                username, slug, booking_uid, resp_body,
            )
            continue

        try:
            resp_data = json.loads(resp_body) if isinstance(resp_body, str) else resp_body
            ph_uid = resp_data.get("data", {}).get("uid", "")
        except (json.JSONDecodeError, AttributeError):
            ph_uid = ""

        if ph_uid:
            PlaceholderBooking.objects.create(
                original_booking_uid=booking_uid,
                placeholder_booking_uid=ph_uid,
            )
            created_count += 1

            ph_status = resp_data.get("data", {}).get("status", "")
            if ph_status == "pending":
                confirm_calcom_booking(ph_uid)
        else:
            logger.warning("Placeholder booking on %s/%s returned no UID", username, slug)

    logger.info(
        "Created %d placeholder booking(s) for original uid=%s at %s",
        created_count, booking_uid, inferred_location,
    )


def cancel_placeholder_bookings(original_booking_uid):
    """Cancel all placeholder bookings for the given original booking UID.

    Called when the original booking is confirmed, cancelled, rejected,
    or expires. Safe to call multiple times.
    """
    from booking.models import PlaceholderBooking

    placeholders = list(
        PlaceholderBooking.objects.filter(original_booking_uid=original_booking_uid)
    )
    if not placeholders:
        return

    for ph in placeholders:
        cancel_calcom_booking(
            ph.placeholder_booking_uid,
            reason="Slot hold released — original booking resolved.",
        )
        ph.delete()

    logger.info(
        "Cancelled %d placeholder booking(s) for original uid=%s",
        len(placeholders), original_booking_uid,
    )


def cleanup_stale_placeholders(max_age_hours=72):
    """Cancel placeholder bookings older than max_age_hours.

    Safety net for orphaned placeholders (e.g. webhook delivery failures).
    Called from the cron endpoint alongside deposit expiry.
    """
    from django.utils import timezone as tz
    from booking.models import PlaceholderBooking

    cutoff = tz.now() - tz.timedelta(hours=max_age_hours)
    stale = list(PlaceholderBooking.objects.filter(created_at__lt=cutoff))
    if not stale:
        return 0

    for ph in stale:
        cancel_calcom_booking(
            ph.placeholder_booking_uid,
            reason="Slot hold expired — automatic cleanup.",
        )
        ph.delete()

    logger.info("Cleaned up %d stale placeholder booking(s)", len(stale))
    return len(stale)


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

        # 1. Cancel/decline the Cal.com booking and release placeholder holds
        if deposit.cal_booking_uid:
            if was_awaiting:
                decline_calcom_booking(
                    deposit.cal_booking_uid,
                    reason="Booking expired — not reviewed within 48 hours.",
                )
            else:
                cancel_calcom_booking(deposit.cal_booking_uid)
            cancel_placeholder_bookings(deposit.cal_booking_uid)

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


def _get_deposit_amount(location_name=""):
    """Fetch the deposit amount — location override first, then global default.

    If the inferred location has a deposit_amount set, use it.
    Otherwise fall back to the global deposit_amount in SiteSettings.
    """
    if location_name:
        try:
            from booking.models import Location
            loc = Location.objects.filter(name=location_name).first()
            if loc and loc.deposit_amount is not None:
                logger.info(
                    "Using per-location deposit $%s for '%s'",
                    loc.deposit_amount, location_name,
                )
                return loc.deposit_amount
        except Exception:
            pass

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


_LOCATION_NOISE_WORDS = frozenset({
    "main", "clinic", "pop-up", "popup", "the", "a", "an", "and", "at", "in",
    "of", "for", "our", "satellite", "office", "location", "branch", "centre",
    "center", "studio", "room",
})


def _infer_location_from_event(event_title):
    """Try to match a Cal.com event title to a Location name.

    Cal.com event types are typically named like
    "Upper Body Assessments Campbell River" or
    "Breast Screening — Victoria Pop-Up".

    Matching strategy (most specific first):
      1. Full location name found as a substring in the event title.
      2. Significant tokens extracted from each location name (ignoring
         generic words like "Main", "Clinic", "Pop-Up") checked as
         substrings of the event title.  Locations with more matching
         tokens win; ties broken by longest name first.

    Returns the Location.name string if matched, or "" if no match.
    """
    if not event_title:
        return ""
    try:
        from booking.models import Location
        title_lower = event_title.lower()
        locations = list(Location.objects.all())
        locations.sort(key=lambda loc: len(loc.name), reverse=True)

        # Pass 1: exact full-name substring
        for loc in locations:
            if loc.name.lower() in title_lower:
                return loc.name

        # Pass 2: significant-token matching
        best, best_score = None, 0
        for loc in locations:
            tokens = [
                t for t in loc.name.lower().replace("—", " ").replace("-", " ").split()
                if t not in _LOCATION_NOISE_WORDS and len(t) > 1
            ]
            if not tokens:
                continue
            score = sum(1 for t in tokens if t in title_lower)
            if score > best_score:
                best, best_score = loc, score

        if best and best_score > 0:
            logger.debug(
                "Location inferred by token match: '%s' (score=%d) from '%s'",
                best.name, best_score, event_title,
            )
            return best.name

    except Exception:
        logger.debug("Could not look up location from event title", exc_info=True)
    return ""



def _handle_booking_created(payload, trigger_event="BOOKING_CREATED"):
    """Auto-create a Client (or find existing) and Deposit in 'awaiting_review' status.

    The deposit request email is NOT sent automatically — the owner must
    review the client info in Wagtail admin and click "Approve & Send
    Deposit Request" to validate the client and trigger the email.

    Auto-populates on the Client record (only when real data is available):
      - last_appointment_date  (from startTime)
      - clinic_location        (inferred from eventTitle ↔ Location names)
      - previous_visit_reason  (set to the Cal.com event title)

    For BOOKING_REQUESTED events, also creates placeholder bookings on
    sibling event types at the same location to prevent double-booking.
    """
    from clients.models import Client, Deposit

    # Skip webhooks fired for our own placeholder bookings to avoid infinite loops
    metadata = payload.get("metadata", {}) or {}
    if metadata.get("placeholder") == "true":
        logger.info("Skipping webhook for placeholder booking uid=%s", payload.get("uid", ""))
        return

    attendees = payload.get("attendees", [])
    if not attendees:
        logger.info("BOOKING_CREATED webhook: no attendees — skipping")
        return

    attendee = attendees[0]
    client_email = attendee.get("email", "").strip()
    client_name = attendee.get("name", "").strip()

    if client_name == _PLACEHOLDER_ATTENDEE_NAME:
        logger.info("Skipping webhook for placeholder booking (attendee name match)")
        return

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

    if booking_uid:
        try:
            existing = Deposit.objects.get(cal_booking_uid=booking_uid)
        except Deposit.DoesNotExist:
            existing = None

        if existing is not None:
            # BOOKING_CREATED fires after owner confirms a BOOKING_REQUESTED booking.
            # Transition the existing deposit to "confirmed" if it's still pre-confirmation.
            if existing.status in ("awaiting_review", "pending", "received"):
                existing.status = "confirmed"
                existing.deposit_confirmed_sent = True
                existing.notes = (existing.notes or "") + "\nDeposit confirmed — booking confirmed in Cal.com."
                existing.save(update_fields=["status", "deposit_confirmed_sent", "notes", "updated_at"])
                logger.info("Deposit pk=%s → confirmed (owner confirmed in Cal.com, BOOKING_CREATED)", existing.pk)
            else:
                logger.info("BOOKING_CREATED webhook: deposit already exists for uid=%s (status=%s)", booking_uid, existing.status)
            threading.Thread(
                target=cancel_placeholder_bookings, args=(booking_uid,), daemon=True,
            ).start()
            return

    # Infer location from the event title; use the title itself as the visit reason
    inferred_location = _infer_location_from_event(event_title)
    visit_reason = event_title.strip() if event_title else ""

    # Find existing client by email hash (O(1) indexed lookup)
    client = Client.find_by_email(client_email)

    if client is None:
        create_kwargs = {"name": client_name, "email": client_email}
        if appointment_date:
            create_kwargs["last_appointment_date"] = appointment_date
        if inferred_location:
            create_kwargs["clinic_location"] = inferred_location
        if visit_reason:
            create_kwargs["previous_visit_reason"] = visit_reason

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
        if visit_reason and visit_reason != client.previous_visit_reason:
            client.previous_visit_reason = visit_reason
            update_fields.append("previous_visit_reason")

        if len(update_fields) > 1:
            client.save(update_fields=update_fields)
            logger.info(
                "Updated client pk=%s from new booking: %s",
                client.pk, ", ".join(f for f in update_fields if f != "updated_at"),
            )

    deposit_amount = _get_deposit_amount(location_name=inferred_location)

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

    # Block sibling event types at the same location to prevent double-booking.
    # Only for BOOKING_REQUESTED (pending confirmation) — not for instantly
    # confirmed bookings, which Cal.com handles natively.
    if trigger_event == "BOOKING_REQUESTED" and booking_uid and start_time:
        threading.Thread(
            target=_create_placeholder_bookings,
            args=(booking_uid, start_time, event_title, inferred_location),
            daemon=True,
        ).start()


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
        deposit.notes = (deposit.notes or "") + "\nDeposit confirmed — booking confirmed in Cal.com."
        deposit.save(update_fields=["status", "deposit_confirmed_sent", "notes", "updated_at"])
        logger.info("Deposit pk=%s → confirmed (via Cal.com webhook)", deposit.pk)

    threading.Thread(
        target=cancel_placeholder_bookings, args=(booking_uid,), daemon=True,
    ).start()


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
        "confirmed": "client cancelled after deposit was confirmed",
        "waived": "client cancelled after fee was waived",
    }
    reason = reason_map.get(deposit.status)
    if reason:
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + f"\nAuto-forfeited: {reason}."
        deposit.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Deposit pk=%s forfeited (%s)", deposit.pk, reason)

    threading.Thread(
        target=cancel_placeholder_bookings, args=(booking_uid,), daemon=True,
    ).start()


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

    if deposit.status in ("awaiting_review", "pending", "received", "confirmed", "waived"):
        deposit.status = "forfeited"
        deposit.notes = (deposit.notes or "") + "\nAuto-forfeited: booking rejected by owner in Cal.com."
        deposit.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Deposit pk=%s forfeited (rejected in Cal.com)", deposit.pk)

    threading.Thread(
        target=cancel_placeholder_bookings, args=(booking_uid,), daemon=True,
    ).start()


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

    old_uid = reschedule_uid or deposit.cal_booking_uid
    deposit.save(update_fields=update_fields)
    logger.info("Deposit pk=%s updated from BOOKING_RESCHEDULED (new uid=%s, date=%s)",
                deposit.pk, booking_uid, new_date)

    # Keep the Client record in sync with the latest appointment date
    if new_date and deposit.client:
        client = deposit.client
        if client.last_appointment_date != new_date:
            client.last_appointment_date = new_date
            client.save(update_fields=["last_appointment_date", "updated_at"])

    # Cancel old placeholders and create new ones for the new time slot
    if old_uid:
        threading.Thread(
            target=cancel_placeholder_bookings, args=(old_uid,), daemon=True,
        ).start()
    if booking_uid and new_start:
        inferred_location = _infer_location_from_event(new_title)
        threading.Thread(
            target=_create_placeholder_bookings,
            args=(booking_uid, new_start, new_title, inferred_location),
            daemon=True,
        ).start()


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
            if handler is _handle_booking_created:
                handler(payload, trigger_event=trigger)
            else:
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
    stale = cleanup_stale_placeholders(max_age_hours=72)

    return JsonResponse({"ok": True, "forfeited": count, "stale_placeholders_cleaned": stale})
