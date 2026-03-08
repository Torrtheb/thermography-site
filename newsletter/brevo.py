"""
Brevo integration — sync newsletter subscribers to a Brevo contact list.

Uses the official brevo-python v4 SDK (replaces deprecated sib-api-v3-sdk).

Required env vars (production):
  BREVO_API_KEY       — Your Brevo v3 API key (not SMTP key)
  BREVO_LIST_ID       — Numeric ID of the contact list to sync to

The sync is best-effort: if Brevo is unreachable the subscriber is still
saved locally and can be synced later via CSV export or a management command.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _redact_email(email: str) -> str:
    """Mask an email for safe logging, e.g. 'j***@example.com'."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _get_client():
    """Return a configured Brevo client, or None if the API key is missing."""
    api_key = getattr(settings, "BREVO_API_KEY", "")
    if not api_key:
        return None

    from brevo import Brevo
    return Brevo(api_key=api_key)


def add_contact_to_brevo(email: str) -> bool:
    """
    Add or update a contact in the configured Brevo list.
    Returns True on success, False on failure (logged, never raises).
    """
    list_id = getattr(settings, "BREVO_LIST_ID", None)
    client = _get_client()

    if not client or not list_id:
        logger.debug("Brevo sync skipped — BREVO_API_KEY or BREVO_LIST_ID not set.")
        return False

    try:
        from brevo.core.api_error import ApiError

        client.contacts.create_contact(
            email=email,
            list_ids=[int(list_id)],
            update_enabled=True,
        )
        logger.info("Brevo: added/updated contact %s to list %s", _redact_email(email), list_id)
        return True

    except ApiError as e:
        if e.status_code == 409:
            logger.info("Brevo: contact %s already exists — skipped.", _redact_email(email))
            return True
        logger.warning("Brevo API error syncing %s: %s", _redact_email(email), e)
        return False
    except Exception:
        logger.exception("Unexpected error syncing %s to Brevo", _redact_email(email))
        return False


def remove_contact_from_brevo(email: str) -> bool:
    """
    Remove a contact from the configured Brevo list (not from Brevo entirely).
    Returns True on success, False on failure.
    """
    list_id = getattr(settings, "BREVO_LIST_ID", None)
    client = _get_client()

    if not client or not list_id:
        return False

    try:
        from brevo.contacts.types import RemoveContactFromListRequestBodyEmails

        client.contacts.remove_contact_from_list(
            list_id=int(list_id),
            request=RemoveContactFromListRequestBodyEmails(emails=[email]),
        )
        logger.info("Brevo: removed %s from list %s", _redact_email(email), list_id)
        return True

    except Exception:
        logger.exception("Error removing %s from Brevo list", _redact_email(email))
        return False


def unblock_contact_in_brevo(email: str) -> bool:
    """
    Remove a contact from Brevo's global SMTP blocklist (suppression list).

    When someone unsubscribes, Brevo may add them to a global blocklist that
    blocks ALL future emails (including transactional ones like contact-form
    notifications). This function lifts that block so emails can be delivered
    again — call it when a user explicitly re-subscribes.

    Returns True on success, False on failure (logged, never raises).
    """
    client = _get_client()
    if not client:
        logger.debug("Brevo unblock skipped — BREVO_API_KEY not set.")
        return False

    try:
        from brevo.core.api_error import ApiError

        client.transactional_emails.unblock_or_resubscribe_a_transactional_contact(email)
        logger.info("Brevo: unblocked %s from SMTP blocklist", _redact_email(email))
        return True

    except ApiError as e:
        if e.status_code == 404:
            logger.debug("Brevo: %s was not on SMTP blocklist.", _redact_email(email))
            return True
        logger.warning("Brevo API error unblocking %s: %s", _redact_email(email), e)
        return False
    except Exception:
        logger.exception("Unexpected error unblocking %s in Brevo", _redact_email(email))
        return False
