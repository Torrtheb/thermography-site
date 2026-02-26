import hashlib
import uuid

from django.db import models
from django.utils import timezone


class NewsletterSubscriber(models.Model):
    """Stores newsletter/mailing-list subscribers."""

    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to unsubscribe this address.",
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Secret token for one-click unsubscribe links.",
    )
    ip_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of the subscriber's IP for rate limiting.",
    )

    class Meta:
        ordering = ["-subscribed_at"]
        verbose_name = "Newsletter subscriber"
        verbose_name_plural = "Newsletter subscribers"

    def __str__(self):
        status = "active" if self.is_active else "unsubscribed"
        return f"{self.email} ({status})"


class NewsletterCampaign(models.Model):
    """
    Record of a newsletter sent from the Wagtail admin.
    Keeps a full audit trail of what was sent, when, and to how many people.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("partial", "Partially Sent"),
        ("failed", "Failed"),
    ]

    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Plain-text body of the newsletter.")
    sign_off = models.TextField(
        blank=True,
        default="",
        help_text="Closing text appended after the body.",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    recipients_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Not used — kept for future audit trail.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Newsletter campaign"
        verbose_name_plural = "Newsletter campaigns"

    def __str__(self):
        return f"{self.subject} ({self.get_status_display()}, {self.sent_at or 'not sent'})"

    def status_badge(self):
        """HTML badge for use in admin listings."""
        from django.utils.html import format_html

        colours = {
            "draft": "#6b7280",
            "sending": "#f59e0b",
            "sent": "#10b981",
            "partial": "#f97316",
            "failed": "#ef4444",
        }
        colour = colours.get(self.status, "#6b7280")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 10px; '
            'border-radius:9999px; font-size:0.8rem; font-weight:600;">{}</span>',
            colour,
            self.get_status_display(),
        )

    status_badge.short_description = "Status"


class SubscribeRateLimit(models.Model):
    """Simple DB-backed rate limiter to prevent spam submissions."""

    ip_hash = models.CharField(max_length=64, db_index=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["ip_hash", "attempted_at"]),
        ]

    @classmethod
    def is_rate_limited(cls, ip_address, max_attempts=5, window_minutes=60):
        """Return True if this IP has exceeded the attempt limit."""
        from datetime import timedelta

        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()
        cutoff = timezone.now() - timedelta(minutes=window_minutes)
        recent = cls.objects.filter(ip_hash=ip_hash, attempted_at__gte=cutoff).count()
        return recent >= max_attempts

    @classmethod
    def record_attempt(cls, ip_address):
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()
        cls.objects.create(ip_hash=ip_hash)
        # Periodic cleanup: delete records older than 24 hours
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
        cls.objects.filter(attempted_at__lt=cutoff).delete()
        return ip_hash
