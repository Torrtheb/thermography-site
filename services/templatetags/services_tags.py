"""
Template tags for pulling ServicePage data into any template.

Usage:
    {% load services_tags %}
    {% get_services as services %}
    {% get_services featured_only=True as services %}
"""

import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def get_services(featured_only=False):
    """Return live ServicePage instances, optionally filtered to featured only."""
    from services.models import ServicePage

    qs = ServicePage.objects.live().public().order_by("title")
    if featured_only:
        qs = qs.filter(is_featured=True)
    return qs


_EMPTY_PARAGRAPH_RE = re.compile(
    r"<p>(?:\s|&nbsp;|&#160;|<br\s*/?>)*</p>",
    flags=re.IGNORECASE,
)


@register.filter(name="strip_empty_richtext_paragraphs")
def strip_empty_richtext_paragraphs(value):
    """
    Remove blank rich-text paragraphs produced by editor line breaks.

    This prevents visible vertical gaps in checklist/intro rich-text blocks.
    """
    if not value:
        return value
    return mark_safe(_EMPTY_PARAGRAPH_RE.sub("", str(value)))
