"""
Production settings — loaded when DJANGO_SETTINGS_MODULE=thermography_site.settings.production

All secrets and host-specific values come from environment variables.
See .env.example for the full list.
"""

import base64
import json
import os

import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False

# ──────────────────────────────────────────────────────────
# Secrets & hosts
# ──────────────────────────────────────────────────────────
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # REQUIRED — will crash on startup if missing

# Railway auto-injects RAILWAY_PUBLIC_DOMAIN (e.g. "myapp.up.railway.app").
# Use it as a fallback so you don't have to set ALLOWED_HOSTS manually.
_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
]
if _railway_domain and _railway_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_railway_domain)
# Railway healthcheck probes use this host header
if "healthcheck.railway.app" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("healthcheck.railway.app")

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
if _railway_domain:
    _railway_origin = f"https://{_railway_domain}"
    if _railway_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_railway_origin)

# ──────────────────────────────────────────────────────────
# Database — Neon PostgreSQL (or any DATABASE_URL provider)
# Neon requires SSL; dj-database-url handles the full URL.
# search_path is set at the role level (ALTER ROLE neondb_owner SET search_path TO public)
# because the Neon pooler doesn't support startup parameters.
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
# Caching — in-process memory cache for rendered pages
# Eliminates repeated DB queries for anonymous visitors.
# Cache is per-worker and resets on each deploy.
# ──────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "thermography-prod",
        "TIMEOUT": 600,  # 10 minutes
    }
}

# Cache anonymous page views (bypass cache for logged-in users / admin)
MIDDLEWARE.insert(0, "django.middleware.cache.UpdateCacheMiddleware")
MIDDLEWARE.append("django.middleware.cache.FetchFromCacheMiddleware")
CACHE_MIDDLEWARE_SECONDS = 600  # 10 min
CACHE_MIDDLEWARE_KEY_PREFIX = "thermo"

# Persistent DB connections — avoids reconnecting on every request
# (Railway europe-west4 → Neon eu-central-1, ~5-10ms).
if DATABASES.get("default"):
    DATABASES["default"]["CONN_MAX_AGE"] = 600
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# ──────────────────────────────────────────────────────────
# HTTPS / security headers
# Railway (and most PaaS) terminates TLS at the edge proxy and forwards
# plain HTTP internally. The proxy sets X-Forwarded-Proto so Django
# knows the original request was HTTPS.  We do NOT set
# SECURE_SSL_REDIRECT because Railway's edge already redirects
# HTTP → HTTPS for external traffic, and internal healthchecks arrive
# over plain HTTP without X-Forwarded-Proto.
# ──────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Railway edge handles HTTPS redirect
SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ──────────────────────────────────────────────────────────
# Content Security Policy (CSP) — via django-csp
# Restricts which origins can load scripts, styles, frames, etc.
# ──────────────────────────────────────────────────────────
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "'unsafe-inline'",  # inline <script> blocks (AOS init, booking flow, etc.)
            "https://unpkg.com",  # AOS.js
            "https://gc.zgo.at",  # GoatCounter
            "https://*.goatcounter.com",  # GoatCounter beacon
        ],
        "style-src": [
            "'self'",
            "'unsafe-inline'",  # inline style= attributes throughout templates
            "https://unpkg.com",  # AOS CSS
        ],
        "img-src": [
            "'self'",
            "data:",  # inline SVG data URIs in CSS
            "https://storage.googleapis.com",  # GCS media
            "https://*.s3.amazonaws.com",  # S3 media fallback
        ],
        "font-src": ["'self'"],
        "frame-src": [
            "'self'",
            "https://cal.com",  # Cal.com booking embed
            "https://www.google.com",  # Google Maps embeds
            "https://*.goatcounter.com",  # GoatCounter admin dashboard
        ],
        "connect-src": [
            "'self'",
            "https://*.goatcounter.com",  # GoatCounter beacon
            "https://gc.zgo.at",  # GoatCounter script
        ],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'self'"],
    },
}

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
    # Public bucket — no signed URLs needed; images are served directly.
    # The bucket has allUsers:objectViewer for fast, cacheable image delivery.
    GS_QUERYSTRING_AUTH = False
    GS_FILE_OVERWRITE = False  # prevent accidental overwrites
    GS_OBJECT_PARAMETERS = {"cache_control": "public, max-age=86400"}
    MEDIA_URL = f"https://storage.googleapis.com/{GS_BUCKET_NAME}/"

    # Credentials: On Cloud Run, authentication is automatic via the
    # attached service account.  On Railway (or any non-GCP host), supply
    # the service account JSON key as a base64-encoded env var.
    #   base64 -i gcs-key.json | tr -d '\n'  → set as GCS_CREDENTIALS_BASE64
    _gcs_creds_b64 = os.environ.get("GCS_CREDENTIALS_BASE64")
    if _gcs_creds_b64:
        from google.oauth2 import service_account as _sa

        _info = json.loads(base64.b64decode(_gcs_creds_b64))
        GS_CREDENTIALS = _sa.Credentials.from_service_account_info(_info)

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
# Email — Brevo transactional HTTP API (bypasses SMTP port blocking on Railway)
# Uses the custom backend in thermography_site/backends/brevo_email.py
# which sends via Brevo's REST API over HTTPS (port 443).
# ──────────────────────────────────────────────────────────
EMAIL_BACKEND = "thermography_site.backends.brevo_email.BrevoAPIBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@yourdomain.com")

# ──────────────────────────────────────────────────────────
# Brevo (Sendinblue) Contacts API — for newsletter list sync
# Get your API key at https://app.brevo.com → Settings → API Keys
# Create a list and note its numeric ID.
# ──────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_LIST_ID = os.environ.get("BREVO_LIST_ID", "")

# ──────────────────────────────────────────────────────────
# Analytics — GoatCounter site code (e.g. "mythermography")
# Injected into templates via context processor
# ──────────────────────────────────────────────────────────
GOATCOUNTER_SITE_CODE = os.environ.get("GOATCOUNTER_SITE_CODE", "")

# ──────────────────────────────────────────────────────────
# Wagtail & site URL
# ──────────────────────────────────────────────────────────
_default_url = f"https://{_railway_domain}" if _railway_domain else "https://example.com"
WAGTAILADMIN_BASE_URL = os.environ.get("WAGTAILADMIN_BASE_URL", _default_url)
SITE_URL = os.environ.get("SITE_URL", _default_url)

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
