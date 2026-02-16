"""
Reusable StreamField block types for the homepage.

Each block defines:
  - fields the owner fills in via the admin panel
  - a template that renders the block on the public site

Block types:
  - HeroBlock: big heading + subtext + button + background image
  - RichTextBlock: free-form formatted text (built into Wagtail)
  - TextWithImageBlock: text on one side, image on the other
  - TestimonialBlock: a client quote
  - NewsItemBlock: a news/event entry with date
  - CallToActionBlock: highlighted banner with a button
"""

from wagtail.blocks import (
    CharBlock,          # single line of text
    TextBlock,          # multi-line plain text
    RichTextBlock,      # formatted text (bold, links, lists, etc.)
    URLBlock,           # a URL field
    DateBlock,          # a date picker
    StructBlock,        # a group of fields (like a mini-form)
    ListBlock,          # a repeatable list of one block type
    StreamBlock,        # the main container (menu of block types)
)
from wagtail.images.blocks import ImageChooserBlock  # image picker


class HeroBlock(StructBlock):
    """
    The big banner at the top of the page.
    Owner fills in: heading, subheading, button text, button link, background image.
    """
    heading = CharBlock(
        max_length=200,
        help_text="Main heading (e.g., 'Welcome to Thermography')"
    )
    subheading = TextBlock(
        required=False,
        help_text="Text below the heading"
    )
    button_text = CharBlock(
        max_length=50,
        default="Book an Appointment",
        help_text="Text on the button"
    )
    button_link = URLBlock(
        required=False,
        default="/booking/",
        help_text="Where the button links to"
    )
    background_image = ImageChooserBlock(
        required=False,
        help_text="Background image (optional)"
    )

    class Meta:
        template = "home/blocks/hero_block.html"
        icon = "image"
        label = "Hero Section"


class TextWithImageBlock(StructBlock):
    """
    A section with text on one side and an image on the other.
    Great for 'What is Thermography?' or 'Meet Your Technician'.
    """
    heading = CharBlock(max_length=200)
    text = RichTextBlock(
        help_text="Formatted text — supports bold, links, lists, etc."
    )
    image = ImageChooserBlock()
    image_position = CharBlock(
        max_length=5,
        default="right",
        help_text="'left' or 'right' — which side the image appears on"
    )

    class Meta:
        template = "home/blocks/text_with_image_block.html"
        icon = "doc-full"
        label = "Text with Image"


class TestimonialBlock(StructBlock):
    """A client testimonial/quote."""
    quote = TextBlock(help_text="The testimonial text")
    author = CharBlock(max_length=100, help_text="Client name")
    role = CharBlock(
        max_length=100,
        required=False,
        help_text="e.g., 'Client since 2024' (optional)"
    )

    class Meta:
        template = "home/blocks/testimonial_block.html"
        icon = "openquote"
        label = "Testimonial"


class NewsItemBlock(StructBlock):
    """A news or event entry displayed on the homepage."""
    title = CharBlock(max_length=200)
    date = DateBlock()
    summary = TextBlock(help_text="Short description")
    link = URLBlock(required=False, help_text="Link to full article (optional)")
    category = CharBlock(
        max_length=20,
        default="News",
        help_text="'News' or 'Event'"
    )

    class Meta:
        template = "home/blocks/news_item_block.html"
        icon = "date"
        label = "News / Event"


class CallToActionBlock(StructBlock):
    """A highlighted banner with a heading and button."""
    heading = CharBlock(max_length=200)
    text = TextBlock(required=False)
    button_text = CharBlock(max_length=50, default="Book Now")
    button_link = URLBlock(default="/booking/")

    class Meta:
        template = "home/blocks/cta_block.html"
        icon = "plus-inverse"
        label = "Call to Action"