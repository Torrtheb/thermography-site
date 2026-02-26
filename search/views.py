import re
from html import escape as html_escape

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

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

# ──────────────────────────────────────────────────────────
# Excerpt helpers — extract the sentence containing the keyword
# ──────────────────────────────────────────────────────────

# Sentence-ending punctuation (split points)
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')

# Fields to pull plain text from, in priority order per page type.
_TEXT_FIELDS = [
    "excerpt", "short_summary", "intro", "description", "body",
    "bio", "full_name",
    "step1_body", "step2_body", "step3_body",
    "step4_body", "step5_body", "step6_body",
    "faq_items",
]


def _get_plain_text(page):
    """Collect all searchable text from a page into a single string."""
    specific = page.specific
    parts = []
    for field in _TEXT_FIELDS:
        val = getattr(specific, field, None)
        if not val:
            continue
        text = str(val)
        # Strip HTML tags and collapse whitespace
        text = strip_tags(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _build_excerpt(page, query, max_len=220):
    """
    Find the sentence containing `query` and return an HTML-safe excerpt
    with the keyword wrapped in <mark>.

    Falls back to search_description, then the first ~max_len chars of
    page text if the keyword isn't found in a sentence.
    """
    if not query:
        return ""

    full_text = _get_plain_text(page)
    if not full_text:
        # Last resort: use page search_description
        return html_escape(page.search_description or "")

    # Try to find a sentence containing the keyword
    query_lower = query.lower()
    sentences = _SENTENCE_RE.split(full_text)

    best = None
    for sentence in sentences:
        if query_lower in sentence.lower():
            best = sentence.strip()
            break

    if not best:
        # Keyword not in a single sentence — try a sliding window
        idx = full_text.lower().find(query_lower)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(full_text), idx + len(query) + 140)
            best = full_text[start:end].strip()
            if start > 0:
                best = "…" + best
            if end < len(full_text):
                best = best + "…"
        else:
            # Keyword not in body at all — show start of text
            best = full_text[:max_len].strip()
            if len(full_text) > max_len:
                best = best + "…"

    # Truncate if the sentence is very long
    if len(best) > max_len:
        # Cut around the keyword position
        idx = best.lower().find(query_lower)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(best), idx + len(query) + 140)
            best = best[start:end].strip()
            if start > 0:
                best = "…" + best
            if end < len(best):
                best = best + "…"
        else:
            best = best[:max_len] + "…"

    # Highlight the keyword with <mark>
    safe_text = html_escape(best)
    pattern = re.compile(re.escape(html_escape(query)), re.IGNORECASE)
    highlighted = pattern.sub(
        lambda m: f'<mark class="bg-brand-100 text-brand-800 px-0.5 rounded">{m.group()}</mark>',
        safe_text,
    )

    return mark_safe(highlighted)


def _page_type_label(page):
    """Human-friendly label for the page type."""
    labels = {
        "ServicePage": "Service",
        "BlogPage": "Article",
        "FAQPage": "FAQ",
        "FirstVisitPage": "First Visit",
        "ContactPage": "Contact",
        "BookingPage": "Booking",
        "TechnicianPage": "About",
        "HomePage": "Home",
        "ServicesIndexPage": "Services",
        "BlogIndexPage": "Resources",
    }
    class_name = page.specific_class.__name__
    return labels.get(class_name, class_name)


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

    # Build excerpts and type labels for each result
    annotated_results = []
    for result in search_results:
        annotated_results.append({
            "page": result,
            "excerpt": _build_excerpt(result, search_query),
            "type_label": _page_type_label(result),
        })

    return TemplateResponse(
        request,
        "search/search.html",
        {
            "search_query": search_query,
            "search_results": search_results,
            "annotated_results": annotated_results,
        },
    )
