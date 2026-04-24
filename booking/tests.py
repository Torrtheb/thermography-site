"""
Tests for the Cal.com cross-event-type slot blocking logic.

Covers the bug where a 90-minute booking on one event type only produced
a single short placeholder on sibling event types, leaving the rest of
the original time range bookable on those siblings.
"""

import json
import urllib.error
from datetime import datetime, timezone
from unittest import mock

from django.test import SimpleTestCase, TestCase

from booking.webhooks import (
    _calcom_api_post,
    _compute_placeholder_starts,
    _fetch_event_type_length_minutes,
    _format_cal_iso,
    _parse_iso_datetime,
    _placeholder_attendee_email,
)


class ComputePlaceholderStartsTests(SimpleTestCase):
    """The heart of the fix: tiling placeholders across the original range."""

    def setUp(self):
        # Original booking: 4:00pm → 5:30pm local = 90 minutes.
        # Use UTC throughout so the test doesn't depend on local timezone.
        self.start = datetime(2026, 5, 12, 23, 0, 0, tzinfo=timezone.utc)
        self.end = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)

    def test_thirty_minute_sibling_produces_three_placeholders(self):
        """90-min original + 30-min sibling → placeholders at :00, :30, :00."""
        starts = _compute_placeholder_starts(self.start, self.end, 30)
        self.assertEqual(len(starts), 3)
        self.assertEqual(starts[0], self.start)
        self.assertEqual(
            starts[1], datetime(2026, 5, 12, 23, 30, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            starts[2], datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc),
        )

    def test_sixty_minute_sibling_produces_two_placeholders(self):
        """90-min original + 60-min sibling → placeholders at :00 and +60."""
        starts = _compute_placeholder_starts(self.start, self.end, 60)
        self.assertEqual(len(starts), 2)
        self.assertEqual(starts[0], self.start)
        self.assertEqual(
            starts[1], datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc),
        )

    def test_sibling_longer_than_original_produces_single_placeholder(self):
        """30-min original + 60-min sibling → one placeholder at start."""
        short_end = self.start.replace(hour=23, minute=30)
        starts = _compute_placeholder_starts(self.start, short_end, 60)
        self.assertEqual(starts, [self.start])

    def test_equal_length_produces_single_placeholder(self):
        """30-min original + 30-min sibling → one placeholder at start."""
        short_end = self.start.replace(hour=23, minute=30)
        starts = _compute_placeholder_starts(self.start, short_end, 30)
        self.assertEqual(starts, [self.start])

    def test_missing_end_time_falls_back_to_single_placeholder(self):
        starts = _compute_placeholder_starts(self.start, None, 30)
        self.assertEqual(starts, [self.start])

    def test_missing_sibling_length_falls_back_to_single_placeholder(self):
        starts = _compute_placeholder_starts(self.start, self.end, None)
        self.assertEqual(starts, [self.start])

    def test_zero_sibling_length_falls_back_to_single_placeholder(self):
        starts = _compute_placeholder_starts(self.start, self.end, 0)
        self.assertEqual(starts, [self.start])

    def test_missing_start_returns_empty_list(self):
        self.assertEqual(_compute_placeholder_starts(None, self.end, 30), [])

    def test_end_before_start_falls_back_to_single_placeholder(self):
        bad_end = self.start.replace(hour=22)
        starts = _compute_placeholder_starts(self.start, bad_end, 30)
        self.assertEqual(starts, [self.start])

    def test_safety_cap_prevents_runaway_placeholder_counts(self):
        """A mis-parsed or malicious multi-day span must not explode."""
        huge_end = datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
        starts = _compute_placeholder_starts(self.start, huge_end, 5)
        self.assertLessEqual(len(starts), 96)


