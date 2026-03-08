"""
Forms for the clients app — used in Wagtail admin views.
"""

from django import forms

from .models import Client, VISIT_REASON_CHOICES


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


class ClientFilterForm(forms.Form):
    """Filter form used on both the client list and email compose page."""

    clinic_location = forms.CharField(required=False, label="Location")
    previous_visit_reason = forms.ChoiceField(
        required=False,
        label="Visit reason",
        choices=[("", "All")] + list(VISIT_REASON_CHOICES),
    )
    appt_from = forms.DateField(
        required=False,
        label="Appointment from",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    appt_to = forms.DateField(
        required=False,
        label="Appointment to",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    search = forms.CharField(
        required=False,
        label="Search name/email/phone",
        widget=forms.TextInput(attrs={"placeholder": "Type to search…"}),
    )


class CSVImportForm(forms.Form):
    """Upload a CSV of client records."""

    csv_file = forms.FileField(
        label="CSV file",
        help_text=(
            "Columns: name (required), email, phone, clinic_location, "
            "previous_visit_reason, last_appointment_date (YYYY-MM-DD), notes. "
            "First row must be a header row."
        ),
    )

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if not f.name.endswith(".csv"):
            raise forms.ValidationError("File must be a .csv file.")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File too large (max 5 MB).")
        return f
