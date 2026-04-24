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
  72-hour expiry cron → cancels booking via Cal.com API + cancels placeholders

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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parseaddr
from zoneinfo import ZoneInfo

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

# Cal.com's burst rate limit kicks in around ~5–10 requests/second. When we
# hit it, we back off and retry so batch jobs (backfill, multi-placeholder
# creation) don't silently drop writes.
_CAL_RATE_LIMIT_MAX_RETRIES = 4
_CAL_RATE_LIMIT_BASE_DELAY_S = 2.0


def _calcom_api_post(path, body_dict=None, max_retries=_CAL_RATE_LIMIT_MAX_RETRIES):
    """
    Make an authenticated POST to the Cal.com v2 API.

    Automatically retries HTTP 429 (rate-limited) responses with exponential
    backoff, honouring a ``Retry-After`` header when present.

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

    attempts = max(1, max_retries)
    last_resp_body = ""
    last_code = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")[:2000]
                logger.info("Cal.com API %s → %d: %s", path, resp.status, resp_body[:200])
                return True, resp_body
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", errors="replace")[:500]
            last_resp_body = resp_body
            last_code = e.code

            if e.code == 429 and attempt < attempts - 1:
                retry_after_hdr = e.headers.get("Retry-After") if e.headers else None
                try:
                    retry_after = float(retry_after_hdr) if retry_after_hdr else None
                except (TypeError, ValueError):
                    retry_after = None
                delay = retry_after if retry_after and retry_after > 0 else (
                    _CAL_RATE_LIMIT_BASE_DELAY_S * (2 ** attempt)
                )
                logger.warning(
                    "Cal.com API %s rate-limited (attempt %d/%d) — sleeping %.1fs",
                    path, attempt + 1, attempts, delay,
                )
                time.sleep(delay)
                continue

            logger.warning("Cal.com API %s → HTTP %d: %s", path, e.code, resp_body)
            return False, f"HTTP {e.code}: {resp_body}"
        except Exception as exc:
            logger.warning("Cal.com API %s → exception: %s", path, exc)
            return False, str(exc)

    # Exhausted retries (429 loop)
    logger.warning(
        "Cal.com API %s → HTTP %s after %d retries: %s",
        path, last_code, attempts, last_resp_body,
    )
    return False, f"HTTP {last_code}: {last_resp_body}"


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
        {"cancellationReason": reason or "Booking deposit not received within 72 hours."},
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
# Cal.com's v2 /bookings endpoint validates the attendee email. Sending the
# RFC-5322 "Display Name <addr@host>" form produces an ``email_validation_error``
# — we must pass only the bare address. This fallback is used if
# ``DEFAULT_FROM_EMAIL`` is unset or malformed.
_PLACEHOLDER_EMAIL_FALLBACK = "noreply@cal.com"
# Minimal delay between consecutive placeholder POSTs to stay below Cal.com's
# burst rate limit when tiling many placeholders for a single booking.
_PLACEHOLDER_POST_DELAY_S = 0.25


def _placeholder_attendee_email():
    """Return a bare email address safe to send to Cal.com's v2 booking API.

    Strips any ``Display Name <addr@host>`` wrapper from ``DEFAULT_FROM_EMAIL``
    and falls back to a known-valid address if the parsed result is empty
    or missing an ``@``.
    """
    raw = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    _, addr = parseaddr(raw)
    addr = (addr or "").strip()
    if addr and "@" in addr:
        return addr
    return _PLACEHOLDER_EMAIL_FALLBACK


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


def _fetch_event_type_length_minutes(username, slug):
    """Return a Cal.com event type's duration in minutes, or None on failure.

    Needed so we can tile placeholder bookings across a sibling event type
    whose length may differ from the original booking's length. Without this,
    a single placeholder only blocks the sibling's own duration, which leaves
    the rest of the original booking's time range bookable on that sibling
    (see Cal.com bug #23069 and the multi-placeholder logic below).
    """
    if not username or not slug:
        return None

    ok, data = _calcom_api_get(
        "/v2/event-types",
        params={"username": username, "eventSlug": slug},
    )
    if not ok or not isinstance(data, dict):
        return None

    payload = data.get("data")

    # Cal.com has shipped a few response shapes over the years; handle the
    # common ones defensively so the fix doesn't silently break on upgrades.
    candidates = []
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("eventTypeGroups"), list):
            for group in payload["eventTypeGroups"]:
                if isinstance(group, dict) and isinstance(group.get("eventTypes"), list):
                    candidates.extend(group["eventTypes"])
        elif isinstance(payload.get("eventTypes"), list):
            candidates = payload["eventTypes"]
        else:
            candidates = [payload]

    for et in candidates:
        if not isinstance(et, dict):
            continue
        et_slug = et.get("slug")
        if et_slug and et_slug != slug:
            continue
        length = et.get("lengthInMinutes") or et.get("length")
        if isinstance(length, (int, float)) and length > 0:
            return int(length)

    logger.warning("Could not determine length for Cal.com event type %s/%s", username, slug)
    return None


def _parse_iso_datetime(iso_str):
    """Parse a Cal.com ISO timestamp into a timezone-aware UTC datetime, or None."""
    if not iso_str:
        return None
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _format_cal_iso(dt):
    """Format a UTC datetime as a Cal.com-compatible ISO string."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _compute_placeholder_starts(original_start_dt, original_end_dt, sibling_length_minutes):
    """Return the list of placeholder start datetimes (UTC) needed on one sibling.

    Strategy: place placeholders every `sibling_length_minutes` starting at
    `original_start_dt` while the placeholder's start is strictly before
    `original_end_dt`. Each placeholder occupies `sibling_length_minutes`,
    so adjacent placeholders tile without gaps across the original range.

    This is enough to block every sibling slot whose time span overlaps the
    original booking, because:
      - A candidate start T on the sibling makes [T, T+L) busy.
      - If T < original_end and T >= original_start, T falls inside a placeholder
        (or at its exact start), causing a conflict.
      - If T < original_start but T + L > original_start, the placeholder
        at original_start (covering [original_start, original_start+L)) overlaps it.

    If the sibling's length is unknown, we fall back to a single placeholder
    at the original start (preserving the previous, partial behaviour rather
    than failing open).
    """
    if original_start_dt is None:
        return []

    if (
        original_end_dt is None
        or original_end_dt <= original_start_dt
        or not sibling_length_minutes
        or sibling_length_minutes <= 0
    ):
        return [original_start_dt]

    starts = []
    current = original_start_dt
    step = timedelta(minutes=int(sibling_length_minutes))

    # Safety cap: a single booking should never need more than 96 placeholders
    # (24 hours in 15-minute steps). This protects us from a pathological
    # mis-parse or malicious payload that reports a multi-day booking.
    max_placeholders = 96

    while current < original_end_dt and len(starts) < max_placeholders:
        starts.append(current)
        current = current + step

    return starts


def _get_sibling_event_slugs(event_title, inferred_location, booked_cal_url=""):
    """Find Cal.com event slugs for other services at the same location.

    Uses the LocationServiceLink table — no API call needed.
    Returns a list of (username, event_slug) tuples, excluding the
    event type that matches the current booking.

    Identification of the "current" event type (to exclude):
      1. If booked_cal_url is provided, match by parsed (username, slug).
      2. Otherwise fall back to fuzzy title matching.
    """
    from booking.models import Location, LocationServiceLink

    if not inferred_location:
        return []

    location = Location.objects.filter(name=inferred_location).first()
    if not location:
        return []

    booked_user, booked_slug = _parse_cal_url(booked_cal_url) if booked_cal_url else (None, None)
    title_lower = (event_title or "").lower()

    siblings = []
    for link in LocationServiceLink.objects.filter(location=location).select_related("service"):
        username, slug = _parse_cal_url(link.cal_booking_url)
        if not username or not slug:
            continue

        # Exclude the event type that was just booked
        if booked_user and booked_slug:
            if username == booked_user and slug == booked_slug:
                continue
        else:
            svc_lower = link.service.title.lower()
            if svc_lower in title_lower or title_lower in svc_lower:
                continue

        siblings.append((username, slug))

    return siblings


def _create_placeholder_bookings(
    booking_uid,
    start_time,
    event_title,
    inferred_location,
    booked_cal_url="",
    end_time="",
):
    """Create placeholder bookings on sibling event types to block the time slot.

    Called synchronously from the webhook handler so slots are blocked
    before the HTTP response is returned (prevents race-condition
    double-booking if another client loads the calendar immediately).

    Because each sibling event type may have a DIFFERENT length than the
    original booking, a single placeholder at the original start only blocks
    the sibling's own duration. For a 90-minute original booking and a
    30-minute sibling, a single placeholder at 4:00pm would leave 4:30,
    5:00, and 5:15 bookable on the sibling. To close that hole, we tile
    placeholders across the entire original time range for each sibling,
    using that sibling's own length as the step size.

    If ``end_time`` is not provided we fall back to a single placeholder at
    the start (pre-fix behaviour), which protects short single-slot bookings
    but does not fully cover multi-slot ones.
    """
    from booking.models import PlaceholderBooking

    if not booking_uid or not start_time:
        return

    siblings = _get_sibling_event_slugs(event_title, inferred_location, booked_cal_url=booked_cal_url)
    if not siblings:
        logger.info("No sibling event types found for '%s' — no placeholders needed", event_title)
        return

    original_start_dt = _parse_iso_datetime(start_time)
    original_end_dt = _parse_iso_datetime(end_time) if end_time else None

    if original_start_dt is None:
        logger.warning(
            "Could not parse startTime=%r for booking %s — skipping placeholder creation",
            start_time, booking_uid,
        )
        return

    placeholder_email = _placeholder_attendee_email()

    created_count = 0
    first_post = True
    for username, slug in siblings:
        sibling_length = _fetch_event_type_length_minutes(username, slug)
        placeholder_starts = _compute_placeholder_starts(
            original_start_dt, original_end_dt, sibling_length,
        )

        if original_end_dt is None:
            logger.warning(
                "No endTime available for booking %s; placing single placeholder on %s/%s "
                "(may leave later slots bookable on this sibling)",
                booking_uid, username, slug,
            )
        elif sibling_length is None:
            logger.warning(
                "Could not fetch length for %s/%s; placing single placeholder "
                "(may leave later slots bookable on this sibling)",
                username, slug,
            )

        for ph_start_dt in placeholder_starts:
            ph_start_iso = _format_cal_iso(ph_start_dt)
            body = {
                "start": ph_start_iso,
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

            if not first_post:
                time.sleep(_PLACEHOLDER_POST_DELAY_S)
            first_post = False

            ok, resp_body = _calcom_api_post("/v2/bookings", body)
            if not ok:
                # Some placeholder slots may be outside the sibling's schedule
                # (e.g. the tail end of a pop-up clinic's hours) — Cal.com
                # rejects those and we simply skip; the slot wasn't bookable
                # there anyway.
                logger.warning(
                    "Failed to create placeholder on %s/%s at %s for booking %s: %s",
                    username, slug, ph_start_iso, booking_uid, resp_body,
                )
                continue

            try:
                resp_data = json.loads(resp_body) if isinstance(resp_body, str) else resp_body
                ph_uid = resp_data.get("data", {}).get("uid", "")
            except (json.JSONDecodeError, AttributeError):
                resp_data = {}
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
                logger.warning(
                    "Placeholder booking on %s/%s at %s returned no UID",
                    username, slug, ph_start_iso,
                )

    logger.info(
        "Created %d placeholder booking(s) for original uid=%s at %s (range %s → %s)",
        created_count, booking_uid, inferred_location, start_time, end_time or "?",
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


_PLACEHOLDER_BLOCKING_STATUSES = frozenset({
    "awaiting_review",  # owner hasn't reviewed the new booking yet
    "pending",          # deposit request sent, awaiting payment
    "received",         # deposit paid, awaiting confirmation
    "confirmed",        # fully confirmed — still holds the slot
    "waived",           # fee waived but slot still reserved
})


def cleanup_stale_placeholders(max_age_hours=None):
    """Cancel orphaned placeholder bookings.

    A placeholder is "orphaned" when its original booking is no longer
    expected to hold a slot — i.e. no Deposit row with that cal_booking_uid
    exists, or the deposit's status is ``forfeited`` / ``applied`` /
    ``refunded``. Orphans can accumulate if a BOOKING_CANCELLED or
    BOOKING_REJECTED webhook is missed or malformed.

    An active future booking (awaiting_review, pending, received, confirmed,
    waived) keeps its placeholders indefinitely. This is a behaviour change
    from the previous 96-hour age cutoff, which incorrectly cancelled valid
    placeholders for any booking more than ~4 days in the future and left
    sibling event types bookable during those slots.

    To avoid racing with in-flight BOOKING_REQUESTED webhooks we skip
    placeholders created in the last hour — if a deposit row hasn't been
    written yet, the placeholder would look orphaned.

    ``max_age_hours`` is accepted for backwards compatibility with the
    existing cron endpoint and ignored.
    """
    from django.utils import timezone as tz
    from booking.models import PlaceholderBooking
    from clients.models import Deposit

    del max_age_hours  # accepted for compatibility; unused

    min_age_cutoff = tz.now() - tz.timedelta(hours=1)
    candidates = list(
        PlaceholderBooking.objects.filter(created_at__lt=min_age_cutoff)
    )
    if not candidates:
        return 0

    original_uids = {p.original_booking_uid for p in candidates if p.original_booking_uid}

    active_uids = set(
        Deposit.objects
        .filter(cal_booking_uid__in=original_uids, status__in=_PLACEHOLDER_BLOCKING_STATUSES)
        .values_list("cal_booking_uid", flat=True)
    ) if original_uids else set()

    orphans = [p for p in candidates if p.original_booking_uid not in active_uids]
    if not orphans:
        return 0

    for ph in orphans:
        cancel_calcom_booking(
            ph.placeholder_booking_uid,
            reason="Orphaned slot hold — original booking no longer active.",
        )
        ph.delete()

    logger.info(
        "Cleaned up %d orphaned placeholder booking(s) (original booking resolved or missing)",
        len(orphans),
    )
    return len(orphans)


# ──────────────────────────────────────────────────────────
# Deposit expiry warning — 24 hours before cancellation
# ──────────────────────────────────────────────────────────

def send_deposit_expiry_warnings(hours=48):
    """
    Send a warning email to clients whose deposits have been pending for
    `hours` (default 48) but not yet expired.

    Only targets "pending" deposits (where the client has received the
    deposit request but hasn't paid). Skips deposits where the warning
    has already been sent.

    Returns the number of warning emails sent.
    """
    from django.db.models import F, Q
    from django.db.models.functions import Coalesce
    from django.utils import timezone as tz
    from clients.models import Deposit
    from clients.email import send_deposit_expiry_warning

    cutoff = tz.now() - tz.timedelta(hours=hours)

    warn_qs = Deposit.objects.filter(
        status="pending",
        expiry_warning_sent=False,
    ).annotate(
        timer_start=Coalesce(F("approved_at"), F("created_at")),
    ).filter(
        timer_start__lt=cutoff,
    ).select_related("client")

    warn_list = list(warn_qs)
    if not warn_list:
        return 0

    sent = 0
    for deposit in warn_list:
        date_str = deposit.appointment_date.strftime("%B %d, %Y") if deposit.appointment_date else ""
        try:
            send_deposit_expiry_warning(
                deposit.client,
                deposit.amount,
                appointment_date=date_str,
                service_name=deposit.service_name,
            )
            deposit.expiry_warning_sent = True
            deposit.save(update_fields=["expiry_warning_sent", "updated_at"])
            sent += 1
        except Exception:
            logger.exception("Failed to send expiry warning for deposit pk=%s", deposit.pk)

    logger.info("Sent %d deposit expiry warning(s) (>%d hours pending)", sent, hours)
    return sent


# ──────────────────────────────────────────────────────────
# Shared expiry logic — used by both cron endpoint and management command
# ──────────────────────────────────────────────────────────

def expire_pending_deposits(hours=72):
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
                    reason="Booking expired — not reviewed within 72 hours.",
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
    """Parse a Cal.com startTime ISO string into a local-timezone date.

    Cal.com sends startTime in UTC (e.g. "2026-04-10T01:00:00.000Z").
    Naive slicing of the first 10 chars would yield the UTC calendar date,
    which can be a day ahead of the actual appointment date in Pacific time
    for evening bookings.  Convert to America/Vancouver first.
    """
    if not start_time_str:
        return None
    try:
        cleaned = start_time_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo(_PLACEHOLDER_TIMEZONE))
        return local_dt.date()
    except (ValueError, TypeError):
        return None


_LOCATION_NOISE_WORDS = frozenset({
    "main", "clinic", "pop-up", "popup", "the", "a", "an", "and", "at", "in",
    "of", "for", "our", "satellite", "office", "location", "branch", "centre",
    "center", "studio", "room",
})


def _infer_location_from_cal_url(cal_url):
    """Try to match a Cal.com event-type URL to a Location via LocationServiceLink.

    More reliable than title matching because it uses the exact URL stored
    in the database. Returns the Location.name string if matched, or "".
    """
    if not cal_url:
        return ""
    try:
        from booking.models import LocationServiceLink
        link = (
            LocationServiceLink.objects
            .filter(cal_booking_url=cal_url)
            .select_related("location")
            .first()
        )
        if link:
            return link.location.name
    except Exception:
        logger.debug("Could not look up location from Cal URL", exc_info=True)
    return ""


def _infer_location_from_event(event_title, cal_url=""):
    """Try to match a Cal.com event to a Location name.

    Matching strategy (most reliable first):
      0. Exact Cal.com URL lookup via LocationServiceLink (if provided).
      1. Full location name found as a substring in the event title.
      2. Significant tokens extracted from each location name (ignoring
         generic words like "Main", "Clinic", "Pop-Up") checked as
         substrings of the event title.  Locations with more matching
         tokens win; ties broken by longest name first.

    Returns the Location.name string if matched, or "" if no match.
    """
    # Pass 0: exact URL match (most reliable)
    if cal_url:
        loc_name = _infer_location_from_cal_url(cal_url)
        if loc_name:
            return loc_name

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



def _extract_cal_url_from_payload(payload):
    """Extract the Cal.com event-type URL from a webhook payload.

    Cal.com includes event type metadata in various payload shapes.
    Try common fields that contain the event-type slug or URL.
    """
    # Some payloads include the full event URL
    for key in ("eventTypeUrl", "calEventUrl", "bookingUrl"):
        val = (payload.get(key) or "").strip()
        if val and "cal.com" in val:
            return val

    # Build from slug + organizer username if available
    slug = payload.get("eventTypeSlug", "") or ""
    organizer = payload.get("organizer", {}) or {}
    username = organizer.get("username", "") or ""
    if slug and username:
        return f"https://cal.com/{username}/{slug}"

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

    For BOOKING_REQUESTED events, creates placeholder bookings on
    sibling event types at the same location to prevent double-booking.
    Placeholders are created synchronously to eliminate the race-condition
    window that allowed double-booking.
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
    end_time = payload.get("endTime", "")
    event_title = payload.get("eventTitle", "") or payload.get("title", "")
    appointment_date = _parse_appointment_date(start_time)
    booked_cal_url = _extract_cal_url_from_payload(payload)

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
            # Intentionally NOT cancelling placeholders here: the original
            # booking is still active (now confirmed), and Cal.com's
            # cross-event-type blocking bug means the confirmed booking
            # doesn't block slots on sibling event types. Keep the placeholders
            # alive until the booking is cancelled, rejected, or forfeited.
            return

    # Infer location — try Cal.com URL first (most reliable), then event title
    inferred_location = _infer_location_from_event(event_title, cal_url=booked_cal_url)
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

    # Block sibling event types SYNCHRONOUSLY before sending any emails
    # or returning the webhook response. This eliminates the race-condition
    # window where another client could book the same slot.
    if trigger_event == "BOOKING_REQUESTED" and booking_uid and start_time:
        try:
            _create_placeholder_bookings(
                booking_uid, start_time, event_title, inferred_location,
                booked_cal_url=booked_cal_url, end_time=end_time,
            )
        except Exception:
            logger.exception(
                "Failed to create placeholder bookings for uid=%s — "
                "double-booking risk until placeholders are created manually or by cron",
                booking_uid,
            )

    # Notify the owner so they know to review and approve (background — non-critical)
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
        deposit.notes = (deposit.notes or "") + "\nDeposit confirmed — booking confirmed in Cal.com."
        deposit.save(update_fields=["status", "deposit_confirmed_sent", "notes", "updated_at"])
        logger.info("Deposit pk=%s → confirmed (via Cal.com webhook)", deposit.pk)

    # Intentionally NOT cancelling placeholders here: the confirmed booking
    # still needs to block its slot on sibling event types, and Cal.com does
    # not propagate cross-event-type busy status even for confirmed bookings
    # (Cal.com bug #23069). Placeholders are released only when the booking
    # is cancelled, rejected, rescheduled, or the deposit is forfeited.


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

    cancel_placeholder_bookings(booking_uid)


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

    cancel_placeholder_bookings(booking_uid)


def _handle_booking_rescheduled(payload):
    """Update the deposit when a Cal.com booking is rescheduled."""
    from clients.models import Deposit

    booking_uid = payload.get("uid", "")
    reschedule_uid = payload.get("rescheduleUid", "")
    if not booking_uid:
        logger.info("BOOKING_RESCHEDULED webhook: no booking uid — skipping")
        return

    new_start = payload.get("startTime", "")
    new_end = payload.get("endTime", "")
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
        cancel_placeholder_bookings(old_uid)
    if booking_uid and new_start:
        booked_cal_url = _extract_cal_url_from_payload(payload)
        inferred_location = _infer_location_from_event(new_title, cal_url=booked_cal_url)
        try:
            _create_placeholder_bookings(
                booking_uid, new_start, new_title, inferred_location,
                booked_cal_url=booked_cal_url, end_time=new_end,
            )
        except Exception:
            logger.exception(
                "Failed to create placeholder bookings for rescheduled uid=%s",
                booking_uid,
            )


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
    HTTP-callable endpoint for the 72-hour deposit expiry rule.

    Protected by CRON_SECRET — an external cron service (e.g. cron-job.org)
    POSTs to this URL every hour with the secret in the Authorization header.

    What happens when this runs:
      1. Sends a warning email to clients whose deposits have been pending
         for 48 hours (24 hours before the 72-hour cancellation).
      2. Finds all deposits still "pending" after 72 hours.
      3. Cancels their Cal.com bookings (frees the slot).
      4. Emails each client about the cancellation.
      5. Emails the owner a summary.
      6. Marks the deposits as "forfeited".

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

    warn_count = send_deposit_expiry_warnings(hours=48)
    count = expire_pending_deposits(hours=72)
    stale = cleanup_stale_placeholders(max_age_hours=96)

    return JsonResponse({
        "ok": True, "warnings_sent": warn_count,
        "forfeited": count, "stale_placeholders_cleaned": stale,
    })
