from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from clients.models import Client, Deposit


class OwnerNewBookingNoticeTests(TestCase):
    """The owner notification should include the client's phone and email."""

    def test_notice_includes_phone_and_email(self):
        from clients.email import send_owner_new_booking_notice

        client = Client.objects.create(
            name="Jane Doe",
            email="jane@example.com",
            phone="250-555-1234",
        )
        deposit = Deposit.objects.create(client=client, amount="25.00", status="pending")

        mail.outbox = []
        send_owner_new_booking_notice(client, deposit)

        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("jane@example.com", body)
        self.assertIn("250-555-1234", body)

    def test_notice_handles_missing_phone(self):
        from clients.email import send_owner_new_booking_notice

        client = Client.objects.create(name="No Phone", email="np@example.com")
        deposit = Deposit.objects.create(client=client, amount="25.00", status="pending")

        mail.outbox = []
        send_owner_new_booking_notice(client, deposit)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("no phone", mail.outbox[0].body)


class PendingDepositResendButtonTests(TestCase):
    """Pending deposits must expose a one-click 'Send Deposit Email' button."""

    def test_pending_deposit_shows_send_email_button(self):
        client = Client.objects.create(name="Lost Email", email="lost@example.com")
        deposit = Deposit.objects.create(client=client, amount="25.00", status="pending")

        html = str(deposit.status_and_actions())
        self.assertIn(f"/admin/deposits/{deposit.pk}/send-request/", html)
        self.assertIn("Send Deposit Email", html)

    def test_confirmed_deposit_has_no_send_button(self):
        client = Client.objects.create(name="Done", email="done@example.com")
        deposit = Deposit.objects.create(client=client, amount="25.00", status="confirmed")

        html = str(deposit.status_and_actions())
        self.assertNotIn("/send-request/", html)


class SendDepositEmailViewTests(TestCase):
    """Manual-booking deposit email flow: create a pending deposit + send."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="owner", email="owner@example.com", password="pw12345!",
        )
        self.client.force_login(self.admin)
        self.url = reverse("deposit_send_email")

    def test_get_renders_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Send Deposit Email")

    def test_post_creates_pending_deposit_and_sends(self):
        person = Client.objects.create(name="Manual Client", email="manual@example.com")

        with mock.patch("clients.views._send_email_async") as mocked_send:
            resp = self.client.post(self.url, {
                "client": person.pk,
                "amount": "40.00",
                "appointment_date": "2026-07-01",
                "service_name": "Full Body Scan",
            })

        self.assertEqual(resp.status_code, 302)
        deposit = Deposit.objects.get(client=person)
        self.assertEqual(deposit.status, "pending")
        self.assertTrue(deposit.deposit_request_sent)
        self.assertIsNotNone(deposit.approved_at)
        self.assertEqual(str(deposit.amount), "40.00")
        self.assertEqual(deposit.service_name, "Full Body Scan")
        mocked_send.assert_called_once()

    def test_post_rejects_client_without_email(self):
        person = Client.objects.create(name="No Email")  # no email

        with mock.patch("clients.views._send_email_async") as mocked_send:
            resp = self.client.post(self.url, {
                "client": person.pk,
                "amount": "25.00",
            })

        # Form re-renders with an error; no deposit created, no email sent.
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Deposit.objects.filter(client=person).exists())
        mocked_send.assert_not_called()
        self.assertContains(resp, "no email address on file")

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, (302, 403))
