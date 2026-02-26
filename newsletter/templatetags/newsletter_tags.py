from django import template

from newsletter.forms import NewsletterForm

register = template.Library()


@register.inclusion_tag("newsletter/newsletter_section.html", takes_context=True)
def newsletter_signup(context):
    """Render the newsletter signup section. Use in any template."""
    return {
        "newsletter_form": NewsletterForm(),
        "request": context.get("request"),
    }
