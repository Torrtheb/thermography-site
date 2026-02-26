"""
Blog / Resources app models.

Three page types concern here:
  1. BlogIndexPage — the listing page at /resources/
     Shows all BlogPages grouped by category with section navigation.

  2. BlogPage — an individual blog post / article
     Each one has a title, author, date, cover image, excerpt, body,
     and a category for grouping into subsections.

Categories (subsections):
  - "what-is-thermography" → What is Thermography?
  - "articles" → Articles

Page hierarchy:
  Root Page
    └── Home Page
    └── Blog Index Page              ← BlogIndexPage (one of these)
          ├── What Is Thermography?  ← BlogPage (category: what-is-thermography)
          ├── 5 Benefits of ...      ← BlogPage (category: articles)
          └── Preparing for Your ... ← BlogPage (category: articles)
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.images import get_image_model_string
from wagtail.search import index
from wagtail.snippets.models import register_snippet


CATEGORY_CHOICES = [
    ("what-is-thermography", "What is Thermography?"),
    ("articles", "Articles"),
]


class BlogIndexPage(Page):
    """
    The listing page for blog posts / resources.
    Shows all published BlogPages, newest first.

    max_count = 1: only one blog index.
    subpage_types: only BlogPage children.
    """

    intro = models.TextField(
        blank=True,
        help_text="Optional intro text shown above the articles.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    max_count = 1
    subpage_types = ["blog.BlogPage"]

    def get_context(self, request, *args, **kwargs):
        """Add published blog posts to the template, grouped by category."""
        context = super().get_context(request, *args, **kwargs)

        # Evaluate once to avoid repeated DB queries per category
        all_posts = list(
            BlogPage.objects.child_of(self).live().public().order_by("-publish_date")
        )

        # Category filter from URL: /resources/?category=articles
        active_category = request.GET.get("category", "")
        context["active_category"] = active_category
        context["categories"] = CATEGORY_CHOICES

        if active_category and active_category != "experts":
            context["posts"] = [p for p in all_posts if p.category == active_category]
        elif active_category == "experts":
            context["posts"] = []  # no blog posts when viewing experts
        else:
            context["posts"] = all_posts

        # Group posts by category for the "all" view (in-memory, no extra queries)
        context["sections"] = []
        for slug, label in CATEGORY_CHOICES:
            section_posts = [p for p in all_posts if p.category == slug]
            if section_posts:
                context["sections"].append({
                    "slug": slug,
                    "label": label,
                    "posts": section_posts,
                })

        # Meet the Experts — auto-pull active Expert snippets
        context["experts"] = Expert.objects.filter(is_active=True)

        return context

    class Meta:
        verbose_name = "Blog Index Page"


class BlogPage(Page):
    """
    An individual blog post / article.

    parent_page_types: can only live under BlogIndexPage.
    """

    publish_date = models.DateField(
        help_text="The date shown on the article (used for ordering).",
    )

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="articles",
        help_text="Which section this post belongs to on the Resources page.",
    )

    author_name = models.CharField(
        max_length=100,
        help_text="Author name displayed on the article.",
    )

    cover_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional cover image shown at the top of the post and on the card.",
    )

    excerpt = models.CharField(
        max_length=300,
        help_text="Short summary shown on the blog listing card (max 300 chars).",
    )

    external_url = models.URLField(
        blank=True,
        help_text="Link to an external article. If filled, the card links here instead of a detail page.",
    )

    body = RichTextField(
        blank=True,
        help_text="The full article content. Leave empty for external links.",
    )

    related_service = models.ForeignKey(
        "services.ServicePage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blog_posts",
        help_text="Optional: link this article to a specific service. A booking button will appear at the bottom.",
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Featured posts may be highlighted on the homepage.",
    )

    citation = models.TextField(
        blank=True,
        help_text="Citation or credit for the article source/author (e.g., 'Smith, J. (2025). Thermography Today, 12(3), 45-52.').",
    )

    source_url = models.URLField(
        blank=True,
        help_text="Optional link to the original source article.",
    )

    @property
    def is_external(self):
        """True if this post links to an external article."""
        return bool(self.external_url)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("publish_date"),
                FieldPanel("category"),
                FieldPanel("author_name"),
            ],
            heading="Article Info",
        ),
        FieldPanel("cover_image"),
        FieldPanel("excerpt"),
        FieldPanel("external_url"),
        FieldPanel("body"),
        MultiFieldPanel(
            [
                FieldPanel("citation"),
                FieldPanel("source_url"),
            ],
            heading="Citation / Source Credit",
        ),
        FieldPanel("related_service"),
        FieldPanel("is_featured"),
    ]

    parent_page_types = ["blog.BlogIndexPage"]

    search_fields = Page.search_fields + [
        index.SearchField("body"),
        index.SearchField("excerpt"),
        index.SearchField("author_name"),
        index.SearchField("citation"),
    ]

    class Meta:
        verbose_name = "Blog Post"


# ──────────────────────────────────────────────────────────
# Expert (Wagtail Snippet — "Meet the Experts" on Resources page)
# ──────────────────────────────────────────────────────────

SPECIALTY_CHOICES = [
    ("thermographer", "Thermographer"),
    ("hormone-practitioner", "Hormone Practitioner"),
    ("naturopath", "Naturopath"),
    ("health-coach", "Health Coach"),
    ("other", "Other"),
]


@register_snippet
class Expert(index.Indexed, models.Model):
    """
    A practitioner or key partner highlighted on the Resources page.

    The owner manages these from Wagtail admin → Snippets → Experts.
    """

    name = models.CharField(
        max_length=150,
        help_text="Full name (e.g., 'Dr. Jane Smith').",
    )

    specialty = models.CharField(
        max_length=50,
        choices=SPECIALTY_CHOICES,
        default="thermographer",
        help_text="Primary specialty — used for the badge label.",
    )

    title_role = models.CharField(
        max_length=200,
        blank=True,
        help_text="Professional title, e.g. 'Certified Clinical Thermographer' or 'RHN, Hormone Health Specialist'.",
    )

    photo = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Professional headshot (square crop works best).",
    )

    bio = models.TextField(
        help_text="Short bio (2–4 sentences). What they do & why they're great.",
    )

    website = models.URLField(
        blank=True,
        help_text="Link to their website or profile (optional).",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide without deleting.",
    )

    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first.",
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("name"),
                FieldPanel("specialty"),
                FieldPanel("title_role"),
            ],
            heading="Identity",
        ),
        FieldPanel("photo"),
        FieldPanel("bio"),
        FieldPanel("website"),
        FieldPanel("is_active"),
        FieldPanel("sort_order"),
    ]

    search_fields = [
        index.SearchField("name"),
        index.SearchField("bio"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Expert"
        verbose_name_plural = "Experts"

    def __str__(self):
        return f"{self.name} ({self.get_specialty_display()})"
