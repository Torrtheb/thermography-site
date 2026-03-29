"""Add sort_order field to ServicePage for manual ordering."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0011_servicesindexpage_cta_fields_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicepage",
            name="sort_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Lower numbers appear first. Services with the same number sort alphabetically.",
            ),
        ),
    ]
