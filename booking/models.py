"""
Booking app — location-aware booking with Cal.com integration.

Models:
  - Location: permanent clinics and travelling pop-up clinics (Wagtail snippet)
  - LocationServiceLink: maps (location, service) → Cal.com event-type URL
  - BookingPage: the public booking page with multi-step flow

Design (Cal.com is the single source of truth for availability):
  - ALL services are offered at ALL locations.
  - Each (location, service) pair has its OWN Cal.com event-type URL.
  - In Cal.com, each location has its own Schedule:
      • Home clinic schedule: recurring weekly hours (e.g., Tue/Thu 9am–4pm)
      • Pop-up schedules: empty by default — add date overrides before each trip
  - The owner manages availability ONLY in Cal.com.
  - Pop-up locations have a display_until date — they auto-show while the
    date is in the future and auto-hide once it passes. No manual toggling.
  - Permanent clinics are always visible (display_until is ignored).
"""

from django.db import models
from django.utils import timezone

from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet


# ──────────────────────────────────────────────────────────
# Location (Wagtail Snippet — editable from admin sidebar)
# ──────────────────────────────────────────────────────────

@register_snippet
class Location(ClusterableModel):
    """
    A clinic location — either permanent or a travelling pop-up.

    Permanent clinics (is_permanent=True) are always shown on the site.
    Pop-up clinics (is_permanent=False) auto-show while display_until is
    in the future and auto-hide once it passes.

    All services are available at every location.
    Each (location, service) pair maps to a separate Cal.com event type
    via LocationServiceLink. The owner manages availability only in Cal.com
    by assigning each location a separate Cal.com Schedule.
    """

    name = models.CharField(
        max_length=200,
        help_text="Location name (e.g., 'Main Clinic — Nanaimo' or 'Victoria Pop-Up').",
    )

    address = models.TextField(
        help_text="Full street address.",
    )

    is_permanent = models.BooleanField(
        default=False,
        help_text="Check for a permanent clinic with year-round availability. "
                  "Uncheck for a travelling pop-up clinic.",
    )

    display_until = models.DateField(
        null=True,
        blank=True,
        help_text="Pop-up clinics: set the last day of the visit (e.g., March 17). "
                  "The location auto-shows until this date passes, then auto-hides. "
                  "Leave blank for permanent clinics (they're always visible).",
    )

    starts_on = models.DateField(
        null=True,
        blank=True,
        help_text="First date with availability (e.g., March 14). "
                  "The Cal.com calendar opens directly on this date so clients "
                  "don't have to click through months. Leave blank to default to today.",
    )

    schedule_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Displayed schedule or upcoming dates for visitors. "
                  "e.g., 'Tuesdays & Thursdays, 9am – 4pm' for home clinic, "
                  "or 'March 15–17, 2026' for a pop-up visit.",
    )

    map_embed_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Google Maps embed URL (optional). Use the 'Embed a map' URL from Google Maps.",
    )

    featured_on_homepage = models.BooleanField(
        default=False,
        help_text="Show this location on the homepage (e.g., as an upcoming pop-up).",
    )

    deposit_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Deposit amount ($) for bookings at this location. "
                  "Leave blank to use the global default from Site Settings.",
    )

    sort_order = models.IntegerField(
        default=0,
        help_text="Lower numbers appear first. Permanent clinics should be 0.",
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("name"),
                FieldPanel("address"),
                FieldPanel("is_permanent"),
                FieldPanel("display_until"),
                FieldPanel("starts_on"),
                FieldPanel("schedule_text"),
                FieldPanel("map_embed_url"),
            ],
            heading="Location details",
        ),
        InlinePanel(
            "service_links",
            label="Service → Cal.com links",
            help_text="Map each service to its Cal.com event-type URL for this location. "
                      "Create one Cal.com event type per service per location, each assigned "
                      "to this location's Cal.com Schedule. Example: "
                      "'Full Body Scan — Victoria' → https://cal.com/you/full-body-victoria",
        ),
        MultiFieldPanel(
            [
                FieldPanel("deposit_amount"),
            ],
            heading="Deposit",
            help_text="Override the global deposit amount for this location. Leave blank to use the default.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("featured_on_homepage"),
                FieldPanel("sort_order"),
            ],
            heading="Display options",
        ),
    ]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Location"
        verbose_name_plural = "Locations"

    def __str__(self):
        label = self.name
        if self.is_permanent:
            label += " (permanent)"
        elif self.schedule_text:
            label += f" ({self.schedule_text})"
        return label

    @property
    def date_label(self):
        """Human-readable schedule/date label for display."""
        if self.schedule_text:
            return self.schedule_text
        if self.is_permanent:
            return "Available year-round"
        return ""

    @classmethod
    def _active_filter(cls):
        """Q filter for locations that should be visible on the site.

        Permanent clinics are always active.
        Pop-ups are active when display_until >= today (local time).
        """
        today = timezone.localdate()  # respects TIME_ZONE setting
        return (
            models.Q(is_permanent=True)
            | models.Q(display_until__gte=today)
        )

    @classmethod
    def get_active_locations(cls):
        """Return all visible locations (permanent + current pop-ups)."""
        return (
            cls.objects.filter(cls._active_filter())
            .prefetch_related("service_links", "service_links__service")
            .order_by("sort_order", "name")
        )

    @classmethod
    def get_homepage_featured(cls):
        """Return visible locations marked for homepage display."""
        return (
            cls.objects.filter(
                cls._active_filter(),
                featured_on_homepage=True,
            )
            .prefetch_related("service_links", "service_links__service")
            .order_by("sort_order")
        )


