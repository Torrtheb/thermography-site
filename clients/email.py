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
    )
    if message:
        plain_message += f"{context['custom_message']}\n\n"
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



def _get_etransfer_email():
    """Fetch the e-Transfer email from SiteSettings (returns '' if not set)."""
    try:
        from wagtail.models import Site
        from home.models import SiteSettings
        site = Site.objects.get(is_default_site=True)
        return SiteSettings.for_site(site).etransfer_email or ""
    except Exception:
        return ""


def send_deposit_request(client, amount, appointment_date=""):
    """
    Send deposit payment instructions to a client after they book.

    The e-Transfer email is pulled from SiteSettings and included only in
    this private email — never on the public website.
    """
    if not client.email:
        return False

    etransfer_email = _get_etransfer_email()

    subject = "Booking Deposit Required — Payment Instructions"
    context = {
        "client_name": client.name,
        "amount": str(amount),
        "appointment_date": appointment_date,
        "etransfer_email": etransfer_email,
    }

    plain_message = (
        f"Hi {context['client_name']},\n\n"
        f"Thank you for booking your thermography appointment"
        f"{f' on {appointment_date}' if appointment_date else ''}!\n\n"
        f"To confirm your booking, a ${context['amount']} non-refundable deposit is required.\n\n"
        f"HOW TO PAY:\n"
    )
    if etransfer_email:
        plain_message += f"  • e-Transfer: Send ${context['amount']} to {etransfer_email}\n"
    plain_message += (
        "  • Cash: Pay at your appointment\n"
        "  • Cheque: Mail or bring in person\n\n"
        "Your deposit will be applied toward your service fee on the day of your visit.\n\n"
        "If you have any questions, please reply to this email.\n\n"
        "Best regards,\n"
        "Your Thermography Team"
    )

    try:
        html_message = render_to_string(
            "clients/emails/deposit_request.html", context
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


def send_deposit_confirmation(client, amount, appointment_date="", payment_method=""):
    """
    Send a deposit-received confirmation email to a client.

    Args:
        client: A Client model instance.
        amount: Deposit amount as a string or Decimal.
        appointment_date: Human-readable date string (optional).
        payment_method: How they paid, e.g. "e-Transfer" (optional).
    """
    if not client.email:
        return False

    subject = "Deposit Received — Your Booking Is Confirmed"
    context = {
        "client_name": client.name,
        "amount": str(amount),
        "appointment_date": appointment_date,
        "payment_method": payment_method,
    }

    plain_message = (
        f"Hi {context['client_name']},\n\n"
        f"Thank you! We've received your ${context['amount']} booking deposit "
        f"and your appointment is confirmed.\n\n"
    )
    if appointment_date:
        plain_message += f"Appointment date: {appointment_date}\n"
    if payment_method:
        plain_message += f"Paid via: {payment_method}\n"
    plain_message += (
        "\nYour deposit will be applied toward your service fee on the day of your visit.\n\n"
        "If you need to reschedule or have any questions, please reply to this email.\n\n"
        "Best regards,\n"
        "Your Thermography Team"
    )

    try:
        html_message = render_to_string(
            "clients/emails/deposit_confirmation.html", context
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


def send_deposit_expired_cancellation(client, amount, appointment_date="", service_name=""):
    """
    Notify a client that their appointment was cancelled because
    the booking deposit was not received within 48 hours.
    """
    if not client.email:
        return False

    subject = "Appointment Cancelled — Booking Deposit Not Received"
    context = {
        "client_name": client.name,
        "amount": str(amount),
        "appointment_date": appointment_date,
        "service_name": service_name,
    }

    plain_message = (
        f"Hi {context['client_name']},\n\n"
        f"We're writing to let you know that your thermography appointment"
        f"{f' on {appointment_date}' if appointment_date else ''}"
        f"{f' ({service_name})' if service_name else ''}"
        f" has been cancelled.\n\n"
        f"The required ${context['amount']} booking deposit was not received "
        f"within 48 hours of booking, and the appointment has been automatically released.\n\n"
        f"If you'd like to rebook, you're welcome to visit our website and "
        f"schedule a new appointment at any time.\n\n"
        f"If you believe this was an error or you've already sent payment, "
        f"please reply to this email and we'll sort it out right away.\n\n"
        f"Best regards,\n"
        f"Your Thermography Team"
    )

    try:
        html_message = render_to_string(
            "clients/emails/deposit_expired.html", context
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


def send_owner_deposit_expiry_notice(expired_deposits):
    """
    Notify the owner (DEFAULT_FROM_EMAIL) about deposits that were
    auto-forfeited and Cal.com bookings that were cancelled.
    """
    if not expired_deposits:
        return False

    owner_email = settings.DEFAULT_FROM_EMAIL
    if not owner_email:
        return False

    count = len(expired_deposits)
    subject = f"[Auto] {count} appointment(s) cancelled — deposit not received"

    lines = [
        f"{count} booking(s) were automatically cancelled because the deposit "
        f"was not received within 48 hours:\n"
    ]

    for dep in expired_deposits:
        client_name = dep.client.name if dep.client_id else "Unknown"
        date_str = dep.appointment_date.strftime("%B %d, %Y") if dep.appointment_date else "no date"
        svc = dep.service_name or "Unknown service"
        lines.append(f"  • {client_name} — {svc} — {date_str} — ${dep.amount}")

    lines.append(
        "\nThe Cal.com bookings have been cancelled and the clients have been notified.\n"
        "You can review these in Wagtail admin → Deposits (filter by 'Forfeited').\n"
    )

    body = "\n".join(lines)

    send_mail(
        subject=subject,
        message=body,
        from_email=owner_email,
        recipient_list=[owner_email],
        fail_silently=False,
    )
    return True
