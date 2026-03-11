# Generated migration for About page restructure — adds owner story,
# clinic story, and contact CTA fields to TechnicianPage.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("about", "0009_technicianpage_secondary_cta_button_fields"),
        ("wagtailimages", "0001_initial"),
    ]

    operations = [
        # Owner Story section
        migrations.AddField(
            model_name="technicianpage",
            name="owner_story_heading",
            field=models.CharField(
                blank=True,
                default="Our Story",
                help_text="Heading for the owner story section.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="owner_story_image",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional image for the owner story section (e.g. a candid photo).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="wagtailimages.image",
            ),
        ),

        # Clinic Story section
        migrations.AddField(
            model_name="technicianpage",
            name="clinic_story_heading",
            field=models.CharField(
                blank=True,
                default="Creating the Clinic",
                help_text="Heading for the clinic story section.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="clinic_story_image",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional second image (e.g. the mobile clinic or community event).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="wagtailimages.image",
            ),
        ),

        # Contact CTA section
        migrations.AddField(
            model_name="technicianpage",
            name="show_contact_cta",
            field=models.BooleanField(
                default=True,
                verbose_name="Show 'Reach Out' contact section",
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="contact_heading",
            field=models.CharField(
                default="Have Questions?",
                help_text="Heading for the contact CTA section.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="contact_text",
            field=models.TextField(
                blank=True,
                default="We'd love to hear from you. Reach out anytime — no question is too small.",
                help_text="Optional supporting text below the contact heading.",
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="contact_button_text",
            field=models.CharField(
                default="Get in Touch",
                help_text="Text shown on the contact button.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="technicianpage",
            name="contact_button_url",
            field=models.CharField(
                default="/contact/",
                help_text="URL for the contact button.",
                max_length=300,
            ),
        ),

        # Update existing field defaults/help_text
        migrations.AlterField(
            model_name="technicianpage",
            name="thermographers_heading",
            field=models.CharField(
                blank=True,
                default="People Reading Your Thermograms",
                help_text="Heading for the thermographer profiles section. Leave blank to hide.",
                max_length=200,
            ),
        ),
    ]
