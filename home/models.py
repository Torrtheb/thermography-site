"""
HomePage model — defines what fields the owner can edit in the admin.
SiteSettings — site-wide branding (name, tagline) editable from admin.

Uses StreamField so the owner can add, remove, and reorder sections freely.
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import StreamField, RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting

from .blocks import (
    AnnouncementBlock,
    HeroBlock,
    TextWithImageBlock,
    ThreeColumnFeatureBlock,
    TwoColumnInfoBlock,
    ServicesGridBlock,
    ChecklistBlock,
    TrustBlock,
    WhyChooseUsBlock,
    TestimonialBlock,
    NewsItemBlock,
    FAQPreviewBlock,
    CallToActionBlock,
    BigCTABlock,
    ProcessStepsBlock,
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
            ("announcement", AnnouncementBlock()),
            ("hero", HeroBlock()),
            ("text_section", RichTextBlock(
                template="home/blocks/richtext_block.html",
                icon="pilcrow",
                label="Text Section",
                help_text="A free-form text area — type anything you want with bold, links, bullet points, etc.",
            )),
            ("three_column_feature", ThreeColumnFeatureBlock()),
            ("text_with_image", TextWithImageBlock()),
            ("two_column_info", TwoColumnInfoBlock()),
            ("services_grid", ServicesGridBlock()),
            ("checklist", ChecklistBlock()),
            ("trust", TrustBlock()),
            ("why_choose_us", WhyChooseUsBlock()),
            ("testimonial", TestimonialBlock()),
            ("news_item", NewsItemBlock()),
            ("faq_preview", FAQPreviewBlock()),
            ("call_to_action", CallToActionBlock()),
            ("big_cta", BigCTABlock()),
            ("process_steps", ProcessStepsBlock()),
        ],
        use_json_field=True,  # required by Wagtail for new StreamFields
        blank=True,           # allows the page to be saved with no blocks
        block_counts={
            "announcement": {"max_num": 1},   # only one announcement at a time
            "hero": {"max_num": 2},            # up to two hero banners
            "services_grid": {"max_num": 1},   # only one services grid
            "faq_preview": {"max_num": 1},     # only one FAQ preview
        },
    )

    # --- Admin panel layout ---
    # content_panels defines what the owner sees when editing the page
    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]

    # Only allow one homepage
    max_count = 1


@register_setting(icon="cog")
class SiteSettings(BaseSiteSetting):
    """
    Site-wide branding settings editable from Wagtail admin → Settings → Site Settings.
    These values are available in all templates via {{ settings.home.SiteSettings }}.
    """

    business_name = models.CharField(
        max_length=100,
        default="Thermography Vancouver Island",
        help_text="Business name shown in the header and footer.",
    )

    tagline = models.TextField(
        blank=True,
        default="Providing accessible thermography services for residents of Vancouver Island and beyond\u2026",
        help_text="Short description shown in the footer.",
    )

    cancellation_policy = RichTextField(
        blank=True,
        help_text="Cancellation/rescheduling policy shown on the booking and services pages. Leave blank to hide.",
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("business_name"),
                FieldPanel("tagline"),
            ],
            heading="Branding",
        ),
        FieldPanel("cancellation_policy"),
    ]

    class Meta:
        verbose_name = "Site Settings"