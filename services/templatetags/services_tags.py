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


SERVICE_ICON_MAP = {
    "full-body": {
        "color": "#0d9488",
        "bg": "#ccfbf1",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z'
            'M4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75'
            'c-2.676 0-5.216-.584-7.499-1.632Z" />'
        ),
    },
    "breast": {
        "color": "#db2777",
        "bg": "#fce7f3",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733'
            '-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25'
            'c0 7.22 9 12 9 12s9-4.78 9-12Z" />'
        ),
    },
    "upper-body": {
        "color": "#2563eb",
        "bg": "#dbeafe",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09'
            'L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846'
            'a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z'
            'M18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456'
            'L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035'
            'a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259'
            'a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183'
            'a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394'
            'a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183'
            'a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394'
            'a2.25 2.25 0 0 0-1.423 1.423Z" />'
        ),
    },
    "head": {
        "color": "#7c3aed",
        "bg": "#ede9fe",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5'
            'c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639'
            'C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />'
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />'
        ),
    },
    "dental": {
        "color": "#0891b2",
        "bg": "#cffafe",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M15.182 15.182a4.5 4.5 0 0 1-6.364 0M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z'
            'M9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75Z'
            'm-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75'
            '.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z" />'
        ),
    },
    "sport": {
        "color": "#ea580c",
        "bg": "#ffedd5",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M15.362 5.214A8.252 8.252 0 0 1 12 21 8.25 8.25 0 0 1 6.038 7.047'
            ' 8.287 8.287 0 0 0 9 9.601a8.983 8.983 0 0 1 3.361-6.867'
            ' 8.21 8.21 0 0 0 3 2.48Z" />'
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M12 18a3.75 3.75 0 0 0 .495-7.468 5.99 5.99 0 0 0-1.925 3.547'
            ' 5.975 5.975 0 0 1-2.133-1.001A3.75 3.75 0 0 0 12 18Z" />'
        ),
    },
    "follow": {
        "color": "#059669",
        "bg": "#d1fae5",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992'
            'm-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865'
            'a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />'
        ),
    },
    "region": {
        "color": "#6366f1",
        "bg": "#e0e7ff",
        "svg": (
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M9 6.75V15m6-6v8.25m.503 3.498 4.875-2.437c.381-.19.622-.58.622-1.006'
            'V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0'
            'L9.503 3.252a1.125 1.125 0 0 0-1.006 0L3.622 5.689'
            'C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006'
            'l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0Z" />'
        ),
    },
}

FALLBACK_ICON = {
    "color": "#458a95",
    "bg": "#e0f2f1",
    "svg": (
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0'
        'v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5'
        'm-.5-1.5h-9.5m0 0-.5 1.5m.75-9 3-3 2.148 2.148A12.061 12.061 0 0 1 16.5 7.605" />'
    ),
}

ICON_COLORS = [
    {"color": "#0d9488", "bg": "#ccfbf1"},
    {"color": "#db2777", "bg": "#fce7f3"},
    {"color": "#2563eb", "bg": "#dbeafe"},
    {"color": "#7c3aed", "bg": "#ede9fe"},
    {"color": "#ea580c", "bg": "#ffedd5"},
    {"color": "#059669", "bg": "#d1fae5"},
    {"color": "#6366f1", "bg": "#e0e7ff"},
    {"color": "#0891b2", "bg": "#cffafe"},
]


def _get_icon_for_service(slug, index=0):
    """Return (svg_paths, color, bg) for a service based on its slug."""
    slug_lower = slug.lower()
    for keyword, icon_data in SERVICE_ICON_MAP.items():
        if keyword in slug_lower:
            return icon_data
    palette = ICON_COLORS[index % len(ICON_COLORS)]
    return {**FALLBACK_ICON, **palette}


@register.simple_tag
def service_icon_svg(service, loop_counter=0, white=False):
    """Render an SVG icon for a service based on its slug.

    Usage:
        {% service_icon_svg service forloop.counter0 %}
        {% service_icon_svg service forloop.counter0 white=True %}
    """
    icon = _get_icon_for_service(service.slug, loop_counter)
    stroke = "rgba(255,255,255,0.9)" if white else icon["color"]
    return mark_safe(
        f'<svg class="w-12 h-12" viewBox="0 0 24 24" fill="none" '
        f'stroke="{stroke}" stroke-width="1.5" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'{icon["svg"]}</svg>'
    )


@register.simple_tag
def service_icon_bg(service, loop_counter=0):
    """Return the background color for a service icon."""
    icon = _get_icon_for_service(service.slug, loop_counter)
    return icon["bg"]


@register.simple_tag
def service_icon_color(service, loop_counter=0):
    """Return the accent color for a service icon."""
    icon = _get_icon_for_service(service.slug, loop_counter)
    return icon["color"]


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
