"""
Diagnose why Brevo transactional email is (or isn't) sending.

Run this on the server (e.g. `railway run python manage.py brevo_diagnose you@example.com`)
to get a definitive answer in one shot. It:

  1. Prints the effective email config (backend, from-address, API key shape).
  2. Authenticates the BREVO_API_KEY against Brevo's /account endpoint and
     prints the plan + remaining email credits (reveals a bad key or an
     exhausted daily/plan quota).
  3. Sends a real test email through the configured backend and prints the
     EXACT success/failure reason (the raw Brevo error is otherwise blank).

Usage:
    python manage.py brevo_diagnose you@example.com
    python manage.py brevo_diagnose you@example.com --no-send   # skip the test send
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Diagnose Brevo transactional email configuration and quota."

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?", help="Address to send a test email to.")
        parser.add_argument(
            "--no-send",
            action="store_true",
            help="Only check config + account; do not send a test email.",
        )

    def handle(self, *args, **options):
        email = options.get("email")
        info = self.style.HTTP_INFO
        ok = self.style.SUCCESS
        warn = self.style.WARNING
        err = self.style.ERROR

        self.stdout.write("")
        self.stdout.write(info("=" * 60))
        self.stdout.write(info(" Brevo email diagnostic"))
        self.stdout.write(info("=" * 60))

        # 1. Config ----------------------------------------------------------
        backend = getattr(settings, "EMAIL_BACKEND", "")
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        api_key = getattr(settings, "BREVO_API_KEY", "") or ""

        self.stdout.write(f"  EMAIL_BACKEND:      {backend}")
        self.stdout.write(f"  DEFAULT_FROM_EMAIL: {from_email!r}")

        if not api_key:
            self.stdout.write(err("  BREVO_API_KEY:      MISSING — set it in your env vars."))
        else:
            stripped = api_key.strip()
            shape = f"{stripped[:10]}…{stripped[-4:]} (len={len(stripped)})"
            self.stdout.write(f"  BREVO_API_KEY:      {shape}")
            if api_key != stripped:
                self.stdout.write(
                    err("  ⚠ API key has leading/trailing whitespace — this WILL cause "
                        "401 'Key not found'. Re-paste it with no spaces/newlines.")
                )
            if not stripped.startswith("xkeysib-"):
                self.stdout.write(
                    warn("  ⚠ API key does not start with 'xkeysib-'. A transactional "
                         "send needs an *API* key, not the SMTP key (xsmtpsib-).")
                )

        if "brevo" not in backend.lower():
            self.stdout.write(
                warn("  Note: the active backend is not the Brevo API backend, so this "
                     "environment won't reproduce production. Run with production settings.")
            )

        # 2. Account / quota check ------------------------------------------
        self.stdout.write("")
        self.stdout.write(info(" Account & quota"))
        self.stdout.write(info("-" * 60))
        if not api_key:
            self.stdout.write(err("  Skipped — no API key."))
        else:
            try:
                from brevo import Brevo

                client = Brevo(api_key=api_key.strip(), timeout=15.0)
                account = client.account.get_account()
                self.stdout.write(ok("  ✓ API key authenticated (GET /account succeeded)."))
                self._print_plan(account)
            except Exception as exc:
                from thermography_site.backends.brevo_email import describe_send_failure

                self.stdout.write(err(f"  ✗ Account check FAILED: {describe_send_failure(exc)}"))
                self.stdout.write(
                    warn("    A 401 here means the key is wrong/disabled/whitespaced or from "
                         "a different Brevo account.")
                )

        # 3. Live test send --------------------------------------------------
        if options["no_send"]:
            self.stdout.write("")
            self.stdout.write(warn("  Test send skipped (--no-send)."))
            return
        if not email:
            self.stdout.write("")
            self.stdout.write(warn("  No recipient given — skipping test send. "
                                   "Pass an address to send a test email."))
            return

        self.stdout.write("")
        self.stdout.write(info(" Live test send"))
        self.stdout.write(info("-" * 60))
        self.stdout.write(f"  Sending a test email to {email} via {backend} …")
        try:
            send_mail(
                subject="[Brevo diagnostic] Test email",
                message="If you received this, transactional email is working.",
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            self.stdout.write(ok("  ✓ Send returned success. Check the inbox (and spam)."))
        except Exception as exc:
            # The backend already formats the reason into the raised message.
            self.stdout.write(err(f"  ✗ Send FAILED: {exc}"))
            self.stdout.write(
                warn("  Common fixes:\n"
                     "   • 401 'Key not found'  → re-paste BREVO_API_KEY (no spaces), "
                     "or create a fresh API key.\n"
                     "   • 400 'sender ... not valid' → verify the DEFAULT_FROM_EMAIL "
                     "sender/domain in Brevo → Senders, Domains & Dedicated IPs.\n"
                     "   • quota / 'not enough credits' → Brevo free cap (300/day) hit; "
                     "wait for reset or upgrade.")
            )
            raise CommandError("Brevo test send failed — see reason above.")

    def _print_plan(self, account):
        """Best-effort print of plan + remaining credits from GET /account."""
        try:
            data = account
            if hasattr(account, "model_dump"):
                data = account.model_dump()
            elif hasattr(account, "dict"):
                data = account.dict()
            plan = None
            if isinstance(data, dict):
                plan = data.get("plan")
            if plan:
                for p in (plan if isinstance(plan, list) else [plan]):
                    if isinstance(p, dict):
                        ptype = p.get("type", "?")
                        credits = p.get("credits", p.get("creditsType", "?"))
                        self.stdout.write(
                            f"    plan type={ptype!r}  credits={credits!r}"
                        )
            else:
                self.stdout.write("    (plan/credits detail not present in response)")
        except Exception:
            self.stdout.write("    (could not parse plan detail; auth still succeeded)")
