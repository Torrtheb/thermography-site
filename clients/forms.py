"""
Forms for the clients app — used in Wagtail admin views.
"""

from django import forms

from .models import Client


class ComposeEmailForm(forms.Form):
    """Form for composing and sending an email to one or more clients."""

    recipients = forms.ModelMultipleChoiceField(
        queryset=Client.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select the client(s) to email.",
    )

    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Email subject line…"}),
    )

    body = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 12,
            "placeholder": "Write your message here…\n\nThe client's first name will be used in the greeting automatically.",
        }),
    )

    sign_off = forms.CharField(
        initial="Best regards,\nYour Thermography Team",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="The sign-off appended to every email.",
    )

    def clean_recipients(self):
        recipients = self.cleaned_data["recipients"]
        no_email = [c.name for c in recipients if not c.email]
        if no_email:
            raise forms.ValidationError(
                f"These clients have no email on file: {', '.join(no_email)}. "
                "Remove them or add an email address first."
            )
        return recipients
