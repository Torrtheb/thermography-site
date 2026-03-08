"""
Data migration: re-save existing ClientReport rows so the notes field
is encrypted by the new EncryptedTextField.

from_db_value() decrypts on load (returns plaintext for unencrypted data),
and get_prep_value() encrypts on save — so a simple .save() round-trips
each row through encrypt.
"""

import os

from django.db import migrations


def encrypt_existing(apps, schema_editor):
    if not os.environ.get("FIELD_ENCRYPTION_KEY"):
        return
    from clients.models import ClientReport
    for obj in ClientReport.objects.exclude(notes=""):
        obj.save(update_fields=["notes"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0006_alter_clientreport_notes"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, noop),
    ]