class ParseFormatIsoTests(SimpleTestCase):
    def test_parse_z_suffix(self):
        dt = _parse_iso_datetime("2026-05-12T23:00:00.000Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.hour, 23)

    def test_parse_offset(self):
        dt = _parse_iso_datetime("2026-05-12T16:00:00-07:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.astimezone(timezone.utc).hour, 23)

    def test_parse_garbage_returns_none(self):
        self.assertIsNone(_parse_iso_datetime(""))
        self.assertIsNone(_parse_iso_datetime("not a date"))
        self.assertIsNone(_parse_iso_datetime(None))

    def test_format_produces_cal_compatible_z_suffix(self):
        dt = datetime(2026, 5, 12, 23, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_format_cal_iso(dt), "2026-05-12T23:00:00.000Z")


class FetchEventTypeLengthTests(SimpleTestCase):
    """Defensive parsing against the variety of v2 response shapes."""

    def _patched_get(self, response):
        return mock.patch(
            "booking.webhooks._calcom_api_get",
            return_value=(True, response),
        )

    def test_flat_list_shape(self):
        with self._patched_get({"data": [{"slug": "s", "lengthInMinutes": 30}]}):
            self.assertEqual(_fetch_event_type_length_minutes("u", "s"), 30)

    def test_event_type_groups_shape(self):
        resp = {
            "data": {
                "eventTypeGroups": [
                    {"eventTypes": [{"slug": "s", "length": 60}]}
                ]
            }
        }
        with self._patched_get(resp):
            self.assertEqual(_fetch_event_type_length_minutes("u", "s"), 60)

    def test_single_object_shape(self):
        with self._patched_get({"data": {"slug": "s", "lengthInMinutes": 45}}):
            self.assertEqual(_fetch_event_type_length_minutes("u", "s"), 45)

    def test_wrong_slug_is_filtered_out(self):
        resp = {"data": [
            {"slug": "other", "lengthInMinutes": 15},
            {"slug": "s", "lengthInMinutes": 30},
        ]}
        with self._patched_get(resp):
            self.assertEqual(_fetch_event_type_length_minutes("u", "s"), 30)

    def test_api_failure_returns_none(self):
        with mock.patch(
            "booking.webhooks._calcom_api_get",
            return_value=(False, None),
        ):
            self.assertIsNone(_fetch_event_type_length_minutes("u", "s"))

    def test_empty_identifiers_return_none(self):
        self.assertIsNone(_fetch_event_type_length_minutes("", "s"))
        self.assertIsNone(_fetch_event_type_length_minutes("u", ""))


class PlaceholderAttendeeEmailTests(SimpleTestCase):
    """Cal.com v2 /bookings validates ``attendee.email`` — we must send a bare
    address, not the ``Display Name <addr@host>`` form that Django stores in
    ``DEFAULT_FROM_EMAIL``. Without this helper, every placeholder POST 400s
    with ``email_validation_error``.
    """

    def test_display_name_wrapper_is_stripped(self):
        with self.settings(
            DEFAULT_FROM_EMAIL="Thermography Clinic Vancouver Island <admin@thermographyvancouverisland.com>"
        ):
            self.assertEqual(
                _placeholder_attendee_email(),
                "admin@thermographyvancouverisland.com",
            )

    def test_bare_email_is_passed_through(self):
        with self.settings(DEFAULT_FROM_EMAIL="admin@thermographyvancouverisland.com"):
            self.assertEqual(
                _placeholder_attendee_email(),
                "admin@thermographyvancouverisland.com",
            )

    def test_empty_setting_falls_back_to_safe_default(self):
        with self.settings(DEFAULT_FROM_EMAIL=""):
            self.assertEqual(_placeholder_attendee_email(), "noreply@cal.com")

    def test_garbage_setting_falls_back_to_safe_default(self):
        with self.settings(DEFAULT_FROM_EMAIL="not an email"):
            self.assertEqual(_placeholder_attendee_email(), "noreply@cal.com")


class CalcomApiPostRateLimitTests(SimpleTestCase):
    """A burst of placeholder POSTs can hit Cal.com's 429 rate limit. The
    helper must retry with backoff so the batch doesn't silently drop writes.
    """

    def _fake_http_error(self, code, body=b'{"status":"error"}', headers=None):
        err = urllib.error.HTTPError(
            url="https://api.cal.com/v2/bookings",
            code=code,
            msg="",
            hdrs=None,
            fp=None,
        )
        err.read = lambda: body
        err.headers = headers or {}
        return err

    def test_retries_on_429_then_succeeds(self):
        call_count = {"n": 0}

        class _OkResponse:
            status = 200
            def read(self_):
                return b'{"data":{"uid":"ph-1"}}'
            def __enter__(self_):
                return self_
            def __exit__(self_, *exc):
                return False

        def _fake_urlopen(req, timeout=15):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise self._fake_http_error(429, body=b'{"error":"Rate limit exceeded"}')
            return _OkResponse()

        with mock.patch(
            "booking.webhooks.settings.CAL_API_KEY", "test-key", create=True
        ), mock.patch(
            "booking.webhooks.urllib.request.urlopen", side_effect=_fake_urlopen
        ), mock.patch("booking.webhooks.time.sleep"):
            ok, body = _calcom_api_post("/v2/bookings", {"start": "now"})

        self.assertTrue(ok)
        self.assertEqual(call_count["n"], 3)
        self.assertIn("ph-1", body)

    def test_gives_up_after_retry_budget(self):
        def _always_429(req, timeout=15):
            raise self._fake_http_error(429, body=b'{"error":"Rate limit exceeded"}')

        with mock.patch(
            "booking.webhooks.settings.CAL_API_KEY", "test-key", create=True
        ), mock.patch(
            "booking.webhooks.urllib.request.urlopen", side_effect=_always_429
        ), mock.patch("booking.webhooks.time.sleep"):
            ok, body = _calcom_api_post("/v2/bookings", {"start": "now"}, max_retries=2)

        self.assertFalse(ok)
        self.assertIn("429", body)

    def test_400_is_not_retried(self):
        call_count = {"n": 0}

        def _always_400(req, timeout=15):
            call_count["n"] += 1
            raise self._fake_http_error(400, body=b'{"error":"bad request"}')

        with mock.patch(
            "booking.webhooks.settings.CAL_API_KEY", "test-key", create=True
        ), mock.patch(
            "booking.webhooks.urllib.request.urlopen", side_effect=_always_400
        ), mock.patch("booking.webhooks.time.sleep") as sleep_mock:
            ok, _ = _calcom_api_post("/v2/bookings", {"start": "now"})

        self.assertFalse(ok)
        self.assertEqual(call_count["n"], 1)
        sleep_mock.assert_not_called()


class CleanupStalePlaceholdersTests(TestCase):
    """The new orphan-only cleanup must preserve holds for active bookings."""

    def _make_deposit(self, uid, status):
        from clients.models import Client, Deposit
        client = Client.objects.create(name=f"C-{uid}", email=f"{uid}@example.com")
        return Deposit.objects.create(
            client=client,
            amount="25.00",
            cal_booking_uid=uid,
            status=status,
        )

    def _make_placeholder(self, original_uid, placeholder_uid, hours_old=24):
        from django.utils import timezone as tz
        from booking.models import PlaceholderBooking
        ph = PlaceholderBooking.objects.create(
            original_booking_uid=original_uid,
            placeholder_booking_uid=placeholder_uid,
        )
        PlaceholderBooking.objects.filter(pk=ph.pk).update(
            created_at=tz.now() - tz.timedelta(hours=hours_old)
        )
        return ph

    def test_active_deposit_placeholders_are_kept_indefinitely(self):
        """Even 30-day-old placeholders must stay if the deposit is active."""
        from booking.webhooks import cleanup_stale_placeholders
        from booking.models import PlaceholderBooking

        self._make_deposit("orig-active", "confirmed")
        self._make_placeholder("orig-active", "ph-active", hours_old=30 * 24)

        cancel_calls = []
        with mock.patch(
            "booking.webhooks.cancel_calcom_booking",
            side_effect=lambda uid, reason="": cancel_calls.append(uid) or True,
        ):
            cleaned = cleanup_stale_placeholders()

        self.assertEqual(cleaned, 0)
        self.assertEqual(cancel_calls, [])
        self.assertTrue(
            PlaceholderBooking.objects.filter(placeholder_booking_uid="ph-active").exists()
        )

    def test_orphaned_placeholder_is_cancelled(self):
        """A placeholder whose deposit was forfeited should be released."""
        from booking.webhooks import cleanup_stale_placeholders
        from booking.models import PlaceholderBooking

        self._make_deposit("orig-forfeited", "forfeited")
        self._make_placeholder("orig-forfeited", "ph-orphan", hours_old=24)

        cancel_calls = []
        with mock.patch(
            "booking.webhooks.cancel_calcom_booking",
            side_effect=lambda uid, reason="": cancel_calls.append(uid) or True,
        ):
            cleaned = cleanup_stale_placeholders()

        self.assertEqual(cleaned, 1)
        self.assertEqual(cancel_calls, ["ph-orphan"])
        self.assertFalse(
            PlaceholderBooking.objects.filter(placeholder_booking_uid="ph-orphan").exists()
        )

    def test_placeholder_with_missing_deposit_row_is_cancelled(self):
        """If the Deposit row was deleted, the placeholder is orphaned."""
        from booking.webhooks import cleanup_stale_placeholders
        from booking.models import PlaceholderBooking

        self._make_placeholder("never-existed", "ph-missing", hours_old=24)

        cancel_calls = []
        with mock.patch(
            "booking.webhooks.cancel_calcom_booking",
            side_effect=lambda uid, reason="": cancel_calls.append(uid) or True,
        ):
            cleaned = cleanup_stale_placeholders()

        self.assertEqual(cleaned, 1)
        self.assertEqual(cancel_calls, ["ph-missing"])

    def test_young_placeholders_are_skipped_to_avoid_webhook_races(self):
        """A placeholder created <1 h ago is left alone even if orphaned."""
        from booking.webhooks import cleanup_stale_placeholders
        from booking.models import PlaceholderBooking

        self._make_placeholder("in-flight", "ph-new", hours_old=0)

        cancel_calls = []
        with mock.patch(
            "booking.webhooks.cancel_calcom_booking",
            side_effect=lambda uid, reason="": cancel_calls.append(uid) or True,
        ):
            cleaned = cleanup_stale_placeholders()

        self.assertEqual(cleaned, 0)
        self.assertEqual(cancel_calls, [])
        self.assertTrue(
            PlaceholderBooking.objects.filter(placeholder_booking_uid="ph-new").exists()
        )

    def test_max_age_hours_parameter_is_accepted_but_ignored(self):
        """The cron endpoint still passes max_age_hours; we accept and ignore."""
        from booking.webhooks import cleanup_stale_placeholders
        self._make_deposit("orig-active-2", "confirmed")
        self._make_placeholder("orig-active-2", "ph-active-2", hours_old=500)
        cleaned = cleanup_stale_placeholders(max_age_hours=96)
        self.assertEqual(cleaned, 0)


class CreatePlaceholderBookingsIntegrationTests(TestCase):
    """End-to-end: given a 90-min booking, verify correct placeholders tile."""

    def setUp(self):
        from services.models import ServicePage
        from booking.models import Location, LocationServiceLink
        from wagtail.models import Page

        root = Page.objects.first()

        def _service(title, slug):
            svc = ServicePage(
                title=title,
                slug=slug,
                short_summary="summary",
                description="<p>description</p>",
                price_label="$100",
            )
            root.add_child(instance=svc)
            return svc

        self.long_service = _service("Full Body", "full-body")
        self.short_service = _service("Add-On", "add-on")

        self.location = Location.objects.create(name="Main Clinic", address="1 Test St")
        self.long_link = LocationServiceLink.objects.create(
            location=self.location,
            service=self.long_service,
            cal_booking_url="https://cal.com/you/full-body-main",
        )
        self.short_link = LocationServiceLink.objects.create(
            location=self.location,
            service=self.short_service,
            cal_booking_url="https://cal.com/you/add-on-main",
        )

    def test_90_min_booking_creates_three_placeholders_on_30_min_sibling(self):
        """Reproduces the May 12 bug: verify the sibling is fully tiled."""
        from booking.webhooks import _create_placeholder_bookings
        from booking.models import PlaceholderBooking

        calls = []

        def fake_post(path, body=None):
            calls.append((path, body))
            if path == "/v2/bookings":
                return True, json.dumps({
                    "data": {"uid": f"ph-{len(calls)}", "status": "accepted"},
                })
            return True, "{}"

        def fake_length(username, slug):
            return 30  # short sibling's length

        with mock.patch("booking.webhooks._calcom_api_post", side_effect=fake_post), \
             mock.patch("booking.webhooks._fetch_event_type_length_minutes",
                        side_effect=fake_length):
            _create_placeholder_bookings(
                booking_uid="orig-1",
                start_time="2026-05-12T23:00:00.000Z",
                event_title="Full Body — Main Clinic",
                inferred_location="Main Clinic",
                booked_cal_url="https://cal.com/you/full-body-main",
                end_time="2026-05-13T00:30:00.000Z",
            )

        booking_posts = [c for c in calls if c[0] == "/v2/bookings"]
        self.assertEqual(len(booking_posts), 3)

        starts = sorted(c[1]["start"] for c in booking_posts)
        self.assertEqual(starts, [
            "2026-05-12T23:00:00.000Z",
            "2026-05-12T23:30:00.000Z",
            "2026-05-13T00:00:00.000Z",
        ])

        self.assertEqual(
            PlaceholderBooking.objects.filter(original_booking_uid="orig-1").count(),
            3,
        )

    def test_placeholders_are_retained_on_booking_confirmed(self):
        """Confirming a booking must NOT release cross-event-type holds.

        Cal.com does not propagate busy status to sibling event types even
        for confirmed bookings, so we keep the placeholders until the
        booking is cancelled, rejected, or forfeited.
        """
        from booking.webhooks import _handle_booking_confirmed
        from booking.models import PlaceholderBooking
        from clients.models import Client, Deposit

        client = Client.objects.create(name="Dawn Bishop", email="dawn@example.com")
        Deposit.objects.create(
            client=client,
            amount="25.00",
            cal_booking_uid="orig-confirm-test",
            status="pending",
        )
        PlaceholderBooking.objects.create(
            original_booking_uid="orig-confirm-test",
            placeholder_booking_uid="ph-1",
        )
        PlaceholderBooking.objects.create(
            original_booking_uid="orig-confirm-test",
            placeholder_booking_uid="ph-2",
        )

        cancel_calls = []

        def fake_cancel(uid, reason=""):
            cancel_calls.append(uid)
            return True

        with mock.patch("booking.webhooks.cancel_calcom_booking", side_effect=fake_cancel):
            _handle_booking_confirmed({"uid": "orig-confirm-test"})

        self.assertEqual(cancel_calls, [])
        self.assertEqual(
            PlaceholderBooking.objects.filter(
                original_booking_uid="orig-confirm-test"
            ).count(),
            2,
        )
        deposit = Deposit.objects.get(cal_booking_uid="orig-confirm-test")
        self.assertEqual(deposit.status, "confirmed")

    def test_placeholders_are_retained_on_booking_created_for_existing_deposit(self):
        """The BOOKING_CREATED follow-up that transitions status to confirmed
        must also preserve placeholders for the same reason."""
        from booking.webhooks import _handle_booking_created
        from booking.models import PlaceholderBooking
        from clients.models import Client, Deposit

        client = Client.objects.create(name="Rhonda", email="rhonda@example.com")
        Deposit.objects.create(
            client=client,
            amount="25.00",
            cal_booking_uid="orig-created-test",
            status="pending",
        )
        PlaceholderBooking.objects.create(
            original_booking_uid="orig-created-test",
            placeholder_booking_uid="ph-c1",
        )

        cancel_calls = []

        def fake_cancel(uid, reason=""):
            cancel_calls.append(uid)
            return True

        payload = {
            "uid": "orig-created-test",
            "attendees": [{"email": "rhonda@example.com", "name": "Rhonda"}],
            "startTime": "2026-05-13T16:00:00.000Z",
            "endTime": "2026-05-13T16:30:00.000Z",
            "eventTitle": "Breast Thermography Leduc",
        }

        with mock.patch("booking.webhooks.cancel_calcom_booking", side_effect=fake_cancel):
            _handle_booking_created(payload)

        self.assertEqual(cancel_calls, [])
        self.assertEqual(
            PlaceholderBooking.objects.filter(
                original_booking_uid="orig-created-test"
            ).count(),
            1,
        )

    def test_placeholders_still_cancelled_on_booking_cancelled(self):
        """Cancellation of the original booking must still release holds."""
        from booking.webhooks import _handle_booking_cancelled
        from booking.models import PlaceholderBooking
        from clients.models import Client, Deposit

        client = Client.objects.create(name="Test", email="t@example.com")
        Deposit.objects.create(
            client=client,
            amount="25.00",
            cal_booking_uid="orig-cancel-test",
            status="confirmed",
        )
        PlaceholderBooking.objects.create(
            original_booking_uid="orig-cancel-test",
            placeholder_booking_uid="ph-cancel-1",
        )

        cancel_calls = []

        def fake_cancel(uid, reason=""):
            cancel_calls.append(uid)
            return True

        with mock.patch("booking.webhooks.cancel_calcom_booking", side_effect=fake_cancel):
            _handle_booking_cancelled({"uid": "orig-cancel-test"})

        self.assertIn("ph-cancel-1", cancel_calls)
        self.assertEqual(
            PlaceholderBooking.objects.filter(
                original_booking_uid="orig-cancel-test"
            ).count(),
            0,
        )

    def test_missing_end_time_preserves_legacy_single_placeholder(self):
        """If we can't determine an end, don't break — fall back to 1 placeholder."""
        from booking.webhooks import _create_placeholder_bookings
        from booking.models import PlaceholderBooking

        calls = []

        def fake_post(path, body=None):
            calls.append((path, body))
            return True, '{"data": {"uid": "ph-only", "status": "accepted"}}'

        with mock.patch("booking.webhooks._calcom_api_post", side_effect=fake_post), \
             mock.patch("booking.webhooks._fetch_event_type_length_minutes",
                        return_value=30):
            _create_placeholder_bookings(
                booking_uid="orig-2",
                start_time="2026-05-12T23:00:00.000Z",
                event_title="Full Body — Main Clinic",
                inferred_location="Main Clinic",
                booked_cal_url="https://cal.com/you/full-body-main",
                end_time="",
            )

        self.assertEqual(len([c for c in calls if c[0] == "/v2/bookings"]), 1)
        self.assertEqual(
            PlaceholderBooking.objects.filter(original_booking_uid="orig-2").count(),
            1,
        )
