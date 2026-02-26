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

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models, IntegrityError
from django.db.models import F
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.utils import timezone

from modelcluster.fields import ParentalKey
from wagtail.models import Page, Orderable
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel

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

    @classmethod
    def check_and_increment(cls, ip_hash: str, window_key: int, limit: int) -> bool:
        """Atomically check rate limit and record the attempt.

        Returns True if the request is allowed (under *limit*), False if blocked.
        Combines the check and increment into one step to close the TOCTOU race
        that existed when ``get_count`` and ``increment`` were called separately.
        """
        # Try to atomically increment an existing counter that is still below the limit.
        updated = cls.objects.filter(
            ip_hash=ip_hash, window_key=window_key, submission_count__lt=limit,
        ).update(
            submission_count=F("submission_count") + 1,
            updated_at=timezone.now(),
        )
        if updated:
            # Cleanup old windows periodically
            keep_windows = (7 * 24 * 3600) // CONTACT_RATE_WINDOW
            cls.objects.filter(window_key__lt=window_key - keep_windows).delete()
            return True

        # Either no row yet (first request in window) or already at/above limit.
        if cls.objects.filter(ip_hash=ip_hash, window_key=window_key).exists():
            return False  # Already at or above the limit

        # First submission in this window — create the row.
        try:
            cls.objects.create(ip_hash=ip_hash, window_key=window_key, submission_count=1)
            return True
        except IntegrityError:
            # Concurrent insert won the race; try to increment the new row.
            updated = cls.objects.filter(
                ip_hash=ip_hash, window_key=window_key, submission_count__lt=limit,
            ).update(
                submission_count=F("submission_count") + 1,
                updated_at=timezone.now(),
            )
            return bool(updated)


class ContactSubmission(models.Model):
    """
    Stores every contact-form submission in the database.
    Acts as a permanent record — email delivery may fail, but
    the submission is always saved here.
    """

    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    email_sent = models.BooleanField(
        default=False,
        help_text="Whether the notification email was delivered successfully.",
    )
    ip_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash of the submitter's IP (for rate-limit auditing).",
    )

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Contact Submission"
        verbose_name_plural = "Contact Submissions"

    def __str__(self):
        return f"{self.name} — {self.submitted_at:%Y-%m-%d %H:%M}"


class Location(Orderable):
    """
    A location the business operates from.
    Linked to ContactPage via InlinePanel.
    The owner can toggle visibility on/off as their travel schedule changes.
    """

    page = ParentalKey(
        "contact.ContactPage",
        on_delete=models.CASCADE,
        related_name="locations",
    )

    name = models.CharField(
        max_length=200,
        help_text="Location name, e.g. 'Victoria — Main Office' or 'Nanaimo'.",
    )

    address = models.TextField(
        help_text="Full street address.",
    )

    description = models.CharField(
        max_length=300,
        blank=True,
        help_text="Short note, e.g. 'Available March–May 2026' or 'By appointment only'.",
    )

    map_embed_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Google Maps embed URL (optional).",
    )

    is_primary = models.BooleanField(
        default=False,
        help_text="Mark as the primary / home location (shown first).",
    )

    is_visible = models.BooleanField(
        default=True,
        help_text="Show this location on the contact page. Uncheck to hide temporarily.",
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("address"),
        FieldPanel("description"),
        FieldPanel("map_embed_url"),
        FieldPanel("is_primary"),
        FieldPanel("is_visible"),
    ]

    class Meta(Orderable.Meta):
        verbose_name = "Location"
        verbose_name_plural = "Locations"

    def __str__(self):
        return self.name


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
            ],
            heading="Contact Details",
        ),
        InlinePanel("locations", label="Location", heading="Locations"),
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

    @property
    def visible_locations(self):
        """Return visible locations, primary first, then by sort_order."""
        return self.locations.filter(is_visible=True).order_by("-is_primary", "sort_order")

    @property
    def primary_location(self):
        """Return the primary location (or None)."""
        return self.locations.filter(is_visible=True, is_primary=True).first()

    @property
    def travel_locations(self):
        """Return visible non-primary locations, ordered by sort_order."""
        return self.locations.filter(is_visible=True, is_primary=False).order_by("sort_order")

    def serve(self, request):
        """Handle GET (show form) and POST (send email)."""
        form_submitted = False
        form_error = ""

        if request.method == "POST" and self.contact_form_enabled:
            # ── Rate limiting ──
            # Use the rightmost XFF value (appended by the trusted proxy);
            # an attacker can prepend fake values but cannot control the last one.
            xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
            if xff:
                ip = xff.split(",")[-1].strip()
            else:
                ip = request.META.get("REMOTE_ADDR", "")
            ip_hash = ContactSubmissionRateLimit.hash_ip(ip or "unknown")
            window_key = ContactSubmissionRateLimit.current_window_key()

            # Atomic check-and-increment to prevent race conditions under concurrency.
            if not ContactSubmissionRateLimit.check_and_increment(ip_hash, window_key, CONTACT_RATE_LIMIT):
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

            # Honeypot check — hidden field that bots fill in
            honeypot = request.POST.get("website", "")
            if honeypot:
                # Bot detected — pretend success so it doesn't retry
                return TemplateResponse(
                    request,
                    self.get_template(request),
                    self.get_context(request) | {
                        "form_submitted": True,
                        "form_error": "",
                    },
                )

            # Validate email format server-side
            email_valid = True
            try:
                validate_email(email)
            except ValidationError:
                email_valid = False

            if name and email and email_valid and message:
                # Always save to database first — messages are never lost.
                submission = ContactSubmission.objects.create(
                    name=name,
                    email=email,
                    phone=phone,
                    message=message,
                    ip_hash=ip_hash,
                )

                try:
                    plain_message = (
                        f"Name: {name}\n"
                        f"Email: {email}\n"
                        f"Phone: {phone or 'Not provided'}\n\n"
                        f"Message:\n{message}"
                    )

                    # Try HTML template; fall back to plain text
                    try:
                        html_message = render_to_string(
                            "contact/emails/notification.html",
                            {"name": name, "email": email, "phone": phone, "message": message},
                        )
                    except Exception:
                        html_message = None

                    email_msg = EmailMessage(
                        subject=f"Contact form: {name}",
                        body=html_message or plain_message,
                        from_email=None,  # uses DEFAULT_FROM_EMAIL
                        to=[self.contact_email],
                        reply_to=[email],  # reply goes to the person who submitted
                    )
                    if html_message:
                        email_msg.content_subtype = "html"
                    email_msg.send(fail_silently=False)

                    submission.email_sent = True
                    submission.save(update_fields=["email_sent"])
                except Exception:
                    pass  # Email failed, but submission is saved in DB.

                form_submitted = True
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
