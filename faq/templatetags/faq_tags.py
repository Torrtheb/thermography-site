"""
Template tags for pulling FAQ items into any template.

Usage:
    {% load faq_tags %}
    {% get_faq_items max_items=5 as faq_items %}
"""

from django import template

register = template.Library()


@register.simple_tag
def get_faq_items(max_items=5):
    """Return FAQ items from the FAQPage, limited to max_items."""
    from faq.models import FAQPage

    faq_page = FAQPage.objects.live().public().first()
    if not faq_page:
        return []
    items = list(faq_page.faq_items)
    return items[:max_items]
