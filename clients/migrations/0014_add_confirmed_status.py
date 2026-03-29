"""Add 'confirmed' status to Deposit.status choices."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0013_backfill_email_hash"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deposit",
            name="status",
            field=models.CharField(
                choices=[
                    ("awaiting_review", "Awaiting Review — owner must approve"),
                    ("pending", "Pending — deposit request sent, awaiting payment"),
                    ("received", "Received — deposit paid"),
                    ("confirmed", "Confirmed — deposit secured, booking confirmed"),
                    ("forfeited", "Forfeited — client cancelled / no-show"),
                    ("applied", "Applied to service fee"),
                    ("refunded", "Refunded (exception)"),
                ],
                default="awaiting_review",
                max_length=20,
            ),
        ),
    ]
