"""
Services app models.

Two page types:
  1. ServicesIndexPage — the listing page at /services/
     Shows all ServicePages as a grid of cards.

  2. ServicePage — an individual service (child of ServicesIndexPage)
     Each one has a title, summary, description, price, duration, and image.

How Wagtail page hierarchy works:
  Root Page
    └── Home Page
    └── Services Index Page        ← ServicesIndexPage (you create ONE of these)
          ├── Full Body Scan       ← ServicePage
          ├── Breast Screening     ← ServicePage
          └── Sports Injury Scan   ← ServicePage

The owner adds new services by clicking "Add child page" under the Services page.
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.images import get_image_model_string
from wagtail.search import index


class ServicesIndexPage(Page):
    """
    The listing page at /services/.
    Shows all child ServicePages as a grid of cards.

    max_count = 1: only one Services listing page can exist.
    subpage_types: only ServicePage can be added as a child.
    """

    intro = models.TextField(
        blank=True,
        help_text="Optional intro text shown above the services grid.",
    )

    intro_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image displayed in the intro section.",
    )

    includes_heading = models.CharField(
        max_length=100,
        default="Every service includes",
        blank=True,
        help_text="Heading for the 'what's included' card below the intro.",
    )

    includes_items = RichTextField(
        blank=True,
        features=["ul", "ol", "bold"],
        help_text="Bullet list of what every service includes (use a bulleted list).",
    )

    includes_note = models.CharField(
        max_length=200,
        blank=True,
        default="Reports are typically available within 3\u20134 weeks.",
        help_text="Small note shown below the included items (e.g., turnaround time).",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("intro_image"),
        MultiFieldPanel(
            [
                FieldPanel("includes_heading"),
                FieldPanel("includes_items"),
                FieldPanel("includes_note"),
            ],
            heading="What's Included Card",
            help_text="The card shown below the intro, listing what every service includes.",
        ),
    ]

    # --- Page hierarchy rules ---
    max_count = 1                          # only one services index
    subpage_types = ["services.ServicePage"]  # only ServicePages underneath

    def get_context(self, request, *args, **kwargs):
        """
        Add live (published) child ServicePages to the template context.
        This is how the template gets the list of services to display.
        """
        context = super().get_context(request, *args, **kwargs)
        context["services"] = (
            ServicePage.objects.child_of(self).live().public().order_by("title")
        )
        return context

    class Meta:
        verbose_name = "Services Index Page"


class ServicePage(Page):
    """
    An individual service page (e.g., 'Full Body Thermography').

    parent_page_types: can only live under ServicesIndexPage.
    """

    short_summary = models.CharField(
        max_length=250,
        help_text="One-line summary shown on the services card (e.g., 'Non-invasive full body screening').",
    )

    description = RichTextField(
        help_text="Full description shown on the service detail page.",
    )

    price_label = models.CharField(
        max_length=50,
        help_text="Price displayed on the card (e.g., '$150').",
    )

    duration_label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional duration (e.g., '60 minutes').",
    )

    service_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for this service.",
    )

    image_caption = models.CharField(
        max_length=250,
        blank=True,
        help_text="Optional caption displayed below the service image.",
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Featured services may be highlighted on the homepage.",
    )

    # --- Admin panel layout ---
    content_panels = Page.content_panels + [
        FieldPanel("short_summary"),
        FieldPanel("description"),
        MultiFieldPanel(
            [
                FieldPanel("price_label"),
                FieldPanel("duration_label"),
            ],
            heading="Pricing & Duration",
        ),
        MultiFieldPanel(
            [
                FieldPanel("service_image"),
                FieldPanel("image_caption"),
            ],
            heading="Service Image",
        ),
        FieldPanel("is_featured"),
    ]

    # --- Page hierarchy rules ---
    parent_page_types = ["services.ServicesIndexPage"]  # must live under index

    search_fields = Page.search_fields + [
        index.SearchField("short_summary"),
        index.SearchField("description"),
    ]

    class Meta:
        verbose_name = "Service Page"
