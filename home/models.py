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
    PoliciesBlock,
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

    @property
    def latest_content_update(self):
        """Cache-busting key that tracks changes to related models.

        The homepage renders data from Testimonials and Locations which
        change independently of the page itself. By checking the latest
        pk from those models (pks are monotonically increasing, so a new
        or changed record means a new max pk), we ensure the template
        cache invalidates when any referenced model changes.
        """
        from booking.models import Location

        signals = [
            self.last_published_at,
            Testimonial.objects.order_by("-pk").values_list("pk", flat=True).first(),
            Location.objects.order_by("-pk").values_list("pk", flat=True).first(),
        ]
        return "-".join(str(s) for s in signals if s is not None)

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
            ("policies", PoliciesBlock()),
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

    show_policies = models.BooleanField(
        "Show payment & cancellation policies",
        default=True,
        help_text="Pulls content from Settings → Site Settings → Policies.",
    )

    show_newsletter = models.BooleanField(
        "Show newsletter signup",
        default=True,
    )

    content_panels = Page.content_panels + [
        FieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("show_policies"), FieldPanel("show_newsletter")],
            heading="Page Sections",
            help_text="Toggle which repeating sections appear on this page.",
        ),
    ]

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

    deposit_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=25.00,
        help_text="Non-refundable booking deposit amount ($). Displayed on the booking page and used as the default when creating deposit records.",
    )

    etransfer_email = models.EmailField(
        blank=True,
        default="",
        help_text="e-Transfer email address included in deposit request emails sent to clients. Never displayed publicly on the website.",
    )

    # ── Editable email templates ─────────────────────────
    # The owner can edit these at any time. Placeholders like {client_name}
    # are automatically replaced when the email is sent.

    email_deposit_request = models.TextField(
        "Deposit request email body",
        default=(
            "Hi {client_name},\n\n"
            "Thank you for booking your {service_name} appointment{appointment_line}! "
            "The total appointment price is {service_price}.\n\n"
            "To confirm your booking, a non-refundable ${amount} deposit is required.\n\n"
            "HOW TO PAY:\n"
            "  - e-Transfer: Send ${amount} to {etransfer_email}\n"
            "  - Cash: Pay at your appointment\n"
            "  - Cheque: Mail or bring in person\n\n"
            "Please note: only send e-Transfers to the address above. "
            "We will never ask you to send money to a different address.\n\n"
            "Your deposit will be applied toward your service fee on the day of your visit.\n\n"
            "If you have any questions, please reply to this email.\n\n"
            "Best regards,\n"
            "Your Thermography Team"
        ),
        help_text=(
            "Sent automatically when a client books. Available placeholders: "
            "{client_name}, {amount}, {appointment_line} (\" on March 15, 2026\" or blank), "
            "{etransfer_email}, {service_name} (e.g. \"Full Body Scan\"), "
            "{service_price} (e.g. \"$150\" — pulled from the service page). "
            "Edit freely — placeholders are replaced when the email sends."
        ),
    )

    email_deposit_warning = models.TextField(
        "Deposit warning email body (48h reminder)",
        default=(
            "Hi {client_name},\n\n"
            "This is a friendly reminder that the ${amount} booking deposit for your "
            "thermography appointment{appointment_line}{service_line} has not yet been received.\n\n"
            "If we do not receive the deposit within the next 24 hours, the appointment "
            "will be automatically cancelled.\n\n"
            "If you've already sent payment, please disregard this message — it may take "
            "a moment for us to process it.\n\n"
            "If you have any questions, please reply to this email.\n\n"
            "Best regards,\n"
            "Your Thermography Team"
        ),
        help_text=(
            "Sent 48 hours after booking if the deposit hasn't been received (24 hours before cancellation). "
            "Placeholders: {client_name}, {amount}, {appointment_line}, {service_line}."
        ),
    )

    email_deposit_cancelled = models.TextField(
        "Cancellation email body (72h rule)",
        default=(
            "Hi {client_name},\n\n"
            "We're writing to let you know that your thermography appointment"
            "{appointment_line}{service_line} has been cancelled.\n\n"
            "Unfortunately, the booking deposit was not received within 72 hours. "
            "Please let us know asap if you want to rebook.\n\n"
            "If you believe this was an error or you've already sent payment, "
            "please reply to this email and we'll sort it out right away.\n\n"
            "Best regards,\n"
            "Your Thermography Team"
        ),
        help_text=(
            "Sent automatically when a deposit expires after 72 hours. "
            "Placeholders: {client_name}, {amount}, {appointment_line}, {service_line}."
        ),
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
        MultiFieldPanel(
            [
                FieldPanel("deposit_amount"),
                FieldPanel("etransfer_email"),
            ],
            heading="Deposit Settings",
            help_text="Configure the booking deposit amount and payment details.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("email_deposit_request"),
                FieldPanel("email_deposit_warning"),
                FieldPanel("email_deposit_cancelled"),
            ],
            heading="Email Templates",
            help_text=(
                "Edit the wording of automated emails. Words in {curly braces} are "
                "placeholders — they get replaced with real values when the email sends. "
                "You can change everything else freely."
            ),
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