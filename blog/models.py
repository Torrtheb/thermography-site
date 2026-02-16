"""
Blog / Resources app models.

Two page types:
  1. BlogIndexPage — the listing page at /resources/
     Shows all BlogPages as a grid of article cards.

  2. BlogPage — an individual blog post / article
     Each one has a title, author, date, cover image, excerpt, and body.

Page hierarchy:
  Root Page
    └── Home Page
    └── Blog Index Page              ← BlogIndexPage (one of these)
          ├── What Is Thermography?  ← BlogPage
          ├── 5 Benefits of ...      ← BlogPage
          └── Preparing for Your ... ← BlogPage
"""

from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.images import get_image_model_string


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
        """Add published blog posts to the template, newest first."""
        context = super().get_context(request, *args, **kwargs)
        context["posts"] = (
            BlogPage.objects.child_of(self).live().order_by("-publish_date")
        )
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

    is_featured = models.BooleanField(
        default=False,
        help_text="Featured posts may be highlighted on the homepage.",
    )

    @property
    def is_external(self):
        """True if this post links to an external article."""
        return bool(self.external_url)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("publish_date"),
                FieldPanel("author_name"),
            ],
            heading="Article Info",
        ),
        FieldPanel("cover_image"),
        FieldPanel("excerpt"),
        FieldPanel("external_url"),
        FieldPanel("body"),
        FieldPanel("is_featured"),
    ]

    parent_page_types = ["blog.BlogIndexPage"]

    class Meta:
        verbose_name = "Blog Post"
        ordering = ["-publish_date"]
