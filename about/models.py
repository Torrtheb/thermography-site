"""
About Us page — multi-section storytelling layout.

Sections (in display order):
  1. Hero — title, subtitle, hero image
  2. Owner Story — personal journey, photo, bio, credentials
  3. Creating the Clinic — clinic narrative, images
  4. People Reading Your Thermograms — thermographer profiles
  5. Reach Out CTA — link to contact page
  6. Bottom sections — booking CTA, testimonials, policies, newsletter

Page hierarchy:
  Root Page
    └── Home Page
    └── About Us  ← TechnicianPage (only one)
"""

from django.db import models

from wagtail.models import Page, Orderable
from wagtail.fields import RichTextField
from wagtail.search import index
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, InlinePanel
from wagtail.images import get_image_model_string
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel


class Thermographer(Orderable):
    """A single thermographer profile, linked to TechnicianPage."""

    page = ParentalKey(
        "about.TechnicianPage",
        on_delete=models.CASCADE,
        related_name="thermographers",
    )

    name = models.CharField(
        max_length=200,
        help_text="Thermographer's full name.",
    )

    photo = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Professional headshot / portrait photo.",
    )

    role = models.CharField(
        max_length=200,
        blank=True,
        help_text="Job title or role, e.g. 'Certified Clinical Thermographer'.",
    )

    bio = RichTextField(
        blank=True,
        help_text="Short bio — background, qualifications, approach.",
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("photo"),
        FieldPanel("role"),
        FieldPanel("bio"),
    ]

    class Meta(Orderable.Meta):
        verbose_name = "Thermographer"
        verbose_name_plural = "Thermographers"


