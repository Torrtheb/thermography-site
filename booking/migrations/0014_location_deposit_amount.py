"""Add per-location deposit_amount override to Location model."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0013_bookingpage_deposit_instructions"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="deposit_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Deposit amount ($) for bookings at this location. Leave blank to use the global default from Site Settings.",
                max_digits=6,
                null=True,
            ),
        ),
    ]
