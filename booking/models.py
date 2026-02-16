"""
Booking app — a single page where clients can book an appointment.

For v1 (MVP), this embeds an external booking service (e.g., Calendly,
Acuity, Square Appointments). The owner pastes the embed URL in admin.

For v2, this will be replaced with a custom booking backend.

Page hierarchy:
  Root Page
    └── Book Appointment  ← BookingPage (only one)
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel


class BookingPage(Page):
    """
    The booking page at /booking/.

    The owner sets a headline, optional instructions, and either:
      - an embed URL (for iframe-based booking widgets like Calendly), or
      - a direct booking link (button that opens the external booking site)

    max_count = 1: only one booking page.
    """

    headline = models.CharField(
        max_length=200,
        default="Book an Appointment",
        help_text="Main heading on the booking page.",
    )

    instructions = RichTextField(
        blank=True,
        help_text="Optional instructions shown above the booking widget (e.g., 'Select a service and pick a time').",
    )

    booking_embed_url = models.URLField(
        blank=True,
        help_text="Embed URL for an iframe booking widget (e.g., Calendly embed link). Leave blank if using a direct link instead.",
    )

    booking_link_url = models.URLField(
        blank=True,
        help_text="Direct link to the external booking site. Used if no embed URL is provided.",
    )

    booking_link_text = models.CharField(
        max_length=100,
        default="Book Online",
        help_text="Text on the booking button (only used with the direct link).",
    )

    content_panels = Page.content_panels + [
        FieldPanel("headline"),
        FieldPanel("instructions"),
        MultiFieldPanel(
            [
                FieldPanel("booking_embed_url"),
                FieldPanel("booking_link_url"),
                FieldPanel("booking_link_text"),
            ],
            heading="Booking Widget",
            help_text="Use either an embed URL (iframe) or a direct link (button). If both are set, the embed takes priority.",
        ),
    ]

    max_count = 1

    class Meta:
        verbose_name = "Booking Page"
