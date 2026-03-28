"""
Backfill email_hash for existing Client records.

Decrypts each client's email and stores the SHA-256 hash of the
lowercased value, enabling O(1) lookups by email without scanning
every row.
"""

import hashlib

from django.db import migrations


def backfill_email_hash(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    for client in Client.objects.all().iterator():
        if client.email:
            h = hashlib.sha256(
                client.email.strip().lower().encode("utf-8")
            ).hexdigest()
            if client.email_hash != h:
                client.email_hash = h
                client.save(update_fields=["email_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0012_add_client_email_hash"),
    ]

    operations = [
        migrations.RunPython(backfill_email_hash, migrations.RunPython.noop),
    ]
