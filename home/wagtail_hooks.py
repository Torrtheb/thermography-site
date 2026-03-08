"""
Wagtail admin customizations for a non-technical site owner.

- Custom welcome panel with simple instructions on the admin dashboard
- GoatCounter analytics panel embedded in the dashboard
- Simplified sidebar (hides confusing menu items)
- Friendly admin title
"""

from django.conf import settings
from django.utils.safestring import mark_safe

from django.forms import Media
from wagtail import hooks


# ---------------------------------------------------------------------------
# Custom welcome panel — replaces the default dashboard with friendly guidance
# ---------------------------------------------------------------------------

class WelcomePanel:
    """Shown on the Wagtail admin dashboard when the owner logs in."""

    order = 10

    @property
    def media(self):
        return Media()

    def render(self):
        return mark_safe(
            '<section class="panel summary nice-padding" style="padding:2em;">'

            # Header
            '<div style="text-align:center; margin-bottom:2em;">'
            '<div style="font-size:2.5em; margin-bottom:0.3em;">Welcome back</div>'
            '<p style="font-size:1.05em; color:#666; margin:0;">'
            'Here\'s everything you can do from this dashboard.'
            '</p>'
            '</div>'

            # Quick-action cards grid
            '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:1em; margin-bottom:2em;">'

            # Card: Edit pages
            '<a href="/admin/pages/" style="text-decoration:none; color:inherit;">'
            '<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px; padding:1.2em; '
            'transition:box-shadow 0.2s; cursor:pointer;" '
            'onmouseover="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
            'onmouseout="this.style.boxShadow=\'none\'">'
            '<div style="font-size:1.5em; margin-bottom:0.3em;">\U0001f4dd</div>'
            '<div style="font-weight:700; margin-bottom:0.3em;">Edit Pages</div>'
            '<div style="font-size:0.85em; color:#666;">Update text, images, and content on any page.</div>'
            '</div></a>'

            # Card: Images
            '<a href="/admin/images/" style="text-decoration:none; color:inherit;">'
            '<div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:12px; padding:1.2em; '
            'transition:box-shadow 0.2s; cursor:pointer;" '
            'onmouseover="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
            'onmouseout="this.style.boxShadow=\'none\'">'
            '<div style="font-size:1.5em; margin-bottom:0.3em;">\U0001f5bc\ufe0f</div>'
            '<div style="font-weight:700; margin-bottom:0.3em;">Photos & Images</div>'
            '<div style="font-size:0.85em; color:#666;">Upload, replace, or organize your photos.</div>'
            '</div></a>'

            # Card: Clients
            '<a href="/admin/snippets/clients/client/" style="text-decoration:none; color:inherit;">'
            '<div style="background:#fdf4ff; border:1px solid #e9d5ff; border-radius:12px; padding:1.2em; '
            'transition:box-shadow 0.2s; cursor:pointer;" '
            'onmouseover="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
            'onmouseout="this.style.boxShadow=\'none\'">'
            '<div style="font-size:1.5em; margin-bottom:0.3em;">\U0001f465</div>'
            '<div style="font-weight:700; margin-bottom:0.3em;">Clients</div>'
            '<div style="font-size:0.85em; color:#666;">View, add, or manage your client records.</div>'
            '</div></a>'

            # Card: Settings
            '<a href="/admin/settings/" style="text-decoration:none; color:inherit;">'
            '<div style="background:#fefce8; border:1px solid #fef08a; border-radius:12px; padding:1.2em; '
            'transition:box-shadow 0.2s; cursor:pointer;" '
            'onmouseover="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
            'onmouseout="this.style.boxShadow=\'none\'">'
            '<div style="font-size:1.5em; margin-bottom:0.3em;">\u2699\ufe0f</div>'
            '<div style="font-weight:700; margin-bottom:0.3em;">Site Settings</div>'
            '<div style="font-size:0.85em; color:#666;">Business name, tagline, policies.</div>'
            '</div></a>'

            # Card: Testimonials
            '<a href="/admin/snippets/home/testimonial/" style="text-decoration:none; color:inherit;">'
            '<div style="background:#fff7ed; border:1px solid #fed7aa; border-radius:12px; padding:1.2em; '
            'transition:box-shadow 0.2s; cursor:pointer;" '
            'onmouseover="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
            'onmouseout="this.style.boxShadow=\'none\'">'
            '<div style="font-size:1.5em; margin-bottom:0.3em;">\u2b50</div>'
            '<div style="font-weight:700; margin-bottom:0.3em;">Testimonials</div>'
            '<div style="font-size:0.85em; color:#666;">Add or edit client testimonials.</div>'
            '</div></a>'

            # Card: Locations
            '<a href="/admin/snippets/booking/location/" style="text-decoration:none; color:inherit;">'
            '<div style="background:#f0f9ff; border:1px solid #bae6fd; border-radius:12px; padding:1.2em; '
            'transition:box-shadow 0.2s; cursor:pointer;" '
            'onmouseover="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
            'onmouseout="this.style.boxShadow=\'none\'">'
            '<div style="font-size:1.5em; margin-bottom:0.3em;">\U0001f4cd</div>'
            '<div style="font-weight:700; margin-bottom:0.3em;">Locations</div>'
            '<div style="font-size:0.85em; color:#666;">Manage clinic locations and pop-ups.</div>'
            '</div></a>'

            '</div>'  # end grid

            # How-to tip
            '<div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px; padding:1.2em; text-align:center;">'
            '<p style="margin:0; color:#555; font-size:0.95em;">'
            '\U0001f4a1 <strong>Tip:</strong> After editing any page, click the green <strong>"Publish"</strong> '
            'button to make your changes live. Use <strong>"Preview"</strong> to check before publishing.'
            '</p>'
            '</div>'

            '</section>'
        )


