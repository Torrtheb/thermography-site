from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0026_add_deposit_warning_email_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="gst_rate",
            field=models.DecimalField(
                verbose_name="GST rate (%)",
                max_digits=4,
                decimal_places=2,
                default=Decimal("5.00"),
                help_text="GST percentage applied to appointment prices (e.g. 5.00 for 5%). Used in deposit emails to show total with tax.",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="appointment_price_note",
            field=models.TextField(
                verbose_name="Appointment prices (shown in deposit email)",
                blank=True,
                default=(
                    "APPOINTMENT PRICES (including GST):\n"
                    "  \u2022 $310 service \u2192 $325.50 total\n"
                    "  \u2022 $555 service \u2192 $582.75 total\n"
                    "  \u2022 $940 service \u2192 $987.00 total"
                ),
                help_text=(
                    "Pricing summary shown in the deposit request email. "
                    "Edit freely to keep prices current. "
                    "Leave blank to hide this section from emails."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="email_deposit_request",
            field=models.TextField(
                verbose_name="Deposit request email body",
                default=(
                    "Hi {client_name},\n\n"
                    "Thank you for booking your {service_name} appointment{appointment_line}!\n\n"
                    "To confirm your booking, a non-refundable ${amount} e-transfer deposit is required.\n\n"
                    "HOW TO PAY:\n"
                    "  e-Transfer ${amount} to {etransfer_email}\n\n"
                    "Your ${amount} deposit will be applied toward your {total_with_gst} appointment fee "
                    "(includes GST). The remaining balance of {balance_due} is due on the day of your "
                    "appointment and can be paid by e-transfer, cash, or cheque. "
                    "You\u2019re also welcome to pay the full amount now.\n\n"
                    "A receipt will be issued to you along with your report.\n\n"
                    "Please note: only send e-Transfers to the address above. "
                    "We will never ask you to send money to a different address.\n\n"
                    "If you have any questions, please reply to this email.\n\n"
                    "Best regards,\n"
                    "Your Thermography Team"
                ),
                help_text=(
                    "Sent when a deposit request is approved. Available placeholders: "
                    "{client_name}, {amount}, {appointment_line}, {etransfer_email}, "
                    "{service_name}, {service_price} (price before tax), "
                    "{total_with_gst} (price + GST, e.g. \"$325.50\"), "
                    "{balance_due} (total minus deposit, e.g. \"$300.50\"). "
                    "Edit freely \u2014 placeholders are replaced when the email sends."
                ),
            ),
        ),
    ]
