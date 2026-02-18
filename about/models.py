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

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.search import index
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.images import get_image_model_string


class TechnicianPage(Page):
    """
    The 'Who We Are' / 'About Us' page.

    Two sections:
      1. About the Clinic — intro, mission, optional image
      2. Meet the Technician — headshot, bio, credentials

    max_count = 1: only one of these pages.
    """

    # ── About the Clinic ──────────────────────────────────────────
    clinic_heading = models.CharField(
        max_length=200,
        default="About Our Clinic",
        help_text="Heading for the clinic section.",
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

    content_panels = Page.content_panels + [
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
