"""
Management command: expire deposits that have been pending for more than 48 hours.

Usage:
  python manage.py expire_unpaid_deposits          # dry-run by default
  python manage.py expire_unpaid_deposits --apply   # actually expire them

Schedule this on Railway via a cron job (every hour is fine):
  railway run python manage.py expire_unpaid_deposits --apply

Or use Railway's built-in cron service / an external cron (e.g. cron-job.org)
to hit a URL, or add to start.sh as a one-shot before gunicorn starts.
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

        expired_deposits = Deposit.objects.filter(
            status="pending",
            created_at__lt=cutoff,
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
                f"\nDry run — {count} deposit(s) would be forfeited. "
                "Run with --apply to actually update them."
            ))
            return

        updated = expired_deposits.update(
            status="forfeited",
            updated_at=timezone.now(),
        )

        # Add note to each one explaining why
        for deposit in Deposit.objects.filter(
            pk__in=list(expired_deposits.values_list("pk", flat=True))
        ):
            deposit.notes = (
                (deposit.notes or "") +
                f"\nAuto-forfeited: deposit not received within {hours} hours of booking."
            )
            deposit.save(update_fields=["notes", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"\nForfeited {updated} deposit(s). "
            "The owner can see these in Wagtail admin → Deposits (filter by 'Forfeited')."
        ))
        logger.info("expire_unpaid_deposits: forfeited %d deposit(s) older than %d hours", updated, hours)
