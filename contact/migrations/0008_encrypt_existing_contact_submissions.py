# Data migration: encrypt existing ContactSubmission rows (plaintext → ciphertext).
# When FIELD_ENCRYPTION_KEY is set, re-saves each row so get_prep_value encrypts it.
# When unset (e.g. dev), skips so migrations don't fail; existing rows stay plaintext
# until key is set and you re-save or run a one-off encrypt command.

import os
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    if not os.environ.get("FIELD_ENCRYPTION_KEY"):
        return
    from contact.models import ContactSubmission
    for obj in ContactSubmission.objects.all():
        obj.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("contact", "0007_encrypt_contact_submission_fields"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, noop),
    ]
