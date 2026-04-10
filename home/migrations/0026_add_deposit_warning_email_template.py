from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0025_remove_sitesettings_email_deposit_confirmation"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="email_deposit_warning",
            field=models.TextField(
                verbose_name="Deposit warning email body (48h reminder)",
                default=(
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
                ),
                help_text=(
                    "Sent 48 hours after booking if the deposit hasn't been received (24 hours before cancellation). "
                    "Placeholders: {client_name}, {amount}, {appointment_line}, {service_line}."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="email_deposit_cancelled",
            field=models.TextField(
                verbose_name="Cancellation email body (72h rule)",
                default=(
                    "Hi {client_name},\n\n"
                    "We're writing to let you know that your thermography appointment"
                    "{appointment_line}{service_line} has been cancelled.\n\n"
                    "Unfortunately, the booking deposit was not received within 72 hours. "
                    "Please let us know asap if you want to rebook.\n\n"
                    "If you believe this was an error or you've already sent payment, "
                    "please reply to this email and we'll sort it out right away.\n\n"
                    "Best regards,\n"
                    "Your Thermography Team"
                ),
                help_text=(
                    "Sent automatically when a deposit expires after 72 hours. "
                    "Placeholders: {client_name}, {amount}, {appointment_line}, {service_line}."
                ),
            ),
        ),
    ]
