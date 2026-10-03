# Softens the 48-hour reminder email wording from "within the next 24 hours"
# to "within approximately 24 hours", since the expiry sweep runs on a 6-hour
# cadence and the warning may land a few hours either side of the 48h mark.
#
#   1. AlterField — updates the model-level default (fresh installs).
#   2. RunPython  — updates the stored SiteSettings value, but ONLY if it still
#      matches the previous default (preserves any owner-customised wording).

from django.db import migrations, models


OLD_DEPOSIT_WARNING = (
    "Hi {client_name},\n\n"
    "This is a friendly reminder that the ${amount} booking deposit for your "
    "thermography appointment{appointment_line}{service_line} has not yet been received.\n\n"
    "If we do not receive the deposit within the next 24 hours, the appointment "
    "will be automatically cancelled.\n\n"
    "If you've already sent payment, please disregard this message — it may take "
    "a moment for us to process it.\n\n"
    "If you have any questions, please reply to this email.\n\n"
    "Best regards,\n"
    "Your Thermography Team"
)

NEW_DEPOSIT_WARNING = (
    "Hi {client_name},\n\n"
    "This is a friendly reminder that the ${amount} booking deposit for your "
    "thermography appointment{appointment_line}{service_line} has not yet been received.\n\n"
    "If we do not receive the deposit within approximately 24 hours, the appointment "
    "will be automatically cancelled.\n\n"
    "If you've already sent payment, please disregard this message — it may take "
    "a moment for us to process it.\n\n"
    "If you have any questions, please reply to this email.\n\n"
    "Best regards,\n"
    "Your Thermography Team"
)


def _swap(apps, old_value, new_value):
    SiteSettings = apps.get_model("home", "SiteSettings")
    for ss in SiteSettings.objects.all():
        if (ss.email_deposit_warning or "").strip() == old_value.strip():
            ss.email_deposit_warning = new_value
            ss.save(update_fields=["email_deposit_warning"])


def forwards(apps, schema_editor):
    _swap(apps, OLD_DEPOSIT_WARNING, NEW_DEPOSIT_WARNING)


def backwards(apps, schema_editor):
    _swap(apps, NEW_DEPOSIT_WARNING, OLD_DEPOSIT_WARNING)


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0028_deposit_request_72h_notice"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="email_deposit_warning",
            field=models.TextField(
                default=NEW_DEPOSIT_WARNING,
                help_text=(
                    "Sent 48 hours after booking if the deposit hasn't been received "
                    "(24 hours before cancellation). Placeholders: {client_name}, "
                    "{amount}, {appointment_line}, {service_line}."
                ),
                verbose_name="Deposit warning email body (48h reminder)",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
