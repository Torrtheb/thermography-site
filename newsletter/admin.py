import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "subscribed_at", "is_active"]
    list_filter = ["is_active", "subscribed_at"]
    search_fields = ["email"]
    readonly_fields = ["subscribed_at", "ip_hash"]
    actions = ["mark_active", "mark_unsubscribed", "export_as_csv"]

    @admin.action(description="Mark selected as active")
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected as unsubscribed")
    def mark_unsubscribed(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Export selected as CSV")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="newsletter_subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(["Email", "Subscribed At", "Active"])
        for sub in queryset.order_by("-subscribed_at"):
            writer.writerow([sub.email, sub.subscribed_at.isoformat(), sub.is_active])
        return response
