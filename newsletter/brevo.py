"""
Brevo (Sendinblue) integration — sync newsletter subscribers to a Brevo contact list.

This module provides a simple function to add a contact to a Brevo list.
It's called automatically when someone subscribes via the site.

Required env vars (production):
  BREVO_API_KEY       — Your Brevo v3 API key (not SMTP key)
  BREVO_LIST_ID       — Numeric ID of the contact list to sync to

The sync is best-effort: if Brevo is unreachable the subscriber is still
saved locally and can be synced later via CSV export or a management command.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def add_contact_to_brevo(email: str) -> bool:
    """
    Add or update a contact in the configured Brevo list.
    Returns True on success, False on failure (logged, never raises).
    """
    api_key = getattr(settings, "BREVO_API_KEY", "")
    list_id = getattr(settings, "BREVO_LIST_ID", None)

    if not api_key or not list_id:
        logger.debug("Brevo sync skipped — BREVO_API_KEY or BREVO_LIST_ID not set.")
        return False

    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = api_key
        api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

        # Create or update the contact and add to the list
        contact = sib_api_v3_sdk.CreateContact(
            email=email,
            list_ids=[int(list_id)],
            update_enabled=True,  # update if contact already exists
        )
        api_instance.create_contact(contact)
        logger.info("Brevo: added/updated contact %s to list %s", email, list_id)
        return True

    except ApiException as e:
        # 409 = duplicate contact (already in list) — not an error
        if e.status == 409:
            logger.info("Brevo: contact %s already exists — skipped.", email)
            return True
        logger.warning("Brevo API error syncing %s: %s", email, e)
        return False
    except Exception:
        logger.exception("Unexpected error syncing %s to Brevo", email)
        return False


def remove_contact_from_brevo(email: str) -> bool:
    """
    Remove a contact from the configured Brevo list (not from Brevo entirely).
    Returns True on success, False on failure.
    """
    api_key = getattr(settings, "BREVO_API_KEY", "")
    list_id = getattr(settings, "BREVO_LIST_ID", None)

    if not api_key or not list_id:
        return False

    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = api_key
        api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

        body = sib_api_v3_sdk.RemoveContactFromList(emails=[email])
        api_instance.remove_contact_from_list(int(list_id), body)
        logger.info("Brevo: removed %s from list %s", email, list_id)
        return True

    except Exception:
        logger.exception("Error removing %s from Brevo list", email)
        return False


def unblock_contact_in_brevo(email: str) -> bool:
    """
    Remove a contact from Brevo's global SMTP blocklist (suppression list).

    When someone unsubscribes, Brevo may add them to a global blocklist that
    blocks ALL future emails (including transactional ones like contact-form
    notifications). This function lifts that block so emails can be delivered
    again — call it when a user explicitly re-subscribes.

    Uses the SMTP API (not Contacts API) because the blocklist is SMTP-level.
    Returns True on success, False on failure (logged, never raises).
    """
    api_key = getattr(settings, "BREVO_API_KEY", "")

    if not api_key:
        logger.debug("Brevo unblock skipped — BREVO_API_KEY not set.")
        return False

    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = api_key
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        # Remove from SMTP blocklist
        body = sib_api_v3_sdk.BlockDomain(email=email)
        api_instance.smtp_blocked_contacts_email_delete(email)
        logger.info("Brevo: unblocked %s from SMTP blocklist", email)
        return True

    except ApiException as e:
        if e.status == 404:
            # Contact wasn't on the blocklist — that's fine
            logger.debug("Brevo: %s was not on SMTP blocklist.", email)
            return True
        logger.warning("Brevo API error unblocking %s: %s", email, e)
        return False
    except Exception:
        logger.exception("Unexpected error unblocking %s in Brevo", email)
        return False
