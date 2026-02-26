from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from contact.models import ContactSubmission


class ContactSubmissionViewSet(SnippetViewSet):
    model = ContactSubmission
    icon = "mail"
    menu_label = "Contact Submissions"
    menu_name = "contact-submissions"
    menu_order = 300
    add_to_admin_menu = True
    list_display = ["name", "email", "phone", "submitted_at", "email_sent"]
    list_filter = ["email_sent", "submitted_at"]
    search_fields = ["name", "email", "message"]
    ordering = ["-submitted_at"]
    inspect_view_enabled = True

    # Submissions are created by visitors, not admins.
    add_to_settings_menu = False


register_snippet(ContactSubmission, viewset=ContactSubmissionViewSet)
