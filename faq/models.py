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
from wagtail.admin.panels import FieldPanel
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

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("intro_image"),
        FieldPanel("faq_items"),
    ]

    max_count = 1

    search_fields = Page.search_fields + [
        index.SearchField("intro"),
        index.SearchField("faq_items"),
    ]

    class Meta:
        verbose_name = "FAQ Page"
