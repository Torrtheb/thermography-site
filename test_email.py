"""Quick email test — run with: railway run .venv/bin/python test_email.py"""
import django, os, socket

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "thermography_site.settings.production")
django.setup()

from django.core.mail import send_mail
from django.conf import settings

# Test raw TCP
print("Testing SMTP connectivity...")
try:
    sock = socket.create_connection(("smtp-relay.brevo.com", 587), timeout=10)
    print("TCP connection to smtp-relay.brevo.com:587 OK")
    sock.close()
except Exception as e:
    print(f"TCP connection FAILED: {e}")

print(f"EMAIL_HOST={settings.EMAIL_HOST}")
print(f"EMAIL_PORT={settings.EMAIL_PORT}")
print(f"EMAIL_TIMEOUT={getattr(settings, 'EMAIL_TIMEOUT', 'not set')}")
print(f"FROM={settings.DEFAULT_FROM_EMAIL}")

print("Sending test email...")
try:
    send_mail(
        "Test #2 from Thermography site",
        "This is a test to verify email delivery from the app.",
        settings.DEFAULT_FROM_EMAIL,
        ["admin@thermographyvancouverisland.com"],
        fail_silently=False,
    )
    print("SUCCESS - Email sent!")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