# ──────────────────────────────────────────────────────────
# LocationServiceLink — (location, service) → Cal.com URL
# ──────────────────────────────────────────────────────────

class LocationServiceLink(models.Model):
    """
    Maps a (Location, ServicePage) pair to a Cal.com event-type URL.

    Each location has its own Cal.com Schedule. Each service at that
    location is a separate Cal.com event type assigned to that schedule.
    The owner creates these once and then manages availability only
    in Cal.com (weekly hours for home clinic, date overrides for pop-ups).
    """

    location = ParentalKey(
        "booking.Location",
        on_delete=models.CASCADE,
        related_name="service_links",
    )

    service = models.ForeignKey(
        "services.ServicePage",
        on_delete=models.CASCADE,
        related_name="location_links",
        help_text="The service offered at this location.",
    )

    cal_booking_url = models.URLField(
        help_text="Cal.com event-type URL for this service at this location "
                  "(e.g., https://cal.com/you/full-body-nanaimo).",
    )

    panels = [
        FieldPanel("service"),
        FieldPanel("cal_booking_url"),
    ]

    class Meta:
        ordering = ["service__title"]
        unique_together = ("location", "service")
        verbose_name = "Service booking link"
        verbose_name_plural = "Service booking links"

    def __str__(self):
        return f"{self.location.name} — {self.service.title}"


# ──────────────────────────────────────────────────────────
# PlaceholderBooking — cross-event-type slot blocking
# ──────────────────────────────────────────────────────────

