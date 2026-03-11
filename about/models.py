"""
About / "Who We Are" app — clinic overview and technician profile.

Single page type:
  TechnicianPage — shows an "About the Clinic" section followed by the
  technician's name, photo, bio, credentials, and years of experience.
  Only one can exist (max_count = 1).

Page hierarchy:
  Root Page
    └── Home Page
    └── Who We Are  ← TechnicianPage
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
    The 'Who We Are' / 'About Us' page.

    Two sections:
      1. About the Clinic — intro, mission, optional image
      2. Meet the Technician — headshot, bio, credentials

    max_count = 1: only one of these pages.
    """

    # ── About the Clinic ──────────────────────────────────────────
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

    clinic_heading = models.CharField(
        max_length=200,
        default="About Our Clinic",
        blank=True,
        help_text="Optional heading above the clinic description. Leave blank if headings are in the description.",
    )

    clinic_description = RichTextField(
        blank=True,
        help_text="Tell visitors about the clinic — mission, values, what makes it special.",
    )

    clinic_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional photo of the clinic, office, or equipment.",
    )

    # ── About the Technician ──────────────────────────────────────
    full_name = models.CharField(
        max_length=200,
        help_text="Technician's full name.",
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
        help_text="About the technician — background, passion, approach.",
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

    # ── About Our Thermographers (optional team section) ──────────
    thermographers_heading = models.CharField(
        max_length=200,
        default="Meet Our Thermographers",
        blank=True,
        help_text="Heading for the thermographers section. Leave blank to hide the section.",
    )

    # ── Section visibility toggles ─────────────────────────
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

    content_panels = Page.content_panels + [
        FieldPanel("subtitle"),
        FieldPanel("hero_image"),
        MultiFieldPanel(
            [
                FieldPanel("clinic_heading"),
                FieldPanel("clinic_description"),
                FieldPanel("clinic_image"),
            ],
            heading="About the Clinic",
        ),
        MultiFieldPanel(
            [
                FieldPanel("full_name"),
                FieldPanel("headshot"),
                FieldPanel("bio"),
                FieldPanel("credentials"),
                FieldPanel("years_experience"),
            ],
            heading="About the Technician",
        ),
        MultiFieldPanel(
            [
                FieldPanel("thermographers_heading"),
                InlinePanel("thermographers", label="Thermographer", min_num=0, max_num=10),
            ],
            heading="Our Thermographers (optional)",
        ),
        MultiFieldPanel(
            [
                FieldPanel("show_cta"),
                FieldPanel("show_newsletter"),
                FieldPanel("show_policies"),
                FieldPanel("show_testimonials"),
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
