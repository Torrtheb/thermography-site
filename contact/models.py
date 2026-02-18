"""
Contact app — a single page with contact info and an optional contact form.

The owner can edit contact details (email, phone, address) and toggle
the contact form on/off from the admin.

When a visitor submits the form, an email is sent to the contact_email address.
In development, emails print to the terminal (console backend).

Page hierarchy:
  Root Page
    └── Contact  ← ContactPage (only one)
"""

import hashlib

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models, IntegrityError
from django.db.models import F
from django.core.mail import send_mail
from django.template.response import TemplateResponse
from django.utils import timezone

from wagtail.models import Page
from wagtail.admin.panels import FieldPanel, MultiFieldPanel

# Rate-limit: max 3 contact-form submissions per IP per 10 minutes
CONTACT_RATE_LIMIT = 3
CONTACT_RATE_WINDOW = 600  # seconds


class ContactSubmissionRateLimit(models.Model):
    """
    Shared rate-limit counter backed by the main database.

    Stores hashed client IP + time window key, so limits work across
    all Cloud Run instances without an external cache service.
    """

    ip_hash = models.CharField(max_length=64, db_index=True)
    window_key = models.BigIntegerField(db_index=True)
    submission_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ip_hash", "window_key"],
                name="uniq_contact_rate_ip_window",
            ),
        ]

    @classmethod
    def hash_ip(cls, ip: str) -> str:
        return hashlib.sha256(ip.encode("utf-8")).hexdigest()

    @classmethod
    def current_window_key(cls) -> int:
        return int(timezone.now().timestamp()) // CONTACT_RATE_WINDOW

    @classmethod
    def get_count(cls, ip_hash: str, window_key: int) -> int:
        return (
            cls.objects.filter(ip_hash=ip_hash, window_key=window_key)
            .values_list("submission_count", flat=True)
            .first()
            or 0
        )

    @classmethod
    def increment(cls, ip_hash: str, window_key: int) -> None:
        updated = cls.objects.filter(
            ip_hash=ip_hash, window_key=window_key
        ).update(
            submission_count=F("submission_count") + 1,
            updated_at=timezone.now(),
        )
        if not updated:
            try:
                cls.objects.create(
                    ip_hash=ip_hash,
                    window_key=window_key,
                    submission_count=1,
                )
            except IntegrityError:
                # Concurrent create won the race; increment existing row.
                cls.objects.filter(
                    ip_hash=ip_hash, window_key=window_key
                ).update(
                    submission_count=F("submission_count") + 1,
                    updated_at=timezone.now(),
                )

        # Basic cleanup: keep roughly the last 7 days of buckets.
        keep_windows = (7 * 24 * 3600) // CONTACT_RATE_WINDOW
        cls.objects.filter(window_key__lt=window_key - keep_windows).delete()


class ContactPage(Page):
    """
    The Contact page at /contact/.
    Shows contact details and optionally a contact form.
    max_count = 1: only one contact page.
    """

    intro = models.TextField(
        blank=True,
        help_text="Optional intro text above the contact info.",
    )

    contact_email = models.EmailField(
        help_text="Public contact email address.",
    )

    contact_phone = models.CharField(
        max_length=30,
        help_text="Public phone number.",
    )

    address = models.TextField(
        blank=True,
        help_text="Business address (optional).",
    )

    map_embed_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Google Maps embed URL (optional). Use the 'Embed a map' URL from Google Maps.",
    )

    contact_form_enabled = models.BooleanField(
        default=True,
        help_text="Show the contact form on the page.",
    )

    facebook_url = models.URLField(
        blank=True,
        help_text="Facebook page URL (optional). e.g. https://facebook.com/yourbusiness",
    )

    instagram_url = models.URLField(
        blank=True,
        help_text="Instagram profile URL (optional). e.g. https://instagram.com/yourbusiness",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        MultiFieldPanel(
            [
                FieldPanel("contact_email"),
                FieldPanel("contact_phone"),
                FieldPanel("address"),
            ],
            heading="Contact Details",
        ),
        FieldPanel("map_embed_url"),
        FieldPanel("contact_form_enabled"),
        MultiFieldPanel(
            [
                FieldPanel("facebook_url"),
                FieldPanel("instagram_url"),
            ],
            heading="Social Media (optional)",
        ),
    ]

    max_count = 1

    def serve(self, request):
        """Handle GET (show form) and POST (send email)."""
        form_submitted = False
        form_error = ""

        if request.method == "POST" and self.contact_form_enabled:
            # ── Rate limiting ──
            ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0].strip()
            ip_hash = ContactSubmissionRateLimit.hash_ip(ip or "unknown")
            window_key = ContactSubmissionRateLimit.current_window_key()

            # Shared (database-backed) limiter for multi-instance deployments.
            submissions = ContactSubmissionRateLimit.get_count(ip_hash, window_key)
            if submissions >= CONTACT_RATE_LIMIT:
                form_error = "Too many submissions. Please try again later."
                return TemplateResponse(
                    request,
                    self.get_template(request),
                    self.get_context(request) | {
                        "form_submitted": False,
                        "form_error": form_error,
                    },
                )

            name = request.POST.get("name", "").strip()[:200]
            email = request.POST.get("email", "").strip()[:254]
            phone = request.POST.get("phone", "").strip()[:30]
            message = request.POST.get("message", "").strip()[:5000]

            # Validate email format server-side
            email_valid = True
            try:
                validate_email(email)
            except ValidationError:
                email_valid = False

            if name and email and email_valid and message:
                try:
                    send_mail(
                        subject=f"Contact form: {name}",
                        message=(
                            f"Name: {name}\n"
                            f"Email: {email}\n"
                            f"Phone: {phone or 'Not provided'}\n\n"
                            f"Message:\n{message}"
                        ),
                        from_email=None,  # uses DEFAULT_FROM_EMAIL
                        recipient_list=[self.contact_email],
                        fail_silently=False,
                    )
                    form_submitted = True
                    ContactSubmissionRateLimit.increment(ip_hash, window_key)
                except Exception:
                    form_error = "Sorry, there was a problem sending your message. Please try again or contact us directly."
            elif not email_valid:
                form_error = "Please enter a valid email address."
            else:
                form_error = "Please fill in all required fields."

        return TemplateResponse(
            request,
            self.get_template(request),
            self.get_context(request) | {
                "form_submitted": form_submitted,
                "form_error": form_error,
            },
        )

    class Meta:
        verbose_name = "Contact Page"
