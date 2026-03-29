"""Add imaging & reporting section fields to TechnicianPage."""

import wagtail.fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("wagtailimages", "0001_initial"),
        ("about", "0010_about_page_restructure"),
    ]

    operations = [
        migrations.AddField(
            model_name="technicianpage",
            name="imaging_heading",
            field=models.CharField(
                blank=True,
                default="Professional Imaging and Reporting",
                help_text="Heading for the imaging and reporting section. Leave blank to hide the section.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="imaging_body",
            field=wagtail.fields.RichTextField(
                blank=True,
                help_text="Description of the imaging and reporting process — who reads the scans, turnaround times, what clients receive, etc.",
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="imaging_image",
            field=models.ForeignKey(
                blank=True,
                help_text="Image for this section (e.g. a sample report, the imaging room, or professional equipment).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="wagtailimages.image",
            ),
        ),
    ]
