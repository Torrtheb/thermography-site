from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0016_add_waived_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="deposit",
            name="expiry_warning_sent",
            field=models.BooleanField(
                default=False,
                help_text="Whether the 48-hour warning email has been sent (24 hours before cancellation).",
            ),
        ),
    ]