class PlaceholderBooking(models.Model):
    """
    Tracks placeholder bookings created on sibling Cal.com event types
    to work around a Cal.com bug where unconfirmed bookings only block
    slots within the same event type, not across other event types.

    When a real booking request arrives, we create placeholder bookings
    on all other event types at the same location for the same time slot.
    These are cancelled when the original booking is confirmed, cancelled,
    rejected, or expires.
    """

    original_booking_uid = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Cal.com UID of the real booking that triggered these placeholders.",
    )
    placeholder_booking_uid = models.CharField(
        max_length=200,
        unique=True,
        help_text="Cal.com UID of the placeholder booking to cancel later.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Placeholder booking"
        verbose_name_plural = "Placeholder bookings"

    def __str__(self):
        return f"Placeholder {self.placeholder_booking_uid} (for {self.original_booking_uid})"


# ──────────────────────────────────────────────────────────
# BookingPage (Wagtail Page — the public /booking/ URL)
# ──────────────────────────────────────────────────────────

class BookingPage(Page):
    """
    The booking page at /booking/.

    Booking flow (same for all locations):
      Choose Location → Choose Service → Pick a Date & Time

    Each service's own Cal.com URL is used for booking.
    For pop-up locations, the Cal.com embed is pre-scrolled to the
    first upcoming availability date so visitors land on the right day.

    max_count = 1: only one booking page.
    """

    headline = models.CharField(
        max_length=200,
        default="Book an Appointment",
        help_text="Main heading on the booking page.",
    )

    instructions = RichTextField(
        blank=True,
        help_text="Optional instructions shown above the booking flow.",
    )

    timezone_label = models.CharField(
        max_length=100,
        default="Pacific Time (PT)",
        help_text="Timezone displayed to visitors so they know what time zone slots are in.",
    )

    booking_embed_url = models.URLField(
        blank=True,
        help_text="Optional: Embed URL for a general Cal.com booking widget (fallback).",
    )

    booking_link_url = models.URLField(
        blank=True,
        help_text="Optional: Direct link to the external booking site (fallback).",
    )

    booking_link_text = models.CharField(
        max_length=100,
        default="Book Online",
        help_text="Text on the booking button (only used with the direct link fallback).",
    )

    # ── Booking flow copy (editable in admin) ───────────────
    first_time_text = models.CharField(
        max_length=200,
        blank=True,
        default="First time? Learn what to expect →",
        help_text="Link below the header. Leave blank to hide.",
    )

    step1_heading = models.CharField(
        max_length=100,
        default="Choose a Location",
        help_text="Heading for step 1.",
    )
    step1_description = models.CharField(
        max_length=200,
        blank=True,
        default="Select where you'd like your appointment.",
        help_text="Description under the heading. Leave blank to hide.",
    )

    step2_heading = models.CharField(
        max_length=100,
        default="Choose a Service",
        help_text="Heading for step 2.",
    )
    step2_description_prefix = models.CharField(
        max_length=150,
        default="Select the service you'd like to book at",
        help_text="Text before the location name, e.g. 'Select the service you'd like to book at'.",
    )
    step2_no_services_message = models.CharField(
        max_length=200,
        default="No services are currently available at this location.",
        help_text="Shown when a location has no services configured.",
    )
    step2_try_different_location = models.CharField(
        max_length=100,
        default="← Try a different location",
        help_text="Button text when no services are available.",
    )

    step3_heading = models.CharField(
        max_length=100,
        default="Pick a Date & Time",
        help_text="Heading for step 3.",
    )
    step3_change_service_text = models.CharField(
        max_length=50,
        default="← Change",
        help_text="Button to go back and change the selected service.",
    )
    change_location_text = models.CharField(
        max_length=80,
        default="← Change location",
        help_text="Button to go back and change the selected location.",
    )

    deposit_instructions = RichTextField(
        blank=True,
        default="After booking, you will receive an email with payment instructions.",
        help_text="Shown in the policy section on the booking page. "
                  "Explain how clients should pay their deposit.",
    )

    policy_checkbox_label = models.CharField(
        max_length=200,
        default="I have read and agree to the cancellation and payment policy.",
        help_text="Label for the required policy agreement checkbox.",
    )
    policy_checkbox_error = models.CharField(
        max_length=100,
        default="Please agree to the policy before booking.",
        help_text="Error message when checkbox is not checked.",
    )

    loading_calendar_text = models.CharField(
        max_length=80,
        default="Loading calendar…",
        help_text="Shown while the booking calendar loads.",
    )
    no_booking_message = models.TextField(
        default="Online booking for this service at this location isn't available yet.\n\nPlease contact us to schedule.",
        help_text="Shown when a service has no Cal.com URL configured. Use line breaks for multiple paragraphs.",
    )
    no_booking_button_text = models.CharField(
        max_length=50,
        default="Contact Us",
        help_text="Button text when booking isn't available.",
    )

    # ── Section visibility toggles ─────────────────────────
    show_policies = models.BooleanField(
        "Show cancellation / deposit policies",
        default=True,
    )
    show_testimonials = models.BooleanField(
        "Show testimonials section",
        default=True,
    )
    show_newsletter = models.BooleanField(
        "Show newsletter signup",
        default=True,
    )

    content_panels = Page.content_panels + [
        FieldPanel("headline"),
        FieldPanel("instructions"),
        FieldPanel("timezone_label"),
        FieldPanel("first_time_text"),
        MultiFieldPanel(
            [
                FieldPanel("step1_heading"),
                FieldPanel("step1_description"),
            ],
            heading="Step 1 — Choose Location",
        ),
        MultiFieldPanel(
            [
                FieldPanel("step2_heading"),
                FieldPanel("step2_description_prefix"),
                FieldPanel("step2_no_services_message"),
                FieldPanel("step2_try_different_location"),
            ],
            heading="Step 2 — Choose Service",
        ),
        MultiFieldPanel(
            [
                FieldPanel("step3_heading"),
                FieldPanel("step3_change_service_text"),
                FieldPanel("change_location_text"),
            ],
            heading="Step 3 — Pick Date & Time",
        ),
        MultiFieldPanel(
            [
                FieldPanel("deposit_instructions"),
                FieldPanel("policy_checkbox_label"),
                FieldPanel("policy_checkbox_error"),
            ],
            heading="Policy & Deposit Section",
        ),
        MultiFieldPanel(
            [
                FieldPanel("loading_calendar_text"),
                FieldPanel("no_booking_message"),
                FieldPanel("no_booking_button_text"),
            ],
            heading="Fallback Messages",
        ),
        MultiFieldPanel(
            [
                FieldPanel("booking_embed_url"),
                FieldPanel("booking_link_url"),
                FieldPanel("booking_link_text"),
            ],
            heading="General Booking Widget (optional fallback)",
            help_text="Used only if no locations/services are configured.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("show_policies"),
                FieldPanel("show_testimonials"),
                FieldPanel("show_newsletter"),
            ],
            heading="Page Sections",
            help_text="Toggle which repeating sections appear on this page.",
        ),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("headline"),
        index.SearchField("instructions"),
    ]

    max_count = 1

    def get_context(self, request, *args, **kwargs):
        """Build context for the booking flow."""
        context = super().get_context(request, *args, **kwargs)

        # Active locations (permanent + active pop-ups)
        locations = list(Location.get_active_locations())
        context["locations"] = locations

        # Build a JSON-serialisable mapping:
        # { location_id: { "services": { slug: { title, cal_url, price, duration, detail_url } } } }
        location_service_map = {}
        for loc in locations:
            svc_map = {}
            for link in loc.service_links.all():
                svc = link.service
                if svc.live:
                    svc_map[svc.slug] = {
                        "title": svc.title,
                        "cal_url": link.cal_booking_url or "",
                        "price": svc.price_label,
                        "duration": svc.duration_label,
                        "detail_url": svc.url,
                    }
            loc.service_count = len(svc_map)
            location_service_map[str(loc.pk)] = {
                "services": svc_map,
                "starts_on": loc.starts_on.isoformat() if loc.starts_on else "",
                "display_until": loc.display_until.isoformat() if loc.display_until else "",
                "is_permanent": loc.is_permanent,
            }
        context["location_service_map"] = location_service_map

        # For deep-linking: /booking/?location=<id>&service=<slug>
        context["preselected_location"] = request.GET.get("location", "")
        context["preselected_service"] = request.GET.get("service", "")

        return context

    class Meta:
        verbose_name = "Booking Page"
