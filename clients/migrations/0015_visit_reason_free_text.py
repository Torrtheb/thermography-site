"""Remove choices constraint from previous_visit_reason; store Cal.com event title directly."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0014_add_confirmed_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="previous_visit_reason",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Service / reason for the most recent visit (auto-filled from Cal.com event title).",
                max_length=200,
            ),
        ),
    ]
