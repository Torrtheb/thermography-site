"""
HomePage model — defines what fields the owner can edit in the admin.

Uses StreamField so the owner can add, remove, and reorder sections freely.
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import StreamField
from wagtail.admin.panels import FieldPanel

from .blocks import (
    HeroBlock,
    TextWithImageBlock,
    TestimonialBlock,
    NewsItemBlock,
    CallToActionBlock,
)

# We also use Wagtail's built-in RichTextBlock for free-form text sections
from wagtail.blocks import RichTextBlock


class HomePage(Page):
    """
    The main landing page of the site.

    'body' is a StreamField — the owner picks from a menu of block types
    and adds them in any order. Think of it like building with LEGO blocks.

    max_num = 1 means only one HomePage can exist (there's only one homepage).
    """

    body = StreamField(
        [
            # Each tuple is ("internal_name", BlockClass)
            # The internal name is used in the database and templates
            ("hero", HeroBlock()),
            ("text_section", RichTextBlock(
                template="home/blocks/richtext_block.html",
                icon="pilcrow",
                label="Text Section",
            )),
            ("text_with_image", TextWithImageBlock()),
            ("testimonial", TestimonialBlock()),
            ("news_item", NewsItemBlock()),
            ("call_to_action", CallToActionBlock()),
        ],
        use_json_field=True,  # required by Wagtail for new StreamFields
        blank=True,           # allows the page to be saved with no blocks
    )

    # --- Admin panel layout ---
    # content_panels defines what the owner sees when editing the page
    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]

    # Only allow one homepage
    max_count = 1