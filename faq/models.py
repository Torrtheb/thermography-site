"""
FAQ app — a single page with collapsible question/answer items.

The owner adds Q&A pairs using a StreamField of FAQItemBlocks.
Each item renders as a clickable accordion on the public site.

Page hierarchy:
  Root Page
    └── FAQ  ← FAQPage (only one)
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import StreamField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import CharBlock, RichTextBlock, StructBlock
from wagtail.search import index
from wagtail.images import get_image_model_string


class FAQItemBlock(StructBlock):
    """A single question/answer pair."""
    question = CharBlock(
        max_length=300,
        help_text="The question visitors will see (e.g. 'What should I wear to my appointment?').",
    )
    answer = RichTextBlock(
        help_text="The answer — you can use bold, links, and bullet points.",
    )

    class Meta:
        icon = "help"
        label = "FAQ Item"
        description = "A question and answer pair — click to expand/collapse on the website."


class FAQPage(Page):
    """
    The FAQ page at /faq/.
    Contains an optional intro and a list of question/answer items.
    max_count = 1: only one FAQ page.
    """

    intro = models.TextField(
        blank=True,
        help_text="Optional intro text shown above the FAQ items.",
    )

    intro_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image shown beside the intro text.",
    )

    faq_items = StreamField(
        [
            ("faq_item", FAQItemBlock()),
        ],
        use_json_field=True,
        blank=True,
    )

    show_cta = models.BooleanField(
        "Show 'Book an Appointment' section",
        default=True,
    )
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
    cta_heading = models.CharField(
        max_length=200,
        default="Still have questions?",
        help_text="Heading for the bottom CTA section.",
    )
    cta_text = models.TextField(
        blank=True,
        default="Book an appointment and we'll walk through everything together.",
        help_text="Optional supporting text below the CTA heading.",
    )
    cta_button_text = models.CharField(
        max_length=100,
        default="Book an Appointment",
        help_text="Text shown on the CTA button.",
    )
    cta_button_url = models.CharField(
        max_length=300,
        default="/booking/",
        help_text="URL for the CTA button.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("intro_image"),
        FieldPanel("faq_items"),
        MultiFieldPanel(
            [
                FieldPanel("show_cta"),
                FieldPanel("show_policies"),
                FieldPanel("show_testimonials"),
                FieldPanel("show_newsletter"),
            ],
            heading="Page Sections",
            help_text="Toggle which repeating sections appear on this page.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("cta_heading"),
                FieldPanel("cta_text"),
                FieldPanel("cta_button_text"),
                FieldPanel("cta_button_url"),
            ],
            heading="Bottom CTA",
            help_text="Customize the call-to-action shown near the page bottom.",
        ),
    ]

    max_count = 1

    search_fields = Page.search_fields + [
        index.SearchField("intro"),
        index.SearchField("faq_items"),
    ]

    class Meta:
        verbose_name = "FAQ Page"
