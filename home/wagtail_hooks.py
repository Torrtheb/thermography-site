"""
Wagtail admin customizations for a non-technical site owner.

- Custom welcome panel with simple instructions on the admin dashboard
- Simplified sidebar (hides confusing menu items)
- Friendly admin title
"""

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
    """Replace the default dashboard panels with a friendly welcome guide."""
    panels.clear()
    panels.append(WelcomePanel())


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
        '</style>'
    )
