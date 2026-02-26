from django import forms

from .models import NewsletterSubscriber


class NewsletterForm(forms.ModelForm):
    """Minimal form: just an email field with a honeypot."""

    # Honeypot field — hidden via CSS; bots fill it in, humans don't
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = NewsletterSubscriber
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "Your email address",
                    "autocomplete": "email",
                    "class": (
                        "w-full px-4 py-3 rounded-l-lg text-gray-900 "
                        "placeholder-gray-500 focus:outline-none focus:ring-2 "
                        "focus:ring-brand-400 border-0"
                    ),
                }
            ),
        }

    def clean_website(self):
        """Reject submissions where the honeypot was filled in."""
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Bot detected.")
        return ""

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        return email


class ComposeNewsletterForm(forms.Form):
    """Form for composing a newsletter in the Wagtail admin."""

    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Newsletter subject line…"}),
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 12,
            "placeholder": "Write your newsletter content here…",
        }),
    )
    sign_off = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Best regards,\nYour Thermography Team",
        }),
        initial="Best regards,\nYour Thermography Team",
    )
