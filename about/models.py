"""
About / "Who We Are" app — the technician profile page.

Single page type:
  TechnicianPage — shows the technician's name, photo, bio, credentials,
  and years of experience. Only one can exist (max_count = 1).

Page hierarchy:
  Root Page
    └── Home Page
    └── Who We Are  ← TechnicianPage
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.images import get_image_model_string


class TechnicianPage(Page):
    """
    The 'Who We Are' / 'Meet Your Technician' page.

    max_count = 1: only one of these pages.
    """

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
        FieldPanel("full_name"),
        FieldPanel("headshot"),
        FieldPanel("bio"),
        MultiFieldPanel(
            [
                FieldPanel("credentials"),
                FieldPanel("years_experience"),
            ],
            heading="Credentials & Experience",
        ),
    ]

    max_count = 1

    class Meta:
        verbose_name = "Technician Page"
