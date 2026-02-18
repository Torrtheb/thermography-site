"""
Template tag to load ContactPage info for use in any template (e.g., footer).

Usage in a template:
    {% load contact_tags %}
    {% get_contact_info as contact %}
    {{ contact.contact_email }}
    {{ contact.contact_phone }}
    {{ contact.address }}
"""

from django import template
from contact.models import ContactPage

register = template.Library()


@register.simple_tag
def get_contact_info():
    """Return the live ContactPage, or None if it doesn't exist yet."""
    try:
        return ContactPage.objects.live().public().first()
    except Exception:
        return None
