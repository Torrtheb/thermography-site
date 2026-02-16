"""
Contact app — a single page with contact info and an optional contact form.

The owner can edit contact details (email, phone, address) and toggle
the contact form on/off from the admin.

When a visitor submits the form, an email is sent to the contact_email address.
In development, emails print to the terminal (console backend).

Page hierarchy:
  Root Page
    └── Contact  ← ContactPage (only one)
"""

from django.db import models
from django.core.mail import send_mail
from django.template.response import TemplateResponse

from wagtail.models import Page
from wagtail.admin.panels import FieldPanel, MultiFieldPanel


class ContactPage(Page):
    """
    The Contact page at /contact/.
    Shows contact details and optionally a contact form.
    max_count = 1: only one contact page.
    """

    intro = models.TextField(
        blank=True,
        help_text="Optional intro text above the contact info.",
    )

    contact_email = models.EmailField(
        help_text="Public contact email address.",
    )

    contact_phone = models.CharField(
        max_length=30,
        help_text="Public phone number.",
    )

    address = models.TextField(
        blank=True,
        help_text="Business address (optional).",
    )

    map_embed_url = models.URLField(
        blank=True,
        help_text="Google Maps embed URL (optional). Use the 'Embed a map' URL from Google Maps.",
    )

    contact_form_enabled = models.BooleanField(
        default=True,
        help_text="Show the contact form on the page.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        MultiFieldPanel(
            [
                FieldPanel("contact_email"),
                FieldPanel("contact_phone"),
                FieldPanel("address"),
            ],
            heading="Contact Details",
        ),
        FieldPanel("map_embed_url"),
        FieldPanel("contact_form_enabled"),
    ]

    max_count = 1

    def serve(self, request):
        """Handle GET (show form) and POST (send email)."""
        form_submitted = False
        form_error = ""

        if request.method == "POST" and self.contact_form_enabled:
            name = request.POST.get("name", "").strip()
            email = request.POST.get("email", "").strip()
            phone = request.POST.get("phone", "").strip()
            message = request.POST.get("message", "").strip()

            if name and email and message:
                try:
                    send_mail(
                        subject=f"Contact form: {name}",
                        message=(
                            f"Name: {name}\n"
                            f"Email: {email}\n"
                            f"Phone: {phone or 'Not provided'}\n\n"
                            f"Message:\n{message}"
                        ),
                        from_email=None,  # uses DEFAULT_FROM_EMAIL
                        recipient_list=[self.contact_email],
                        fail_silently=False,
                    )
                    form_submitted = True
                except Exception:
                    form_error = "Sorry, there was a problem sending your message. Please try again or contact us directly."
            else:
                form_error = "Please fill in all required fields."

        return TemplateResponse(
            request,
            self.get_template(request),
            self.get_context(request) | {
                "form_submitted": form_submitted,
                "form_error": form_error,
            },
        )

    class Meta:
        verbose_name = "Contact Page"
