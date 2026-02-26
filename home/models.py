"""
HomePage model — defines what fields the owner can edit in the admin.
SiteSettings — site-wide branding (name, tagline) editable from admin.
Testimonial snippet — reusable client testimonials managed from Wagtail admin.

Uses StreamField so the owner can add, remove, and reorder sections freely.
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import StreamField, RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.images import get_image_model_string
from wagtail.search import index
from wagtail.snippets.models import register_snippet

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
    TestimonialsCarouselBlock,
    NewsItemBlock,
    FAQPreviewBlock,
    CallToActionBlock,
    BigCTABlock,
    ProcessStepsBlock,
    UpcomingClinicsBlock,
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
            ("testimonials", TestimonialsCarouselBlock()),
            ("news_item", NewsItemBlock()),
            ("faq_preview", FAQPreviewBlock()),
            ("call_to_action", CallToActionBlock()),
            ("big_cta", BigCTABlock()),
            ("process_steps", ProcessStepsBlock()),
            ("upcoming_clinics", UpcomingClinicsBlock()),
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
        default="Thermography Clinic Vancouver Island",
        help_text="Business name shown in the header and footer.",
    )

    logo = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Business logo shown in the header. Upload a transparent PNG for best results.",
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

    deposit_policy = RichTextField(
        blank=True,
        help_text="Deposit/payment policy shown alongside the cancellation policy. Leave blank to hide.",
    )

    payment_methods = RichTextField(
        blank=True,
        help_text="Accepted payment methods (e.g. e-Transfer, credit card, cash). Shown on the booking page.",
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("business_name"),
                FieldPanel("logo"),
                FieldPanel("tagline"),
            ],
            heading="Branding",
        ),
        MultiFieldPanel(
            [
                FieldPanel("cancellation_policy"),
                FieldPanel("deposit_policy"),
                FieldPanel("payment_methods"),
            ],
            heading="Policies",
        ),
    ]

    class Meta:
        verbose_name = "Site Settings"


# ──────────────────────────────────────────────────────────
# Testimonial (Wagtail Snippet — editable from admin sidebar)
# ──────────────────────────────────────────────────────────

@register_snippet
class Testimonial(index.Indexed, models.Model):
    """
    A client testimonial/review.

    The owner manages these from Wagtail admin → Snippets → Testimonials.
    Featured testimonials appear automatically on high-traffic pages.
    """

    quote = models.TextField(
        help_text="The testimonial text (1–3 sentences works best).",
    )

    author_name = models.CharField(
        max_length=120,
        help_text="Client's name (or initials for privacy, e.g. 'Sarah M.').",
    )

    role = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional context, e.g. 'Client since 2023' or 'Referred by Dr. Smith'.",
    )

    service = models.ForeignKey(
        "services.ServicePage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="testimonials",
        help_text="Link to a specific service (optional). Shows relevant testimonials on service pages.",
    )

    photo = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional client photo (displayed as a small avatar).",
    )

    star_rating = models.PositiveSmallIntegerField(
        default=5,
        choices=[(i, f"{i} star{'s' if i != 1 else ''}") for i in range(1, 6)],
        help_text="Star rating (1–5).",
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Featured testimonials appear on high-traffic pages (booking, first visit).",
    )

    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first.",
    )

    panels = [
        FieldPanel("quote"),
        MultiFieldPanel(
            [
                FieldPanel("author_name"),
                FieldPanel("role"),
                FieldPanel("photo"),
            ],
            heading="Author",
        ),
        FieldPanel("service"),
        FieldPanel("star_rating"),
        FieldPanel("is_featured"),
        FieldPanel("sort_order"),
    ]

    search_fields = [
        index.SearchField("quote"),
        index.SearchField("author_name"),
    ]

    class Meta:
        ordering = ["sort_order", "-pk"]
        verbose_name = "Testimonial"
        verbose_name_plural = "Testimonials"

    def __str__(self):
        short = self.quote[:50]
        if len(self.quote) > 50:
            return f'"{short}…" — {self.author_name}'
        return f'"{self.quote}" — {self.author_name}'