"""
Booking app — a single page where clients can book an appointment.

Displays a service selector with Cal.com booking links per service.
Each service links to its own Cal.com event type, which handles
availability, slot conflicts, and prevents double-booking automatically.

The owner also has the option to embed a general Cal.com widget or
provide a direct booking link as a fallback.

Page hierarchy:
  Root Page
    └── Book Appointment  ← BookingPage (only one)
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.search import index
from wagtail.admin.panels import FieldPanel, MultiFieldPanel


class BookingPage(Page):
    """
    The booking page at /booking/.

    Shows a service selector with per-service Cal.com booking links.
    Also supports a general embed URL or direct link as fallback.

    max_count = 1: only one booking page.
    """

    headline = models.CharField(
        max_length=200,
        default="Book an Appointment",
        help_text="Main heading on the booking page.",
    )

    instructions = RichTextField(
        blank=True,
        help_text="Optional instructions shown above the service selector (e.g., 'Select a service and pick a time').",
    )

    booking_embed_url = models.URLField(
        blank=True,
        help_text="Optional: Embed URL for a general Cal.com booking widget. Shown below the service selector.",
    )

    booking_link_url = models.URLField(
        blank=True,
        help_text="Optional: Direct link to the external booking site. Used if no embed URL is provided.",
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
            heading="General Booking Widget (optional fallback)",
            help_text="Services with Cal.com URLs set will show their own booking buttons above. "
                      "Use this section for a general booking widget or fallback link.",
        ),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("headline"),
        index.SearchField("instructions"),
    ]

    max_count = 1

    def get_context(self, request, *args, **kwargs):
        """Add all live services to the template context for the service selector."""
        from services.models import ServicePage

        context = super().get_context(request, *args, **kwargs)
        services = ServicePage.objects.live().public().order_by("title")
        context["services"] = services

        # Support deep-linking: /booking/?service=<slug>
        preselected_slug = request.GET.get("service", "")
        context["preselected_slug"] = preselected_slug

        return context

    class Meta:
        verbose_name = "Booking Page"
