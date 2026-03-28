"""
Management command: expire deposits that have been pending for more than 48 hours.

Usage:
  python manage.py expire_unpaid_deposits          # dry-run by default
  python manage.py expire_unpaid_deposits --apply   # actually expire them

When --apply is used, this command:
  1. Cancels the Cal.com booking (frees the slot)
  2. Emails each client about the cancellation
  3. Emails the owner a summary
  4. Marks deposits as "forfeited"
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from clients.models import Deposit

logger = logging.getLogger(__name__)

EXPIRY_HOURS = 48


class Command(BaseCommand):
    help = f"Forfeit deposits that have been pending for more than {EXPIRY_HOURS} hours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually update the records (without this flag, only a dry-run report is shown).",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=EXPIRY_HOURS,
            help=f"Number of hours before a pending deposit expires (default: {EXPIRY_HOURS}).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        hours = options["hours"]
        cutoff = timezone.now() - timezone.timedelta(hours=hours)

        from django.db.models import F, Q
        from django.db.models.functions import Coalesce

        expired_deposits = Deposit.objects.filter(
            Q(status="pending") | Q(status="awaiting_review"),
        ).annotate(
            timer_start=Coalesce(F("approved_at"), F("created_at")),
        ).filter(
            timer_start__lt=cutoff,
        ).select_related("client")

        count = expired_deposits.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No expired deposits found."))
            return

        self.stdout.write(f"Found {count} pending deposit(s) older than {hours} hours:\n")

        for deposit in expired_deposits:
            client_name = deposit.client.name if deposit.client_id else "Unknown"
            date_str = deposit.appointment_date.isoformat() if deposit.appointment_date else "no date"
            self.stdout.write(
                f"  - Deposit #{deposit.pk}: {client_name} — "
                f"${deposit.amount} — appt {date_str} — "
                f"created {deposit.created_at.isoformat()}"
            )

        if not apply:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {count} deposit(s) would be forfeited "
                f"and their Cal.com bookings cancelled. "
                "Run with --apply to actually do it."
            ))
            return

        from booking.webhooks import expire_pending_deposits
        forfeited = expire_pending_deposits(hours=hours)

        self.stdout.write(self.style.SUCCESS(
            f"\nForfeited {forfeited} deposit(s), cancelled their Cal.com bookings, "
            "and notified clients + owner."
        ))
        logger.info("expire_unpaid_deposits: forfeited %d deposit(s) older than %d hours", forfeited, hours)
