"""Create PlaceholderBooking model for cross-event-type slot blocking."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0014_location_deposit_amount"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlaceholderBooking",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "original_booking_uid",
                    models.CharField(
                        db_index=True,
                        help_text="Cal.com UID of the real booking that triggered these placeholders.",
                        max_length=200,
                    ),
                ),
                (
                    "placeholder_booking_uid",
                    models.CharField(
                        help_text="Cal.com UID of the placeholder booking to cancel later.",
                        max_length=200,
                        unique=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Placeholder booking",
                "verbose_name_plural": "Placeholder bookings",
            },
        ),
    ]
