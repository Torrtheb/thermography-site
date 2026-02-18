"""
Custom template context processors for thermography_site.
"""

from django.conf import settings


def analytics(request):
    """Inject GoatCounter site code into every template context."""
    return {
        "goatcounter_site_code": getattr(settings, "GOATCOUNTER_SITE_CODE", ""),
    }
