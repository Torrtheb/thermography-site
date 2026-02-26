"""
Development settings — the default when running locally via manage.py.
"""

import os

from .base import *  # noqa: F401,F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: this key is for local development only.
SECRET_KEY = "django-insecure-jb0uck8i)g^^x^t3j4+*h$fdc+2jm83k=yma*v^+(yhp&v0fie"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# ──────────────────────────────────────────────────────────
# Email — use real SMTP if credentials are in .env, else console
# To test with real emails: add EMAIL_HOST_USER and BREVO_SMTP_KEY to .env
# ──────────────────────────────────────────────────────────
if os.environ.get("EMAIL_HOST_USER") and os.environ.get("BREVO_SMTP_KEY"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp-relay.brevo.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ["EMAIL_HOST_USER"]
    EMAIL_HOST_PASSWORD = os.environ["BREVO_SMTP_KEY"]
    DEFAULT_FROM_EMAIL = os.environ.get(
        "DEFAULT_FROM_EMAIL", EMAIL_HOST_USER
    )
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "noreply@localhost"

# ──────────────────────────────────────────────────────────
# Analytics — GoatCounter (optional in dev, set in .env to test)
# ──────────────────────────────────────────────────────────
GOATCOUNTER_SITE_CODE = os.environ.get("GOATCOUNTER_SITE_CODE", "")

# ──────────────────────────────────────────────────────────
# Brevo Contacts API (optional in dev, set in .env to test)
# ──────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_LIST_ID = os.environ.get("BREVO_LIST_ID", "")

# ──────────────────────────────────────────────────────────
# CSP — disabled in development (no CONTENT_SECURITY_POLICY set)
# The CSPMiddleware is a no-op when the setting is absent.
# ──────────────────────────────────────────────────────────
CONTENT_SECURITY_POLICY = None


try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
