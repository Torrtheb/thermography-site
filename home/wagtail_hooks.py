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
            '<section class="panel summary nice-padding">'
            '<h2 style="margin-top:0;">\U0001f44b Welcome to your website editor!</h2>'
            '<p style="font-size:1.1em; color:#555;">'
            "Here's how to make changes to your website:"
            '</p>'
            '<table style="width:100%; border-collapse:collapse; margin:1em 0;">'
            '<tr style="border-bottom:1px solid #eee;">'
            '<td style="padding:10px 10px 10px 0; font-size:1.3em;">\U0001f4dd</td>'
            '<td style="padding:10px;">'
            '<strong>Edit pages</strong><br>'
            '<span style="color:#666;">Click <strong>"Pages"</strong> in the left menu, then click any page to edit it.</span>'
            '</td></tr>'
            '<tr style="border-bottom:1px solid #eee;">'
            '<td style="padding:10px 10px 10px 0; font-size:1.3em;">\U0001f5bc\ufe0f</td>'
            '<td style="padding:10px;">'
            '<strong>Add photos</strong><br>'
            '<span style="color:#666;">Click <strong>"Images"</strong> to upload or manage your photos.</span>'
            '</td></tr>'
            '<tr style="border-bottom:1px solid #eee;">'
            '<td style="padding:10px 10px 10px 0; font-size:1.3em;">\u2699\ufe0f</td>'
            '<td style="padding:10px;">'
            '<strong>Site settings</strong><br>'
            '<span style="color:#666;">Click <strong>"Settings"</strong> to change business name, tagline, or cancellation policy.</span>'
            '</td></tr>'
            '<tr>'
            '<td style="padding:10px 10px 10px 0; font-size:1.3em;">\u2705</td>'
            '<td style="padding:10px;">'
            '<strong>Publish your changes</strong><br>'
            '<span style="color:#666;">After editing, click the green <strong>"Publish"</strong> button at the bottom to make changes live.</span>'
            '</td></tr>'
            '</table>'
            '<p style="color:#888; font-size:0.9em;">'
            '\U0001f4a1 <em>Tip: You can preview changes before publishing by clicking "Preview" at the bottom of any page editor.</em>'
            '</p>'
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
    """Add subtle CSS tweaks to make the admin feel less technical."""
    return mark_safe(
        '<style>'
        '.c-sf-block-type-description { color: #666 !important; font-size: 0.85em; }'
        '.help { font-size: 0.9em !important; }'
        '.content-wrapper h1 { font-size: 1.5em; }'
        '.content-wrapper { padding-bottom: 100px !important; }'  # stop save bar overlapping content
        '</style>'
    )
