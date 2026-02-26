"""
Management command to test all email flows.

Usage:
    # Console backend (default dev — prints to terminal):
    python manage.py test_email your@email.com

    # Real SMTP (requires EMAIL_HOST_USER + BREVO_SMTP_KEY in .env):
    python manage.py test_email your@email.com

    # Test specific flow only:
    python manage.py test_email your@email.com --flow welcome
    python manage.py test_email your@email.com --flow contact
    python manage.py test_email your@email.com --flow newsletter
    python manage.py test_email your@email.com --flow all
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string


class Command(BaseCommand):
    help = "Send test emails to verify SMTP configuration and all email flows."

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            help="Recipient email address for test emails.",
        )
        parser.add_argument(
            "--flow",
            choices=["all", "basic", "welcome", "contact", "newsletter"],
            default="all",
            help="Which email flow to test (default: all).",
        )

    def handle(self, *args, **options):
        email = options["email"]
        flow = options["flow"]
        backend = settings.EMAIL_BACKEND
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO(" Email Configuration Test"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(f"  Backend:    {backend}")
        self.stdout.write(f"  From:       {from_email}")
        self.stdout.write(f"  To:         {email}")

        if "smtp" in backend.lower():
            self.stdout.write(f"  SMTP Host:  {getattr(settings, 'EMAIL_HOST', 'N/A')}")
            self.stdout.write(f"  SMTP Port:  {getattr(settings, 'EMAIL_PORT', 'N/A')}")
            self.stdout.write(f"  SMTP User:  {getattr(settings, 'EMAIL_HOST_USER', 'N/A')}")
            self.stdout.write(self.style.SUCCESS("  → Using REAL SMTP — emails will be delivered!"))
        else:
            self.stdout.write(self.style.WARNING("  → Using console backend — emails print below."))

        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write("")

        results = []

        if flow in ("all", "basic"):
            results.append(("Basic send_mail", self._test_basic(email, from_email)))

        if flow in ("all", "welcome"):
            results.append(("Newsletter welcome", self._test_welcome(email)))

        if flow in ("all", "contact"):
            results.append(("Contact notification", self._test_contact(email, from_email)))

        if flow in ("all", "newsletter"):
            results.append(("Newsletter campaign", self._test_newsletter(email, from_email)))

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO(" Results"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        for name, success in results:
            status = self.style.SUCCESS("✓ PASS") if success else self.style.ERROR("✗ FAIL")
            self.stdout.write(f"  {status}  {name}")
        self.stdout.write("")

    def _test_basic(self, email, from_email):
        """Test 1: Simple plain-text email via send_mail."""
        self.stdout.write("1) Testing basic send_mail...")
        try:
            send_mail(
                subject="[TEST] Basic Email — Thermography",
                message=(
                    "This is a basic test email from your Thermography site.\n\n"
                    "If you're reading this, your email configuration is working!\n\n"
                    "— Thermography Test Suite"
                ),
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS("   → Sent successfully!"))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   → FAILED: {e}"))
            return False

    def _test_welcome(self, email):
        """Test 2: Newsletter welcome email (with HTML template)."""
        self.stdout.write("2) Testing newsletter welcome email...")
        try:
            from newsletter.email import send_welcome_email

            result = send_welcome_email(email)
            if result:
                self.stdout.write(self.style.SUCCESS("   → Sent successfully!"))
            else:
                self.stdout.write(self.style.ERROR("   → send_welcome_email returned False"))
            return result
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   → FAILED: {e}"))
            return False

    def _test_contact(self, email, from_email):
        """Test 3: Contact form notification email (with HTML template)."""
        self.stdout.write("3) Testing contact form notification email...")
        try:
            from django.core.mail import EmailMessage

            plain_message = (
                "Name: Test User\n"
                "Email: test@example.com\n"
                "Phone: 555-0123\n\n"
                "Message:\nThis is a test contact form submission."
            )

            try:
                html_message = render_to_string(
                    "contact/emails/notification.html",
                    {
                        "name": "Test User",
                        "email": "test@example.com",
                        "phone": "555-0123",
                        "message": "This is a test contact form submission.\n\nIt can have multiple paragraphs.",
                    },
                )
            except Exception:
                html_message = None

            msg = EmailMessage(
                subject="[TEST] Contact Form — Thermography",
                body=html_message or plain_message,
                from_email=from_email,
                to=[email],
                reply_to=["test@example.com"],
            )
            if html_message:
                msg.content_subtype = "html"
            msg.send(fail_silently=False)

            self.stdout.write(self.style.SUCCESS("   → Sent successfully!"))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   → FAILED: {e}"))
            return False

    def _test_newsletter(self, email, from_email):
        """Test 4: Newsletter-style email (plain text, like a real campaign)."""
        self.stdout.write("4) Testing newsletter campaign email...")
        try:
            send_mail(
                subject="[TEST] Newsletter Campaign — Thermography",
                message=(
                    "Hi there!\n\n"
                    "This is a test newsletter from your Thermography site.\n\n"
                    "In a real campaign this would contain your wellness tips, "
                    "thermography insights, and clinic updates.\n\n"
                    "Best regards,\n"
                    "Your Thermography Team"
                ),
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS("   → Sent successfully!"))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   → FAILED: {e}"))
            return False