@hooks.register("construct_homepage_panels")
def add_welcome_panel(request, panels):
    """Replace the default dashboard panels with a friendly welcome guide + analytics."""
    panels.clear()
    panels.append(WelcomePanel())

    # Add analytics panel if GoatCounter is configured
    site_code = getattr(settings, "GOATCOUNTER_SITE_CODE", "")
    if site_code:
        panels.append(AnalyticsPanel(site_code))


# ---------------------------------------------------------------------------
# GoatCounter analytics panel — shows site stats right on the dashboard
# ---------------------------------------------------------------------------

class AnalyticsPanel:
    """
    Clean link-based analytics panel on the Wagtail admin dashboard.

    Shows a summary of what GoatCounter tracks and a prominent button
    to open the full dashboard in a new tab.  No iframe — avoids
    authentication and CSP issues.
    """

    order = 20  # after the welcome panel

    def __init__(self, site_code):
        self.site_code = site_code

    @property
    def media(self):
        return Media()

    def render(self):
        dashboard_url = f"https://{self.site_code}.goatcounter.com"
        return mark_safe(
            f'<section class="panel summary nice-padding">'
            f'<h2 style="margin-top:0;">\U0001f4ca Site Analytics</h2>'
            f'<p style="color:#555; margin-bottom:1em;">'
            f'Your website visitors are tracked by '
            f'<strong style="color:#2d6a4f;">GoatCounter</strong> '
            f'— privacy-friendly, no cookies, GDPR-compliant.'
            f'</p>'

            f'<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px; padding:1.5em; margin-bottom:1.2em;">'
            f'<table style="width:100%; border-collapse:collapse;">'

            f'<tr style="border-bottom:1px solid #d1fae5;">'
            f'<td style="padding:8px 0; color:#555;">\U0001f4c8 Page views</td>'
            f'<td style="padding:8px 0; color:#555; text-align:right;">Which pages visitors view and how often</td>'
            f'</tr>'

            f'<tr style="border-bottom:1px solid #d1fae5;">'
            f'<td style="padding:8px 0; color:#555;">\U0001f310 Referrers</td>'
            f'<td style="padding:8px 0; color:#555; text-align:right;">Where your visitors come from (Google, social media, etc.)</td>'
            f'</tr>'

            f'<tr style="border-bottom:1px solid #d1fae5;">'
            f'<td style="padding:8px 0; color:#555;">\U0001f4f1 Devices</td>'
            f'<td style="padding:8px 0; color:#555; text-align:right;">Desktop vs. mobile, browsers, screen sizes</td>'
            f'</tr>'

            f'<tr>'
            f'<td style="padding:8px 0; color:#555;">\U0001f4cd Locations</td>'
            f'<td style="padding:8px 0; color:#555; text-align:right;">Countries and languages of your visitors</td>'
            f'</tr>'

            f'</table>'
            f'</div>'

            f'<div style="text-align:center;">'
            f'<a href="{dashboard_url}" target="_blank" '
            f'style="display:inline-block; background:#2d6a4f; color:#fff; '
            f'font-weight:600; font-size:1.05em; padding:12px 32px; '
            f'border-radius:8px; text-decoration:none; '
            f'box-shadow:0 2px 6px rgba(0,0,0,0.15);">'
            f'\U0001f4ca&ensp;View Analytics Dashboard'
            f'</a>'
            f'</div>'

            f'<p style="color:#999; font-size:0.85em; margin-top:1em; text-align:center;">'
            f'Opens in a new tab at <em>{dashboard_url}</em>'
            f'</p>'
            f'</section>'
        )


# ---------------------------------------------------------------------------
# Simplified sidebar — hide menu items that would confuse a non-tech user
# ---------------------------------------------------------------------------

@hooks.register("construct_main_menu")
def simplify_main_menu(request, menu_items):
    """
    Remove admin menu items the site owner doesn't need.

    Keeps: Pages, Images, Documents, Settings
    Hides: Reports, Help (Wagtail docs)
    """
    hidden_items = {"reports", "help"}
    menu_items[:] = [
        item for item in menu_items
        if item.name not in hidden_items
    ]


# ---------------------------------------------------------------------------
# Custom admin branding
# ---------------------------------------------------------------------------

@hooks.register("insert_global_admin_css")
def admin_css():
    """Add CSS tweaks for friendlier admin UX + mobile scroll fixes."""
    return mark_safe(
        "<style>"
        ".c-sf-block-type-description { color: #666 !important; font-size: 0.85em; }"
        ".help { font-size: 0.9em !important; }"
        ".content-wrapper h1 { font-size: 1.5em; }"
        ".content-wrapper { padding-bottom: 100px !important; }"
        "#main, .content-wrapper, .content, .nice-padding {"
        "  overflow-x: auto !important;"
        "  overflow-y: visible !important;"
        "  max-width: 100vw;"
        "}"
        ".w-main { overflow: auto !important; }"
        ".listing { min-width: 0; }"
        ".w-table { overflow-x: auto !important; }"
        "footer.w-sticky-footer, .footer, .actions {"
        "  position: sticky !important;"
        "}"
        "</style>"
    )
