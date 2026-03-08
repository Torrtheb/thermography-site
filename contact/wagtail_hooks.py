from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from contact.models import ContactSubmission


class ContactSubmissionViewSet(SnippetViewSet):
    """
    Staff-only list and detail view for contact form submissions.
    PII (name, email, phone, message) is encrypted at rest; decrypted only in admin.
    """
    model = ContactSubmission
    icon = "mail"
    menu_label = "Contact submissions"
    menu_name = "contact-submissions"
    menu_order = 300
    add_to_admin_menu = True
    list_display = ["name", "email", "phone", "submitted_at", "email_sent"]
    list_filter = ["email_sent", "submitted_at"]
    ordering = ["-submitted_at"]
    inspect_view_enabled = True
    # Encrypted fields cannot be searched in DB (ciphertext); filter by date/sent instead.
    search_fields = []


register_snippet(ContactSubmission, viewset=ContactSubmissionViewSet)
