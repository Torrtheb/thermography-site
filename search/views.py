import re

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from wagtail.models import Page

# Keywords that indicate the user wants the services page
# Require multi-word phrases or very specific terms to avoid false positives
SERVICES_KEYWORDS = re.compile(
    r"\b(pricing|how\s+much|service(?:s)?\s+(?:offered|available|list|page)|"
    r"what\s+(?:do\s+you|services)\s+offer|your\s+services)\b",
    re.IGNORECASE,
)

# Keywords that indicate the user wants the booking page
# Require 2+ word phrases or very specific single words to avoid false positives
BOOKING_KEYWORDS = re.compile(
    r"\b(book(?:ing)?\s+(?:an\s+)?appointment|schedule\s+(?:an\s+)?appointment|"
    r"book\s+now|make\s+an?\s+appointment|book\s+a\s+session|reschedule)\b",
    re.IGNORECASE,
)


def search(request):
    search_query = request.GET.get("query", None)
    page = request.GET.get("page", 1)

    # Smart redirects for common intent searches
    if search_query:
        q = search_query.strip()

        # Check booking intent first (more specific)
        if BOOKING_KEYWORDS.search(q):
            return redirect("/booking/")

        # Check services/pricing intent
        if SERVICES_KEYWORDS.search(q):
            return redirect("/services/")

    # Standard search
    if search_query:
        search_results = Page.objects.live().public().search(search_query)
    else:
        search_results = Page.objects.none()

    # Pagination
    paginator = Paginator(search_results, 10)
    try:
        search_results = paginator.page(page)
    except PageNotAnInteger:
        search_results = paginator.page(1)
    except EmptyPage:
        search_results = paginator.page(paginator.num_pages)

    return TemplateResponse(
        request,
        "search/search.html",
        {
            "search_query": search_query,
            "search_results": search_results,
        },
    )
