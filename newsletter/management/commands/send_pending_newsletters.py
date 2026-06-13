"""
Drain the newsletter send queue, throttled to the daily email budget.

This is the throttled replacement for sending a whole campaign at once.
Brevo's free plan caps the account at 300 emails/day, so a large list is
delivered over several days: each run sends up to NEWSLETTER_DAILY_SEND_LIMIT
emails (default 250, leaving headroom for welcome/transactional mail) and then
exits. It counts anything already sent today, so it is safe to run on an
hourly cron — once the daily budget is reached, further runs are no-ops until
the next day.

Usage:
    python manage.py send_pending_newsletters
    python manage.py send_pending_newsletters --limit 100
    python manage.py send_pending_newsletters --dry-run
"""

from django.core.management.base import BaseCommand

from newsletter.email import retry_failed_deliveries, send_pending_newsletters
from newsletter.models import NewsletterCampaign, NewsletterDelivery


class Command(BaseCommand):
    help = "Send queued newsletter emails, throttled to the daily budget."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Override the daily send budget (default: NEWSLETTER_DAILY_SEND_LIMIT).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent without sending anything.",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Re-queue previously failed deliveries (under the attempt cap) "
                 "before sending.",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            default=3,
            help="With --retry-failed, only retry deliveries below this many "
                 "attempts (default: 3).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        if options["dry_run"]:
            self._dry_run(limit)
            return

        if options["retry_failed"]:
            requeued = retry_failed_deliveries(max_attempts=options["max_attempts"])
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"Re-queued {requeued} failed delivery(ies) for retry."
                )
            )

        summary = send_pending_newsletters(
            daily_limit=limit,
            on_event=lambda msg: self.stdout.write(msg),
        )

        if summary["failed"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{summary['failed']} delivery(ies) failed this run — "
                    f"see logs. They will not be retried automatically."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {summary['sent']}, failed {summary['failed']}, "
                f"skipped {summary['skipped']}."
            )
        )

    def _dry_run(self, limit):
        from django.conf import settings

        daily_limit = limit or getattr(settings, "NEWSLETTER_DAILY_SEND_LIMIT", 250)
        queued = NewsletterCampaign.objects.filter(
            status__in=["queued", "sending"]
        ).order_by("created_at")
        pending_total = NewsletterDelivery.objects.filter(status="pending").count()
        failed_total = NewsletterDelivery.objects.filter(status="failed").count()
        retryable = NewsletterDelivery.objects.filter(
            status="failed", attempts__lt=3
        ).count()

        self.stdout.write(self.style.HTTP_INFO("DRY RUN — nothing will be sent."))
        self.stdout.write(f"  Daily budget:       {daily_limit}")
        self.stdout.write(f"  Pending deliveries: {pending_total}")
        self.stdout.write(
            f"  Failed deliveries:  {failed_total} "
            f"({retryable} retryable with --retry-failed)"
        )
        self.stdout.write(f"  Active campaigns:   {queued.count()}")
        for c in queued:
            self.stdout.write(
                f"    #{c.pk} '{c.subject}' — {c.pending_count} pending "
                f"(status={c.status})"
            )
        if pending_total:
            import math

            days = max(1, math.ceil(pending_total / daily_limit))
            self.stdout.write(
                f"  At {daily_limit}/day this clears in ~{days} day(s)."
            )
