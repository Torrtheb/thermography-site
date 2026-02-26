"""
Template tags for the booking app.

Usage in templates:
    {% load booking_tags %}
    {% get_featured_locations as locations %}
    {% get_permanent_locations as permanent %}
    {% get_upcoming_popups as popups %}
"""

from django import template

from booking.models import Location

register = template.Library()


@register.simple_tag
def get_featured_locations():
    """Return active locations marked for homepage display."""
    return list(Location.get_homepage_featured())


@register.simple_tag
def get_permanent_locations():
    """Return all permanent (home) clinics — always visible."""
    return list(
        Location.objects.filter(is_permanent=True)
        .order_by("sort_order", "name")
    )


@register.simple_tag
def get_upcoming_popups():
    """Return pop-up locations whose display_until date hasn't passed."""
    from django.utils import timezone

    today = timezone.localdate()  # respects TIME_ZONE setting
    return list(
        Location.objects.filter(
            is_permanent=False,
            display_until__gte=today,
        )
        .order_by("sort_order", "name")
    )
