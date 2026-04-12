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



def _get_owner_email():
    """Return the email address where owner notifications should be sent."""
    return (
        getattr(settings, "OWNER_NOTIFICATION_EMAIL", "")
        or settings.DEFAULT_FROM_EMAIL
    )


def _get_site_settings():
    """Fetch SiteSettings for the default site, or None on failure."""
    try:
        from wagtail.models import Site
        from home.models import SiteSettings
        site = Site.objects.get(is_default_site=True)
        return SiteSettings.for_site(site)
    except Exception:
        return None


class _SafeDict(dict):
    """Dict subclass that returns '{key}' for missing keys instead of raising KeyError.

    Prevents the owner from accidentally crashing email sends by typing
    an unrecognized placeholder like {name} instead of {client_name}.
    """
    def __missing__(self, key):
        return "{" + key + "}"


def _lookup_service_price(service_name):
    """Look up the price_label from ServicePage by matching on title.

    The deposit stores the Cal.com event title (e.g. "Full Body Scan —
    Nanaimo"), which may contain a location suffix.  We try an exact title
    match first, then fall back to checking whether any ServicePage title
    appears as a substring (longest match wins).

    Returns the price_label string (e.g. "$150") or "" if not found.
    """
    if not service_name:
        return ""
    try:
        from services.models import ServicePage
        pages = list(ServicePage.objects.live().values_list("title", "price_label"))
        if not pages:
            return ""

        sn_lower = service_name.lower()

        for title, price in pages:
            if title.lower() == sn_lower:
                return price

        best_title, best_price = "", ""
        for title, price in pages:
            if title.lower() in sn_lower and len(title) > len(best_title):
                best_title, best_price = title, price
        return best_price
    except Exception:
        return ""


def send_deposit_request(client, amount, appointment_date="", service_name=""):
    """
    Send deposit payment instructions to a client after they book.

    Renders a professional HTML email with deposit details plus the
    cancellation / deposit / payment-methods policies pulled from
    SiteSettings.  The owner-editable plain-text template is kept as the
    text/plain fallback for mail clients that don't render HTML.
    """
    if not client.email:
        return False

    ss = _get_site_settings()
    etransfer_email = (ss.etransfer_email or "") if ss else ""
    appointment_line = f" on {appointment_date}" if appointment_date else ""
    client_name = client.name or "there"
    business_name = (ss.business_name if ss and ss.business_name else "Your Thermography Team")

    service_price = _lookup_service_price(service_name)

    # ── Build the owner-editable message body (used in both HTML + plain text) ──
    template = (ss.email_deposit_request if ss and ss.email_deposit_request else "")
    if not template:
        template = (
            "Hi {client_name},\n\n"
            "A ${amount} non-refundable deposit is required to confirm your booking{appointment_line}.\n\n"
            "Best regards,\nYour Thermography Team"
        )

    plain_message = template.format_map(_SafeDict(
        client_name=client_name,
        amount=str(amount),
        appointment_line=appointment_line,
        etransfer_email=etransfer_email,
        service_name=service_name,
        service_price=service_price,
    ))

    # ── Render richtext policy fields to HTML for the email ──
    deposit_policy_html = ""
    cancellation_policy_html = ""
    if ss:
        from wagtail.rich_text import expand_db_html
        if ss.deposit_policy:
            deposit_policy_html = expand_db_html(ss.deposit_policy)
        if ss.cancellation_policy:
            cancellation_policy_html = expand_db_html(ss.cancellation_policy)
    # ── HTML email — wraps the owner-editable text in a styled template ──
    try:
        html_message = render_to_string(
            "clients/emails/deposit_request.html",
            {
                "email_body": plain_message,
                "amount": str(amount),
                "appointment_line": appointment_line,
                "business_name": business_name,
                "deposit_policy": deposit_policy_html,
                "cancellation_policy": cancellation_policy_html,
                "service_name": service_name,
                "service_price": service_price,
            },
        )
    except Exception:
        html_message = None

    # ── Append policies to the plain-text version for text-only clients ──
    if ss:
        from django.utils.html import strip_tags
        policy_lines = []
        if ss.deposit_policy:
            policy_lines.append("DEPOSIT & PAYMENT POLICY\n" + strip_tags(ss.deposit_policy).strip())
        if ss.cancellation_policy:
            policy_lines.append("CANCELLATION POLICY\n" + strip_tags(ss.cancellation_policy).strip())
        if policy_lines:
            plain_message += "\n\n---\n\n" + "\n\n".join(policy_lines)

    subject = "Booking Deposit Required — Payment Instructions"

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
        html_message=html_message,
        fail_silently=False,
    )
    return True


