"""
Custom Django email backend — sends via Brevo's transactional HTTP API.

Uses the official ``brevo-python`` v4 SDK to bypass SMTP entirely,
which avoids port-blocking issues on PaaS hosts like Railway.

The backend reads the API key from ``settings.BREVO_API_KEY``.

Usage in settings::

    EMAIL_BACKEND = "thermography_site.backends.brevo_email.BrevoAPIBackend"
"""

import logging
import re

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

_ADDRESS_RE = re.compile(r"^(.+?)\s*<(.+?)>\s*$")


def describe_send_failure(exc) -> str:
    """Turn a Brevo SDK exception into a short, human-readable reason.

    ``brevo``'s ``ApiError`` has an unhelpful ``repr`` (just ``ApiError()``),
    so failures used to surface as blank. Pull the HTTP status and Brevo's
    error message out so the reason is visible in logs, the admin, and the
    diagnostic command — e.g. "Brevo HTTP 401: Key not found" or
    "Brevo HTTP 400: sender ... is not valid".
    """
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    if status is not None:
        reason = ""
        if isinstance(body, dict):
            reason = body.get("message") or body.get("code") or ""
        elif body:
            reason = str(body)
        return f"Brevo HTTP {status}: {reason or 'no detail returned'}"
    return (str(exc) or type(exc).__name__).strip()[:300]


def _parse_address(address: str) -> dict:
    """Parse ``'Name <email>'`` into ``{'name': ..., 'email': ...}``."""
    match = _ADDRESS_RE.match(address)
    if match:
        return {"name": match.group(1).strip(), "email": match.group(2).strip()}
    return {"email": address.strip()}


class BrevoAPIBackend(BaseEmailBackend):
    """
    Django email backend that sends via Brevo's HTTP API (port 443).

    Drop-in replacement for the SMTP backend.  All existing ``send_mail()``
    and ``EmailMessage.send()`` calls work unchanged.
    """

    def __init__(self, api_key=None, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key or getattr(settings, "BREVO_API_KEY", "")

    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects via Brevo's transactional API.
        Returns the number of messages sent successfully.
        """
        if not self.api_key:
            logger.error(
                "BREVO_API_KEY is not set — cannot send email via Brevo API."
            )
            if not self.fail_silently:
                raise ValueError("BREVO_API_KEY is not configured")
            return 0

        from brevo import Brevo

        client = Brevo(api_key=self.api_key, timeout=15.0)

        sent_count = 0
        for message in email_messages:
            try:
                self._send_one(client, message)
                sent_count += 1
            except Exception as exc:
                detail = describe_send_failure(exc)
                logger.error(
                    "Brevo API: FAILED to send '%s' to %s — %s",
                    message.subject,
                    message.to,
                    detail,
                    exc_info=True,
                )
                if not self.fail_silently:
                    # Raise with the human-readable reason so it propagates to
                    # the admin "Email failed" badge and the test/diagnose
                    # commands (the raw ApiError's message is blank).
                    raise RuntimeError(detail) from exc

        return sent_count

    def _send_one(self, client, message):
        """Send a single EmailMessage via the Brevo transactional API."""
        from brevo.transactional_emails.types import (
            SendTransacEmailRequestSender,
            SendTransacEmailRequestToItem,
            SendTransacEmailRequestCcItem,
            SendTransacEmailRequestBccItem,
            SendTransacEmailRequestReplyTo,
        )

        from_email = message.from_email or settings.DEFAULT_FROM_EMAIL
        sender_parsed = _parse_address(from_email)
        sender = SendTransacEmailRequestSender(**sender_parsed)

        to_list = [
            SendTransacEmailRequestToItem(**_parse_address(addr))
            for addr in message.to
        ] if message.to else []

        cc_list = [
            SendTransacEmailRequestCcItem(**_parse_address(addr))
            for addr in message.cc
        ] if message.cc else None

        bcc_list = [
            SendTransacEmailRequestBccItem(**_parse_address(addr))
            for addr in message.bcc
        ] if message.bcc else None

        reply_to = None
        if message.reply_to:
            parsed = _parse_address(message.reply_to[0])
            reply_to = SendTransacEmailRequestReplyTo(**parsed)

        text_content = None
        html_content = None

        if hasattr(message, "alternatives") and message.alternatives:
            text_content = message.body
            for content, mimetype in message.alternatives:
                if mimetype == "text/html":
                    html_content = content
                    break
        elif getattr(message, "content_subtype", "plain") == "html":
            html_content = message.body
        else:
            text_content = message.body

        kwargs = {
            "to": to_list,
            "sender": sender,
            "subject": message.subject,
        }
        if text_content:
            kwargs["text_content"] = text_content
        if html_content:
            kwargs["html_content"] = html_content
        if cc_list:
            kwargs["cc"] = cc_list
        if bcc_list:
            kwargs["bcc"] = bcc_list
        if reply_to:
            kwargs["reply_to"] = reply_to

        extra = getattr(message, "extra_headers", {})
        if extra:
            kwargs["headers"] = extra

        result = client.transactional_emails.send_transac_email(**kwargs)
        logger.info(
            "Brevo API: sent '%s' to %s (message_id=%s)",
            message.subject,
            message.to,
            getattr(result, "message_id", "unknown"),
        )
        return result
