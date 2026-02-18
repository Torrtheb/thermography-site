"""
Production settings — loaded when DJANGO_SETTINGS_MODULE=thermography_site.settings.production

All secrets and host-specific values come from environment variables.
See .env.example for the full list.
"""

import os

import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False

# ──────────────────────────────────────────────────────────
# Secrets & hosts
# ──────────────────────────────────────────────────────────
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # REQUIRED — will crash on startup if missing

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# ──────────────────────────────────────────────────────────
# Database — Neon PostgreSQL (or any DATABASE_URL provider)
# Neon requires SSL; dj-database-url handles the full URL.
# ──────────────────────────────────────────────────────────
if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,  # Neon requires SSL connections
        )
    }

# ──────────────────────────────────────────────────────────
# HTTPS / security headers
# ──────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ──────────────────────────────────────────────────────────
# Static files — served by WhiteNoise (no separate web server needed)
# ──────────────────────────────────────────────────────────
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES["staticfiles"][
    "BACKEND"
] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ──────────────────────────────────────────────────────────
# Media files — Google Cloud Storage (for Wagtail image/document uploads)
# ──────────────────────────────────────────────────────────
if os.environ.get("GS_BUCKET_NAME"):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
    }
    GS_BUCKET_NAME = os.environ["GS_BUCKET_NAME"]
    # Keep object ACLs disabled so this works with Uniform bucket-level access.
    GS_DEFAULT_ACL = None
    GS_QUERYSTRING_AUTH = False  # cleaner URLs, no signed tokens
    GS_FILE_OVERWRITE = False  # prevent accidental overwrites
    GS_OBJECT_PARAMETERS = {"cache_control": "public, max-age=86400"}
    MEDIA_URL = f"https://storage.googleapis.com/{GS_BUCKET_NAME}/"

    # On Cloud Run, authentication is automatic via the service account.
    # No credentials file needed — it uses the attached SA identity.
    # To test locally, set GOOGLE_APPLICATION_CREDENTIALS env var pointing
    # to a service account JSON key file.

# ──────────────────────────────────────────────────────────
# Fallback: S3-compatible object storage (AWS S3, Cloudflare R2, etc.)
# ──────────────────────────────────────────────────────────
elif os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    }
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    MEDIA_URL = (
        f"https://{AWS_S3_CUSTOM_DOMAIN}/" if AWS_S3_CUSTOM_DOMAIN
        else f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"
    )

# ──────────────────────────────────────────────────────────
# Email (SMTP for contact form)
# ──────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

# ──────────────────────────────────────────────────────────
# Analytics — GoatCounter site code (e.g. "mythermography")
# Injected into templates via context processor
# ──────────────────────────────────────────────────────────
GOATCOUNTER_SITE_CODE = os.environ.get("GOATCOUNTER_SITE_CODE", "")

# ──────────────────────────────────────────────────────────
# Wagtail
# ──────────────────────────────────────────────────────────
WAGTAILADMIN_BASE_URL = os.environ.get("WAGTAILADMIN_BASE_URL", "https://example.com")

# ──────────────────────────────────────────────────────────
# Logging — surface errors in platform logs
# ──────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
