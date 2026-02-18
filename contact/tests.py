from django.core.cache import cache
from django.test import TestCase

from wagtail.models import Page, Site

from contact.models import (
    CONTACT_RATE_LIMIT,
    ContactPage,
    ContactSubmissionRateLimit,
)


class ContactRateLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        root = Page.get_first_root_node()

        cls.contact_page = ContactPage(
            title="Contact",
            slug="contact",
            contact_email="owner@example.com",
            contact_phone="555-111-2222",
            contact_form_enabled=True,
        )
        root.add_child(instance=cls.contact_page)
        cls.contact_page.save_revision().publish()

        Site.objects.update(is_default_site=False)
        Site.objects.update_or_create(
            hostname="testserver",
            defaults={
                "root_page": root,
                "is_default_site": True,
                "site_name": "Test Site",
            },
        )

    def setUp(self):
        cache.clear()
        ContactSubmissionRateLimit.objects.all().delete()

    def test_db_rate_limit_blocks_after_threshold_even_when_cache_cleared(self):
        form_data = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-123-4567",
            "message": "Testing contact form delivery.",
        }

        # Submit up to the allowed limit, clearing cache each time to ensure
        # DB-backed counting is what enforces the final block.
        for _ in range(CONTACT_RATE_LIMIT):
            response = self.client.post(self.contact_page.url, form_data)
            self.assertContains(response, "Message Sent!")
            cache.clear()

        blocked = self.client.post(self.contact_page.url, form_data)
        self.assertContains(blocked, "Too many submissions. Please try again later.")

        ip_hash = ContactSubmissionRateLimit.hash_ip("127.0.0.1")
        window_key = ContactSubmissionRateLimit.current_window_key()
        self.assertEqual(
            ContactSubmissionRateLimit.get_count(ip_hash, window_key),
            CONTACT_RATE_LIMIT,
        )
