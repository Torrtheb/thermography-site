"""
First Visit app — "Your First Visit" step-by-step guide.

A single page that walks new clients through what to expect:
  1. Book — select a clinic, date & appointment
  2. Instructions — preparation tips before the appointment
  3. Appointment — what happens during the session
  4. Wait — processing / waiting period
  5. Sample Report — what the report looks like
  6. Follow-Up — next steps after receiving results

The owner edits each step's content from Wagtail admin.
The page uses a visual numbered timeline on the public site.

Page hierarchy:
  Root Page
    └── Home Page
          └── Your First Visit  ← FirstVisitPage (only one)
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.images import get_image_model_string
from wagtail.search import index


class FirstVisitPage(Page):
    """
    The 'Your First Visit' page at /your-first-visit/.

    Six steps displayed as a visual timeline.
    Each step has a heading, rich-text body, and optional image.
    max_count = 1: only one of these pages.
    """

    # ── Page intro ────────────────────────────────────────────────
    intro = RichTextField(
        blank=True,
        help_text="Optional intro text shown above the steps "
                  "(e.g., 'We want you to feel comfortable and prepared…').",
    )

    # ── Step 1: Book ──────────────────────────────────────────────
    step1_heading = models.CharField(
        max_length=200,
        default="Book Your Appointment",
        help_text="Heading for the booking step.",
    )
    step1_body = RichTextField(
        blank=True,
        help_text="Explain how to choose a clinic, date, and service.",
    )
    step1_image = models.ForeignKey(
        get_image_model_string(),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for this step.",
    )

    # ── Step 2: Instructions ──────────────────────────────────────
    step2_heading = models.CharField(
        max_length=200,
        default="Preparation Instructions",
        help_text="Heading for the preparation step.",
    )
    step2_body = RichTextField(
        blank=True,
        help_text="What the client needs to do before their appointment "
                  "(e.g., avoid lotions, wear loose clothing).",
    )
    step2_image = models.ForeignKey(
        get_image_model_string(),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for this step.",
    )

    # ── Step 3: Appointment ───────────────────────────────────────
    step3_heading = models.CharField(
        max_length=200,
        default="Your Appointment",
        help_text="Heading for the appointment step.",
    )
    step3_body = RichTextField(
        blank=True,
        help_text="What happens during the thermography session.",
    )
    step3_image = models.ForeignKey(
        get_image_model_string(),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for this step.",
    )

    # ── Step 4: Wait ──────────────────────────────────────────────
    step4_heading = models.CharField(
        max_length=200,
        default="Processing Your Results",
        help_text="Heading for the waiting/processing step.",
    )
    step4_body = RichTextField(
        blank=True,
        help_text="How long results take and what happens behind the scenes.",
    )
    step4_image = models.ForeignKey(
        get_image_model_string(),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for this step.",
    )

    # ── Step 5: Sample Report ─────────────────────────────────────
    step5_heading = models.CharField(
        max_length=200,
        default="Your Report",
        help_text="Heading for the sample report step.",
    )
    step5_body = RichTextField(
        blank=True,
        help_text="Describe what the report includes and show a sample if possible.",
    )
    step5_image = models.ForeignKey(
        get_image_model_string(),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image (e.g., a redacted sample report).",
    )

    # ── Step 6: Follow-Up ─────────────────────────────────────────
    step6_heading = models.CharField(
        max_length=200,
        default="Follow-Up",
        help_text="Heading for the follow-up step.",
    )
    step6_body = RichTextField(
        blank=True,
        help_text="Next steps — review with the technician, scheduling a follow-up, etc.",
    )
    step6_image = models.ForeignKey(
        get_image_model_string(),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional image for this step.",
    )

    # ── Bottom CTA ────────────────────────────────────────────────
    cta_text = models.CharField(
        max_length=200,
        default="Ready to book your first appointment?",
        help_text="Call-to-action text shown at the bottom of the page.",
    )
    cta_button_text = models.CharField(
        max_length=100,
        default="Book Now",
        help_text="Text on the CTA button.",
    )
    cta_button_url = models.CharField(
        max_length=300,
        default="/booking/",
        help_text="URL the button links to (default: /booking/).",
    )

    # ── Admin panel layout ────────────────────────────────────────
    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        MultiFieldPanel(
            [FieldPanel("step1_heading"), FieldPanel("step1_body"), FieldPanel("step1_image")],
            heading="Step 1 — Book",
        ),
        MultiFieldPanel(
            [FieldPanel("step2_heading"), FieldPanel("step2_body"), FieldPanel("step2_image")],
            heading="Step 2 — Instructions",
        ),
        MultiFieldPanel(
            [FieldPanel("step3_heading"), FieldPanel("step3_body"), FieldPanel("step3_image")],
            heading="Step 3 — Appointment",
        ),
        MultiFieldPanel(
            [FieldPanel("step4_heading"), FieldPanel("step4_body"), FieldPanel("step4_image")],
            heading="Step 4 — Wait",
        ),
        MultiFieldPanel(
            [FieldPanel("step5_heading"), FieldPanel("step5_body"), FieldPanel("step5_image")],
            heading="Step 5 — Sample Report",
        ),
        MultiFieldPanel(
            [FieldPanel("step6_heading"), FieldPanel("step6_body"), FieldPanel("step6_image")],
            heading="Step 6 — Follow-Up",
        ),
        MultiFieldPanel(
            [FieldPanel("cta_text"), FieldPanel("cta_button_text"), FieldPanel("cta_button_url")],
            heading="Bottom Call-to-Action",
        ),
    ]

    max_count = 1

    search_fields = Page.search_fields + [
        index.SearchField("intro"),
        index.SearchField("step1_body"),
        index.SearchField("step2_body"),
        index.SearchField("step3_body"),
        index.SearchField("step4_body"),
        index.SearchField("step5_body"),
        index.SearchField("step6_body"),
    ]

    class Meta:
        verbose_name = "Your First Visit Page"
