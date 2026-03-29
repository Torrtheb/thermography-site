"""
Client database — encrypted PII managed from Wagtail admin.

All personal fields (name, phone, email) are encrypted at rest using
Fernet symmetric encryption.  The encryption key is stored in the
FIELD_ENCRYPTION_KEY environment variable, not in the codebase.

An SHA-256 hash of the lowercase email is stored alongside the encrypted
email so that client lookups by email (e.g. from Cal.com webhooks) can
be done in O(1) via a DB query instead of decrypting every row.
"""

import hashlib
from decimal import Decimal

from django.db import models
from django.utils import timezone

from wagtail.admin.panels import FieldPanel, FieldRowPanel, MultiFieldPanel
from wagtail.search import index
from .fields import EncryptedCharField, EncryptedTextField


def _hash_email(email: str) -> str:
    """Return a stable SHA-256 hex digest for a lowercased email."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


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

    email_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        editable=False,
        help_text="SHA-256 hash of lowercased email for O(1) lookups.",
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

    def save(self, **kwargs):
        new_hash = _hash_email(self.email) if self.email else ""
        if self.email_hash != new_hash:
            self.email_hash = new_hash
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = list(kwargs["update_fields"]) + ["email_hash"]
        super().save(**kwargs)

    @classmethod
    def find_by_email(cls, email: str):
        """Look up a client by email using the indexed hash (O(1))."""
        h = _hash_email(email)
        return cls.objects.filter(email_hash=h).first()

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

    notes = EncryptedTextField(
        blank=True,
        default="",
        help_text="Internal notes about this report (encrypted at rest).",
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


# ──────────────────────────────────────────────────────────
# Booking Deposit tracking
# ──────────────────────────────────────────────────────────

DEPOSIT_STATUS_CHOICES = [
    ("awaiting_review", "Awaiting Review — owner must approve"),
    ("pending", "Pending — deposit request sent, awaiting payment"),
    ("received", "Received — deposit paid"),
    ("confirmed", "Confirmed — booking confirmed in Cal.com"),
    ("forfeited", "Forfeited — client cancelled / no-show"),
    ("applied", "Applied to service fee"),
    ("refunded", "Refunded (exception)"),
]

DEPOSIT_METHOD_CHOICES = [
    ("etransfer", "e-Transfer"),
    ("cash", "Cash"),
    ("cheque", "Cheque"),
]


class Deposit(index.Indexed, models.Model):
    """
    Tracks a non-refundable booking deposit payment.

    The owner creates a deposit record when a client books, then marks it
    as received once payment arrives. On the day of the appointment the
    deposit is applied toward the service fee.

    Managed from Wagtail admin → sidebar → Deposits.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="deposits",
        help_text="The client this deposit belongs to.",
    )

    amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("25.00"),
        help_text="Deposit amount ($).",
    )

    appointment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of the booked appointment this deposit is for.",
    )

    service_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Service booked (auto-filled from Cal.com webhook).",
    )

    status = models.CharField(
        max_length=20,
        choices=DEPOSIT_STATUS_CHOICES,
        default="awaiting_review",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=DEPOSIT_METHOD_CHOICES,
        blank=True,
        default="",
        help_text="How the client paid (fill in when deposit is received).",
    )

    received_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the deposit payment was actually received.",
    )

    reference = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="e-Transfer confirmation number, cheque number, or other reference.",
    )

    deposit_request_sent = models.BooleanField(
        default=False,
        help_text="Whether the deposit request email has been sent to the client.",
    )

    deposit_confirmed_sent = models.BooleanField(
        default=False,
        help_text="Whether the deposit confirmation email has been sent.",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="When the owner approved the booking and sent the deposit request. The 48-hour clock starts here.",
    )

    cal_booking_uid = models.CharField(
        max_length=200,
        blank=True,
        default="",
        db_index=True,
        help_text="Cal.com booking UID (auto-filled by webhook). Used to link cancellations.",
    )

    notes = EncryptedTextField(
        blank=True,
        default="",
        help_text="Internal notes (encrypted at rest).",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("client"),
                FieldPanel("appointment_date"),
                FieldPanel("service_name"),
                FieldPanel("amount"),
            ],
            heading="Booking Details",
        ),
        MultiFieldPanel(
            [
                FieldPanel("status"),
                FieldRowPanel([
                    FieldPanel("payment_method"),
                    FieldPanel("received_date"),
                ]),
                FieldPanel("reference"),
            ],
            heading="Payment Status",
        ),
        MultiFieldPanel(
            [
                FieldPanel("deposit_request_sent"),
                FieldPanel("deposit_confirmed_sent"),
            ],
            heading="Email Status",
        ),
        FieldPanel("cal_booking_uid"),
        FieldPanel("notes"),
    ]

    search_fields = [
        index.FilterField("status"),
        index.FilterField("appointment_date"),
        index.FilterField("payment_method"),
        index.FilterField("received_date"),
        index.FilterField("deposit_request_sent"),
    ]

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Deposit"
        verbose_name_plural = "Deposits"

    def __str__(self):
        client_name = self.client.name if self.client_id else "Unknown"
        date_str = self.appointment_date.isoformat() if self.appointment_date else "no date"
        return f"${self.amount} deposit — {client_name} ({date_str})"

    def client_name_display(self):
        return self.client.name if self.client_id else "Unknown"
    client_name_display.short_description = "Client"

    def client_email_display(self):
        return self.client.email if self.client_id else "—"
    client_email_display.short_description = "Email"

    def status_and_actions(self):
        """Combined status badge + contextual action buttons for the admin listing."""
        from django.utils.safestring import mark_safe

        badge_styles = {
            "awaiting_review": ("🔍 Needs Review", "#6d28d9", "#ede9fe"),
            "pending":         ("⏳ Awaiting Deposit", "#856404", "#fff3cd"),
            "received":        ("💰 Deposit Received", "#155724", "#d4edda"),
            "confirmed":       ("✅ Booked", "#004085", "#cce5ff"),
            "forfeited":       ("🚫 Forfeited", "#721c24", "#f8d7da"),
            "applied":         ("💰 Applied", "#065f46", "#d1fae5"),
            "refunded":        ("↩️ Refunded", "#6c757d", "#e2e3e5"),
        }
        label, fg, bg = badge_styles.get(self.status, ("Unknown", "#333", "#eee"))
        badge = (
            f'<span style="color:{fg}; background:{bg}; padding:2px 8px; '
            f'border-radius:4px; font-size:0.8rem; font-weight:600; '
            f'white-space:nowrap;">{label}</span>'
        )

        btn = (
            'display:inline-block; padding:3px 8px; border-radius:4px; '
            'font-size:0.75rem; font-weight:600; border:none; cursor:pointer; '
            'white-space:nowrap;'
        )

        def _post_button(url, text, bg_color, confirm_msg=""):
            onclick = f"return confirm('{confirm_msg}');" if confirm_msg else ""
            return (
                f'<form method="post" action="{url}" style="display:inline;">'
                f'<input type="hidden" name="csrfmiddlewaretoken" '
                f'value="" class="js-csrf-token-placeholder">'
                f'<button type="submit" style="color:#fff; background:{bg_color}; {btn}" '
                f'{f"onclick={chr(34)}{onclick}{chr(34)}" if onclick else ""}>'
                f'{text}</button></form>'
            )

        reject_btn = _post_button(
            f"/admin/deposits/{self.pk}/reject/",
            "❌ Reject", "#dc2626",
            confirm_msg="Reject this booking and cancel in Cal.com?",
        )

        actions = ""
        if self.status == "awaiting_review":
            actions = (
                _post_button(
                    f"/admin/deposits/{self.pk}/approve/",
                    "✅ Approve &amp; Send", "#6d28d9",
                )
                + " " + reject_btn
            )
        elif self.status == "pending":
            actions = (
                _post_button(
                    f"/admin/deposits/{self.pk}/mark-received/",
                    "💰 Mark Received", "#2563eb",
                )
                + " " + reject_btn
            )
        elif self.status == "received":
            actions = _post_button(
                f"/admin/deposits/{self.pk}/send-confirmation/",
                "✅ Confirm Booking", "#059669",
            )

        if actions:
            return mark_safe(
                f'<div style="display:flex; flex-direction:column; gap:6px;">'
                f'{badge}<div style="display:flex; flex-wrap:wrap; gap:4px;">{actions}</div></div>'
            )
        return mark_safe(badge)
    status_and_actions.short_description = "Status"


