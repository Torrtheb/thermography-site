"""
Management command: backfill placeholder bookings for existing deposits.

Fixes a bug where each original booking only received ONE placeholder per
sibling event type, covering only the sibling's own duration. For a 90-minute
booking that's sold via a 30-minute sibling, this left the 4:30, 5:00 and
5:15 slots bookable on the sibling — the exact symptom reported for the
May 12 pending appointment.

This command walks every currently-active deposit (awaiting_review, pending,
received, confirmed, or waived) with a future appointment date, fetches the
original booking's start/end times from Cal.com, cancels the partial
placeholders that were created under the old logic, and recreates a full
set of placeholders using ``_create_placeholder_bookings`` so the entire
original time range is blocked on every sibling event type.

Usage:
    python manage.py backfill_placeholder_bookings              # dry run
    python manage.py backfill_placeholder_bookings --apply      # do it
    python manage.py backfill_placeholder_bookings --deposit-id 42 --apply

Safety:
  - Dry-run by default. Nothing is changed until ``--apply`` is passed.
  - Only touches Cal.com placeholder bookings and the PlaceholderBooking
    table. Client, Deposit, and ClientReport rows are never modified.
  - Re-running the command after success is a no-op (idempotent) because
    the old placeholders have already been cancelled.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


def _fetch_booking(uid):
    """Fetch a single Cal.com booking by UID via the v2 API.

    Returns a dict with at least ``startTime``, ``endTime``, ``eventTitle``
    fields on success, or None on failure. We use the 2024-06-14 API version
    because that's what the rest of the GET paths in ``webhooks.py`` already
    use.
    """
    api_key = getattr(settings, "CAL_API_KEY", "")
    if not api_key or not uid:
        return None

    url = f"https://api.cal.com/v2/bookings/{urllib.parse.quote(uid, safe='')}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "cal-api-version": "2024-08-13",
            "Accept": "application/json",
            "User-Agent": "ThermographyClinic/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        logger.warning("GET /v2/bookings/%s → HTTP %d: %s", uid, e.code, body)
        return None
    except Exception as exc:
        logger.warning("GET /v2/bookings/%s failed: %s", uid, exc)
        return None

    payload = data.get("data")
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return None

    return {
        "startTime": payload.get("start") or payload.get("startTime") or "",
        "endTime": payload.get("end") or payload.get("endTime") or "",
        "eventTitle": (
            payload.get("eventTypeTitle")
            or payload.get("title")
            or payload.get("eventTitle")
            or ""
        ),
        "eventTypeSlug": payload.get("eventTypeSlug") or payload.get("type") or "",
        "username": (
            (payload.get("organizer") or {}).get("username")
            or payload.get("username")
            or ""
        ),
    }


def _build_cal_url(username, slug):
    if not username or not slug:
        return ""
    return f"https://cal.com/{username}/{slug}"


class Command(BaseCommand):
    help = (
        "Rebuild placeholder bookings for active deposits so that multi-slot "
        "original bookings block every overlapping sibling slot (not just "
        "the first one)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually cancel the old placeholders and create new ones. "
                 "Without this flag the command only prints what it would do.",
        )
        parser.add_argument(
            "--deposit-id",
            type=int,
            default=None,
            help="Only process a single deposit by primary key (useful for "
                 "the known May 12 booking).",
        )
        parser.add_argument(
            "--include-past",
            action="store_true",
            help="Also process deposits whose appointment has already passed "
                 "(normally skipped because blocking past slots is pointless).",
        )
        parser.add_argument(
            "--include-confirmed",
            action="store_true",
            help="Also process deposits whose Cal.com booking is already "
                 "confirmed or waived. Cal.com's organizer conflict detection "
                 "naturally blocks sibling event types for confirmed bookings, "
                 "so placeholders are normally unnecessary for these and "
                 "Cal.com will simply reject the POSTs.",
        )

    def handle(self, *args, **options):
        from django.db.models import Q
        from clients.models import Deposit
        from booking.models import PlaceholderBooking
        from booking.webhooks import (
            cancel_placeholder_bookings,
            _create_placeholder_bookings,
            _infer_location_from_event,
        )

        apply = options["apply"]
        deposit_id = options["deposit_id"]
        include_past = options["include_past"]
        include_confirmed = options["include_confirmed"]

        # By default only target statuses where the Cal.com booking is still
        # in the "awaiting confirmation" state — those are the ones affected
        # by Cal.com bug #23069 (pending bookings don't block sibling event
        # types). Confirmed/waived bookings are blocked naturally by Cal.com
        # itself, so placeholder POSTs for them just return 400 "User
        # already has booking at this time" — noise, not progress.
        if include_confirmed:
            active_statuses = Q(status="awaiting_review") | Q(status="pending") \
                | Q(status="received") | Q(status="confirmed") | Q(status="waived")
        else:
            active_statuses = Q(status="awaiting_review") | Q(status="pending") \
                | Q(status="received")

        qs = Deposit.objects.filter(active_statuses).exclude(cal_booking_uid="")
        if deposit_id is not None:
            qs = qs.filter(pk=deposit_id)
        if not include_past:
            today = timezone.localdate()
            qs = qs.filter(appointment_date__gte=today)

        qs = qs.select_related("client").order_by("appointment_date", "pk")

        deposits = list(qs)
        if not deposits:
            self.stdout.write(self.style.SUCCESS(
                "No deposits needing placeholder backfill. "
                "Confirmed/waived bookings are blocked naturally by Cal.com — "
                "pass --include-confirmed to force-retry them anyway."
            ))
            return

        mode = "APPLY" if apply else "DRY-RUN"
        status_scope = "all statuses" if include_confirmed else "pending/awaiting_review/received"
        self.stdout.write(
            f"[{mode}] Found {len(deposits)} deposit(s) to evaluate ({status_scope}).\n"
        )

        processed = 0
        skipped = 0
        errors = 0

        for dep in deposits:
            header = (
                f"\nDeposit #{dep.pk} — {dep.client.name} — "
                f"{dep.appointment_date} — status={dep.status} — "
                f"cal_uid={dep.cal_booking_uid}"
            )
            self.stdout.write(header)

            booking = _fetch_booking(dep.cal_booking_uid)
            if not booking:
                self.stdout.write(self.style.WARNING(
                    "  ! Could not fetch booking from Cal.com — skipping."
                ))
                skipped += 1
                continue

            start_time = booking["startTime"]
            end_time = booking["endTime"]
            event_title = booking["eventTitle"] or dep.service_name
            booked_cal_url = _build_cal_url(booking["username"], booking["eventTypeSlug"])
            inferred_location = _infer_location_from_event(event_title, cal_url=booked_cal_url)

            existing_ph = list(
                PlaceholderBooking.objects.filter(original_booking_uid=dep.cal_booking_uid)
            )

            self.stdout.write(
                f"  start={start_time}  end={end_time}\n"
                f"  title={event_title!r}\n"
                f"  location={inferred_location!r}\n"
                f"  existing placeholders: {len(existing_ph)}"
            )

            if not start_time or not end_time:
                self.stdout.write(self.style.WARNING(
                    "  ! Missing startTime or endTime in Cal.com response — skipping."
                ))
                skipped += 1
                continue

            if not apply:
                self.stdout.write(
                    "  → Would cancel existing placeholders and recreate full coverage."
                )
                processed += 1
                continue

            try:
                cancel_placeholder_bookings(dep.cal_booking_uid)
                _create_placeholder_bookings(
                    dep.cal_booking_uid,
                    start_time,
                    event_title,
                    inferred_location,
                    booked_cal_url=booked_cal_url,
                    end_time=end_time,
                )
                new_count = PlaceholderBooking.objects.filter(
                    original_booking_uid=dep.cal_booking_uid
                ).count()
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ Recreated placeholders: {new_count} now tracked."
                ))
                processed += 1
            except Exception as exc:
                logger.exception("Backfill failed for deposit pk=%s", dep.pk)
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {exc}"))
                errors += 1

        summary = (
            f"\nProcessed={processed}  skipped={skipped}  errors={errors}  "
            f"mode={'APPLY' if apply else 'DRY-RUN'}"
        )
        if apply:
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.WARNING(
                summary + "\nRun again with --apply to make the changes."
            ))