class TechnicianPage(Page):
    """
    The About Us page — multi-section storytelling layout.

    max_count = 1: only one of these pages.
    """

    # ── Hero ───────────────────────────────────────────────────
    subtitle = models.CharField(
        max_length=300,
        blank=True,
        help_text="Short subheading shown below the page title in the hero.",
    )

    hero_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image shown beside the title and subtitle in the hero.",
    )

    # ── Section 1: Owner Story ─────────────────────────────────
    owner_story_heading = models.CharField(
        max_length=200,
        default="Our Story",
        blank=True,
        help_text="Heading for the owner story section.",
    )

    owner_story_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for the owner story section (e.g. a candid photo).",
    )

    full_name = models.CharField(
        max_length=200,
        help_text="Owner / technician's full name.",
    )

    headshot = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Professional headshot / portrait photo.",
    )

    bio = RichTextField(
        help_text="The owner's personal story — why women's health, why Vancouver Island, "
                  "entrepreneurship journey, interest in breast health, etc.",
    )

    credentials = RichTextField(
        blank=True,
        help_text="Certifications, training, qualifications (optional).",
    )

    years_experience = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Years of experience (optional, shown as a stat).",
    )

    # ── Section 2: Creating the Clinic ─────────────────────────
    clinic_story_heading = models.CharField(
        max_length=200,
        default="Creating the Clinic",
        blank=True,
        help_text="Heading for the clinic story section.",
    )

    # Keep original field names for backward compatibility
    clinic_heading = models.CharField(
        max_length=200,
        default="About Our Clinic",
        blank=True,
        help_text="(Legacy) Optional sub-heading. Use clinic_story_heading instead.",
    )

    clinic_description = RichTextField(
        blank=True,
        help_text="The clinic's story — recently moved, community-oriented space, "
                  "part of Thermography Inc / Dr. Alexander Mostovoy, mobile clinic, etc.",
    )

    clinic_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Primary image for the clinic section (e.g. the clinic space).",
    )

    clinic_story_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional second image (e.g. the mobile clinic or community event).",
    )

    # ── Section 3: Thermographer Profiles ──────────────────────
    thermographers_heading = models.CharField(
        max_length=200,
        default="People Reading Your Thermograms",
        blank=True,
        help_text="Heading for the thermographer profiles section. Leave blank to hide.",
    )

    # ── Section 4: Reach Out / Contact CTA ─────────────────────
    show_contact_cta = models.BooleanField(
        "Show 'Reach Out' contact section",
        default=True,
    )

    contact_heading = models.CharField(
        max_length=200,
        default="Have Questions?",
        help_text="Heading for the contact CTA section.",
    )

    contact_text = models.TextField(
        blank=True,
        default="We'd love to hear from you. Reach out anytime — no question is too small.",
        help_text="Optional supporting text below the contact heading.",
    )

    contact_button_text = models.CharField(
        max_length=100,
        default="Get in Touch",
        help_text="Text shown on the contact button.",
    )

    contact_button_url = models.CharField(
        max_length=300,
        default="/contact/",
        help_text="URL for the contact button.",
    )

    # ── Bottom section toggles ─────────────────────────────────
    show_cta = models.BooleanField(
        "Show 'Book an Appointment' section",
        default=True,
    )
    show_newsletter = models.BooleanField(
        "Show newsletter signup",
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

    # ── Bottom CTA copy ────────────────────────────────────────
    cta_heading = models.CharField(
        max_length=200,
        default="Learn More or Book an Appointment",
        help_text="Heading for the bottom CTA section.",
    )
    cta_text = models.TextField(
        blank=True,
        default="Interested in proactive thermographic imaging? Explore our services or schedule your appointment online.",
        help_text="Optional supporting text below the CTA heading.",
    )
    cta_button_text = models.CharField(
        max_length=100,
        default="Book an Appointment",
        help_text="Text shown on the primary CTA button.",
    )
    cta_button_url = models.CharField(
        max_length=300,
        default="/booking/",
        help_text="URL for the primary CTA button.",
    )
    secondary_cta_button_text = models.CharField(
        max_length=100,
        default="View Services",
        help_text="Text shown on the secondary CTA button.",
    )
    secondary_cta_button_url = models.CharField(
        max_length=300,
        default="/services/",
        help_text="URL for the secondary CTA button.",
    )

    # ── Admin panel layout ─────────────────────────────────────
    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("subtitle"),
                FieldPanel("hero_image"),
            ],
            heading="Hero",
        ),
        MultiFieldPanel(
            [
                FieldPanel("owner_story_heading"),
                FieldPanel("full_name"),
                FieldPanel("headshot"),
                FieldPanel("owner_story_image"),
                FieldPanel("bio"),
                FieldPanel("credentials"),
                FieldPanel("years_experience"),
            ],
            heading="Section 1 — Owner Story",
            help_text="The owner's personal journey — why women's health, why Vancouver Island, etc.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("clinic_story_heading"),
                FieldPanel("clinic_description"),
                FieldPanel("clinic_image"),
                FieldPanel("clinic_story_image"),
            ],
            heading="Section 2 — Creating the Clinic",
            help_text="The clinic's story — community space, Thermography Inc, mobile clinic, etc.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("thermographers_heading"),
                InlinePanel("thermographers", label="Thermographer", min_num=0, max_num=10),
            ],
            heading="Section 3 — People Reading Your Thermograms",
        ),
        MultiFieldPanel(
            [
                FieldPanel("show_contact_cta"),
                FieldPanel("contact_heading"),
                FieldPanel("contact_text"),
                FieldPanel("contact_button_text"),
                FieldPanel("contact_button_url"),
            ],
            heading="Section 4 — Reach Out",
            help_text="A contact CTA linking visitors to the contact page.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("show_cta"),
                FieldPanel("show_newsletter"),
                FieldPanel("show_policies"),
                FieldPanel("show_testimonials"),
            ],
            heading="Bottom Page Sections",
            help_text="Toggle which repeating sections appear on this page.",
        ),
        MultiFieldPanel(
            [
                FieldPanel("cta_heading"),
                FieldPanel("cta_text"),
                FieldPanel("cta_button_text"),
                FieldPanel("cta_button_url"),
                FieldPanel("secondary_cta_button_text"),
                FieldPanel("secondary_cta_button_url"),
            ],
            heading="Bottom CTA",
            help_text="Customize the call-to-action shown near the page bottom.",
        ),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("full_name"),
        index.SearchField("bio"),
        index.SearchField("credentials"),
        index.SearchField("clinic_description"),
    ]

    max_count = 1

    class Meta:
        verbose_name = "About Page"
