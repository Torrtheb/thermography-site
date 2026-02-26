"""
Email utilities for the clients app.

Uses Django's built-in email framework (backed by Brevo SMTP in production,
console backend in development).

Usage:
    from clients.email import send_appointment_reminder, send_followup_email

    send_appointment_reminder(client, appointment_date="March 5, 2026")
    send_followup_email(client, message="Thank you for visiting!")
"""

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_appointment_reminder(client, appointment_date, location=""):
    """
    Send an appointment reminder email to a client.

    Args:
        client: A Client model instance (email is decrypted automatically).
        appointment_date: Human-readable date string.
        location: Optional clinic location override.
    """
    if not client.email:
        return False

    subject = f"Appointment Reminder — {appointment_date}"
    context = {
        "client_name": client.name,
        "appointment_date": appointment_date,
        "location": location or client.clinic_location,
    }

    location_str = context["location"]
    plain_message = (
        f"Hi {context['client_name']},\n\n"
        f"This is a friendly reminder about your upcoming thermography appointment "
        f"on {context['appointment_date']}"
        f"{f' at {location_str}' if location_str else ''}.\n\n"
        f"If you need to reschedule, please reply to this email or call us.\n\n"
        f"Best regards,\n"
        f"Your Thermography Team"
    )

    # Try to render an HTML template if it exists
    try:
        html_message = render_to_string(
            "clients/emails/appointment_reminder.html", context
        )
    except Exception:
        html_message = None

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
        html_message=html_message,
        fail_silently=False,
    )
    return True


def send_followup_email(client, message=""):
    """
    Send a follow-up / thank-you email after a visit.

    Args:
        client: A Client model instance.
        message: Optional custom message body.
    """
    if not client.email:
        return False

    subject = "Thank You for Your Visit"
    context = {
        "client_name": client.name,
        "custom_message": message,
    }

    plain_message = (
        f"Hi {context['client_name']},\n\n"
        f"Thank you for your recent thermography visit.\n\n"
        f"{context['custom_message']}\n\n" if message else
        f"Hi {context['client_name']},\n\n"
        f"Thank you for your recent thermography visit.\n\n"
    )
    plain_message += (
        "If you have any questions about your results, don't hesitate to reach out.\n\n"
        "Best regards,\n"
        "Your Thermography Team"
    )

    try:
        html_message = render_to_string(
            "clients/emails/followup.html", context
        )
    except Exception:
        html_message = None

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
        html_message=html_message,
        fail_silently=False,
    )
    return True


def send_custom_email(client, subject, body):
    """
    Send a custom email to a client.

    Args:
        client: A Client model instance.
        subject: Email subject line.
        body: Plain text email body.
    """
    if not client.email:
        return False

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
        fail_silently=False,
    )
    return True



# NOTE: send_report_email was removed — private client reports are no longer
# stored on or sent from this website. Reports are delivered via a separate
# secure channel outside the application.