def send_deposit_expiry_warning(client, amount, appointment_date="", service_name=""):
    """
    Warn a client that their appointment will be cancelled in 24 hours
    unless the booking deposit is received.

    Sent at the 48-hour mark (24 hours before the 72-hour cancellation).
    Uses the owner-editable template from SiteSettings → Email Templates.
    """
    if not client.email:
        return False

    ss = _get_site_settings()
    appointment_line = f" on {appointment_date}" if appointment_date else ""
    service_line = f" ({service_name})" if service_name else ""

    template = (ss.email_deposit_warning if ss and ss.email_deposit_warning else "")
    if not template:
        template = (
            "Hi {client_name},\n\n"
            "This is a friendly reminder that the ${amount} booking deposit for your "
            "thermography appointment{appointment_line}{service_line} has not yet been received.\n\n"
            "If we do not receive the deposit within the next 24 hours, the appointment "
            "will be automatically cancelled.\n\n"
            "If you've already sent payment, please disregard this message — it may take "
            "a moment for us to process it.\n\n"
            "If you have any questions, please reply to this email.\n\n"
            "Best regards,\n"
            "Your Thermography Team"
        )

    plain_message = template.format_map(_SafeDict(
        client_name=client.name or "there",
        amount=str(amount),
        appointment_line=appointment_line,
        service_line=service_line,
    ))

    subject = "Reminder: Booking Deposit Due — Appointment at Risk of Cancellation"

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
        fail_silently=False,
    )
    return True


def send_deposit_expired_cancellation(client, amount, appointment_date="", service_name=""):
    """
    Notify a client that their appointment was cancelled because
    the booking deposit was not received within 72 hours.

    Uses the owner-editable template from SiteSettings → Email Templates.
    """
    if not client.email:
        return False

    ss = _get_site_settings()
    appointment_line = f" on {appointment_date}" if appointment_date else ""
    service_line = f" ({service_name})" if service_name else ""

    template = (ss.email_deposit_cancelled if ss and ss.email_deposit_cancelled else "")
    if not template:
        template = (
            "Hi {client_name},\n\n"
            "Your appointment{appointment_line}{service_line} has been cancelled.\n\n"
            "Unfortunately, the booking deposit was not received within 72 hours. "
            "Please let us know asap if you want to rebook.\n\n"
            "Best regards,\n"
            "Your Thermography Team"
        )

    plain_message = template.format_map(_SafeDict(
        client_name=client.name or "there",
        amount=str(amount),
        appointment_line=appointment_line,
        service_line=service_line,
    ))

    subject = "Appointment Cancelled — Booking Deposit Not Received"

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[client.email],
        fail_silently=False,
    )
    return True


def send_owner_new_booking_notice(client, deposit):
    """
    Notify the owner that a new booking arrived and needs review.

    Sent immediately when the Cal.com webhook creates a deposit in
    'awaiting_review' status so the owner knows to check Wagtail admin.
    """
    owner_email = _get_owner_email()
    if not owner_email:
        return False

    client_name = client.name or "Unknown"
    client_email_addr = client.email or "no email"
    date_str = deposit.appointment_date.strftime("%B %d, %Y") if deposit.appointment_date else "no date set"
    service = deposit.service_name or "Unknown service"

    subject = f"[Action Required] New booking from {client_name}"
    body = (
        f"A new booking has arrived and needs your review:\n\n"
        f"  Client:  {client_name}\n"
        f"  Email:   {client_email_addr}\n"
        f"  Service: {service}\n"
        f"  Date:    {date_str}\n"
        f"  Amount:  ${deposit.amount}\n\n"
        f"Please log in to Wagtail admin → Deposits to review this "
        f"booking and click 'Approve & Send Deposit Request' if everything "
        f"looks good.\n\n"
        f"The deposit request email will NOT be sent to the client until "
        f"you approve it.\n"
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=owner_email,
        recipient_list=[owner_email],
        fail_silently=False,
    )
    return True


def send_owner_deposit_expiry_notice(expired_deposits):
    """
    Notify the owner about deposits that were auto-forfeited and
    Cal.com bookings that were cancelled.
    """
    if not expired_deposits:
        return False

    owner_email = _get_owner_email()
    if not owner_email:
        return False

    count = len(expired_deposits)
    subject = f"[Auto] {count} appointment(s) cancelled — deposit not received"

    lines = [
        f"{count} booking(s) were automatically cancelled because the deposit "
        f"was not received within 72 hours:\n"
    ]

    for dep in expired_deposits:
        client_name = dep.client.name if dep.client_id else "Unknown"
        date_str = dep.appointment_date.strftime("%B %d, %Y") if dep.appointment_date else "no date"
        svc = dep.service_name or "Unknown service"
        lines.append(f"  - {client_name} — {svc} — {date_str} — ${dep.amount}")

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
