"""
Template tags for pulling ServicePage data into any template.

Usage:
    {% load services_tags %}
    {% get_services as services %}
    {% get_services featured_only=True as services %}
"""

from django import template

register = template.Library()


@register.simple_tag
def get_services(featured_only=False):
    """Return live ServicePage instances, optionally filtered to featured only."""
    from services.models import ServicePage

    qs = ServicePage.objects.live().public().order_by("title")
    if featured_only:
        qs = qs.filter(is_featured=True)
    return qs
