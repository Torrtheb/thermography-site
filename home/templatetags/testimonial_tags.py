"""
Template tags for testimonials.

Usage in any template:
  {% load testimonial_tags %}

  {# Featured testimonials (for booking, first visit) #}
  {% testimonials_section %}

  {# Testimonials for a specific service #}
  {% testimonials_section service=page %}

  {# Custom limit #}
  {% testimonials_section limit=2 %}
"""

from django import template
from home.models import Testimonial

register = template.Library()


@register.inclusion_tag("includes/testimonials_section.html")
def testimonials_section(service=None, per_page=3, featured_only=True):
    """
    Renders a testimonials carousel section.

    Args:
        service: Optional ServicePage — filters testimonials for that service.
        per_page: How many testimonials to show per page (default 3).
        featured_only: Only show featured testimonials (default True).
    """
    qs = Testimonial.objects.all()

    if featured_only:
        qs = qs.filter(is_featured=True)

    if service:
        # Show testimonials for this service, fall back to general ones
        service_qs = list(qs.filter(service=service))
        if service_qs:
            return {"testimonials": service_qs, "per_page": per_page}
        # Fall back to testimonials with no linked service (general ones)
        qs = qs.filter(service__isnull=True)

    return {"testimonials": list(qs), "per_page": per_page}
