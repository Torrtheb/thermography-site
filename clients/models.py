"""
Client database — encrypted PII managed from Wagtail admin.

All personal fields (name, phone, email) are encrypted at rest using
Fernet symmetric encryption.  The encryption key is stored in the
FIELD_ENCRYPTION_KEY environment variable, not in the codebase.
"""

from django.db import models
from django.utils import timezone

from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.search import index
from .fields import EncryptedCharField, EncryptedTextField


VISIT_REASON_CHOICES = [
    ("initial_screening", "Initial Screening"),
    ("follow_up", "Follow-Up"),
    ("breast_health", "Breast Health"),
    ("full_body", "Full Body Scan"),
    ("pain_inflammation", "Pain / Inflammation"),
    ("other", "Other"),
]


class Client(index.Indexed, models.Model):
    """
    A client record with encrypted personal information.

    The owner manages clients from Wagtail admin → Snippets → Clients.
    All PII fields are Fernet-encrypted in the database.
    """

    # ── Encrypted PII fields ──────────────────────────────
    name = EncryptedCharField(
        max_length=200,
        help_text="Client's full name (encrypted at rest).",
    )

    phone = EncryptedCharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Phone number (encrypted at rest).",
    )

    email = EncryptedCharField(
        max_length=254,
        blank=True,
        default="",
        help_text="Email address (encrypted at rest).",
    )

    # ── Non-encrypted fields ──────────────────────────────
    clinic_location = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Which clinic location this client visits (e.g. 'Nanaimo', 'Victoria Pop-Up').",
    )

    previous_visit_reason = models.CharField(
        max_length=50,
        choices=VISIT_REASON_CHOICES,
        blank=True,
        default="",
        help_text="Reason for the most recent visit.",
    )

    last_appointment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of the client's most recent appointment.",
    )

    notes = EncryptedTextField(
        blank=True,
        default="",
        help_text="Internal notes about this client (encrypted at rest).",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("name"),
                FieldPanel("phone"),
                FieldPanel("email"),
            ],
            heading="Client Contact Info (encrypted)",
        ),
        MultiFieldPanel(
            [
                FieldPanel("clinic_location"),
                FieldPanel("previous_visit_reason"),
                FieldPanel("last_appointment_date"),
            ],
            heading="Visit Details",
        ),
        FieldPanel("notes"),
    ]

    search_fields = [
        # NOTE: encrypted fields cannot be searched via Wagtail search
        # because the DB stores ciphertext. Use the admin list filter
        # and the client name column (decrypted in Python) instead.
        index.FilterField("clinic_location"),
        index.FilterField("previous_visit_reason"),
        index.FilterField("last_appointment_date"),
    ]

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self):
        return self.name or f"Client #{self.pk}"


REPORT_STATUS_CHOICES = [
    ("pending", "Pending — not yet sent"),
    ("sent", "Sent to client"),
    ("reviewed", "Report review completed"),
]


class ClientReport(models.Model):
    """
    A thermography report linked to a client.

    When the report arrives, the owner uploads it here and sends
    the delivery email (with an optional 'Book a Report Review' link)
    via the admin interface.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="reports",
        help_text="The client this report belongs to.",
    )

    report_date = models.DateField(
        default=timezone.localdate,
        help_text="Date the report was generated / received.",
    )

    status = models.CharField(
        max_length=20,
        choices=REPORT_STATUS_CHOICES,
        default="pending",
        help_text="Track whether the report has been sent and/or reviewed.",
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="When the report delivery email was sent.",
    )

    notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal notes about this report.",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel("client"),
        FieldPanel("report_date"),
        FieldPanel("status"),
        FieldPanel("notes"),
    ]

    class Meta:
        ordering = ["-report_date", "-created_at"]
        verbose_name = "Client Report"
        verbose_name_plural = "Client Reports"

    def __str__(self):
        client_name = self.client.name if self.client_id else "Unknown"
        return f"Report for {client_name} — {self.report_date}"

    def status_badge(self):
        """HTML status badge for the admin listing."""
        from django.utils.html import format_html
        colours = {
            "pending": ("⏳ Pending", "#856404", "#fff3cd"),
            "sent": ("✉️ Sent", "#155724", "#d4edda"),
            "reviewed": ("✅ Reviewed", "#004085", "#cce5ff"),
        }
        label, fg, bg = colours.get(self.status, ("Unknown", "#333", "#eee"))
        return format_html(
            '<span style="color:{}; background:{}; padding:2px 8px; '
            'border-radius:4px; font-size:0.8rem; font-weight:600;">{}</span>',
            fg, bg, label,
        )
    status_badge.short_description = "Status"


