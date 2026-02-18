"""
Reusable StreamField block types for the homepage.

Each block defines:
  - fields the owner fills in via the admin panel
  - a template that renders the block on the public site

Block types:
  - AnnouncementBlock: dismissible coloured banner for time-sensitive notices
  - HeroBlock: big heading + subtext + button + background image
  - RichTextBlock: free-form formatted text (built into Wagtail)
  - TextWithImageBlock: text on one side, image on the other
  - ThreeColumnFeatureBlock: three icon/heading/text cards in a row
  - TwoColumnInfoBlock: heading + rich text in two equal columns
  - ServicesGridBlock: auto-pulls published Service pages into a card grid
  - ChecklistBlock: heading + checkmark list (e.g. "What to Expect")
  - TrustBlock: certifications/logos displayed in a row
  - WhyChooseUsBlock: heading + list of reasons with icons
  - TestimonialBlock: a client quote
  - NewsItemBlock: a news/event entry with date
  - FAQPreviewBlock: auto-pulls a few FAQ items with expandable answers
  - CallToActionBlock: highlighted banner with a button
  - BigCTABlock: full-width CTA with background image and overlay
  - ProcessStepsBlock: numbered horizontal steps (e.g. How It Works)
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
    ChoiceBlock,        # dropdown select
    IntegerBlock,       # integer input
    BooleanBlock,       # checkbox
)
from wagtail.images.blocks import ImageChooserBlock  # image picker


# ---------------------------------------------------------------------------
# AnnouncementBlock
# ---------------------------------------------------------------------------

class AnnouncementBlock(StructBlock):
    """
    A dismissible coloured banner for time-sensitive announcements.
    Appears at the top of the page — e.g. "Holiday Hours" or "New Service Available!"
    """
    message = RichTextBlock(
        help_text="Announcement text (supports links, bold, etc.).",
    )
    style = ChoiceBlock(
        choices=[
            ("info", "Info — teal/brand"),
            ("warning", "Warning — amber"),
            ("success", "Success — green"),
        ],
        default="info",
        help_text="Colour scheme for the banner.",
    )
    dismissible = BooleanBlock(
        required=False,
        default=True,
        help_text="Allow visitors to dismiss this banner?",
    )

    class Meta:
        template = "home/blocks/announcement_block.html"
        icon = "warning"
        label = "Announcement Banner"
        description = "A coloured banner at the top of the page for time-sensitive notices (e.g. holiday hours, new service)."


# ---------------------------------------------------------------------------
# HeroBlock
# ---------------------------------------------------------------------------

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
    button_link = CharBlock(
        max_length=200,
        required=False,
        default="/booking/",
        help_text="Where the button links to (e.g. /booking/ or https://example.com)"
    )
    background_image = ImageChooserBlock(
        required=False,
        help_text="Background image (optional)"
    )

    class Meta:
        template = "home/blocks/hero_block.html"
        icon = "image"
        label = "Hero Section"
        description = "The big banner at the very top of the page with a heading, subtext, and a button."


# ---------------------------------------------------------------------------
# ThreeColumnFeatureBlock
# ---------------------------------------------------------------------------

class FeatureColumnBlock(StructBlock):
    """A single column within the three-column feature section."""
    heading = CharBlock(max_length=100, help_text="Column heading (e.g. 'Non-Invasive').")
    text = TextBlock(help_text="Short description for this column.")

    class Meta:
        icon = "list-ul"
        label = "Feature Column"


class ThreeColumnFeatureBlock(StructBlock):
    """
    Three side-by-side feature cards — perfect for key selling points
    like 'Non-invasive', 'Pain-free', 'FDA registered'.
    """
    section_heading = CharBlock(
        max_length=200,
        required=False,
        help_text="Optional heading above the three columns.",
    )
    column_1 = FeatureColumnBlock()
    column_2 = FeatureColumnBlock()
    column_3 = FeatureColumnBlock()

    class Meta:
        template = "home/blocks/three_column_feature_block.html"
        icon = "grip"
        label = "Three-Column Features"
        description = "Three side-by-side cards — great for key selling points like 'Non-invasive', 'Pain-free', 'FDA registered'."


# ---------------------------------------------------------------------------
# TextWithImageBlock (existing)
# ---------------------------------------------------------------------------

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
    image_position = ChoiceBlock(
        choices=[("left", "Left"), ("right", "Right")],
        default="right",
        help_text="Which side the image appears on"
    )

    class Meta:
        template = "home/blocks/text_with_image_block.html"
        icon = "doc-full"
        label = "Text with Image"
        description = "A section with text on one side and a photo on the other — great for 'What is Thermography?' sections."


# ---------------------------------------------------------------------------
# TwoColumnInfoBlock
# ---------------------------------------------------------------------------

class TwoColumnInfoBlock(StructBlock):
    """
    Two equal columns of rich text, optionally under a shared heading.
    Good for 'Before Your Appointment / During Your Appointment'.
    """
    heading = CharBlock(max_length=200, required=False)
    left_heading = CharBlock(max_length=100, required=False, help_text="Heading for the left column.")
    left_content = RichTextBlock(help_text="Left column content.")
    right_heading = CharBlock(max_length=100, required=False, help_text="Heading for the right column.")
    right_content = RichTextBlock(help_text="Right column content.")

    class Meta:
        template = "home/blocks/two_column_info_block.html"
        icon = "doc-full-inverse"
        label = "Two-Column Info"
        description = "Two equal columns of text side by side — good for 'Before / During Your Appointment' info."


# ---------------------------------------------------------------------------
# ServicesGridBlock
# ---------------------------------------------------------------------------

class ServicesGridBlock(StructBlock):
    """
    Auto-pulls published ServicePage children into a responsive card grid.
    No manual entry needed — just add the block and it pulls live data.
    """
    heading = CharBlock(max_length=200, default="Our Services")
    subheading = TextBlock(required=False, help_text="Optional text below the heading.")
    featured_only = BooleanBlock(
        required=False,
        default=False,
        help_text="If checked, only services marked 'Featured' will display.",
    )

    class Meta:
        template = "home/blocks/services_grid_block.html"
        icon = "table"
        label = "Services Grid"
        description = "Automatically shows your services as a grid of cards — no manual entry needed."


# ---------------------------------------------------------------------------
# ChecklistBlock (What to Expect)
# ---------------------------------------------------------------------------

class ChecklistItemBlock(StructBlock):
    """A single checklist item."""
    text = CharBlock(max_length=300, help_text="Checklist item text.")

    class Meta:
        icon = "tick"
        label = "Checklist Item"


class ChecklistBlock(StructBlock):
    """
    A heading followed by a list of items with checkmarks.
    Ideal for 'What to Expect', 'How to Prepare', etc.
    """
    heading = CharBlock(max_length=200, default="What to Expect")
    intro = TextBlock(required=False, help_text="Optional intro text above the list.")
    items = ListBlock(ChecklistItemBlock())

    class Meta:
        template = "home/blocks/checklist_block.html"
        icon = "tasks"
        label = "Checklist"
        description = "A list with checkmarks — ideal for 'What to Expect' or 'How to Prepare' sections."


# ---------------------------------------------------------------------------
# TrustBlock
# ---------------------------------------------------------------------------

class TrustItemBlock(StructBlock):
    """A single trust badge — logo or text credential."""
    image = ImageChooserBlock(required=False, help_text="Logo or badge image (optional).")
    label = CharBlock(max_length=100, help_text="Label (e.g. 'IACT Certified').")

    class Meta:
        icon = "image"
        label = "Trust Badge"


class TrustBlock(StructBlock):
    """
    A row of certification logos, credentials, or partner badges.
    Builds credibility at a glance.
    """
    heading = CharBlock(max_length=200, default="Trusted & Certified", required=False)
    items = ListBlock(TrustItemBlock())

    class Meta:
        template = "home/blocks/trust_block.html"
        icon = "lock"
        label = "Trust / Credentials"
        description = "A row of logos or badges showing certifications and credentials — builds visitor trust."


# ---------------------------------------------------------------------------
# WhyChooseUsBlock
# ---------------------------------------------------------------------------

class ReasonBlock(StructBlock):
    """A single reason in the 'Why Choose Us' section."""
    heading = CharBlock(max_length=100, help_text="Reason heading (e.g. 'Experienced Team').")
    text = TextBlock(help_text="Short description of this reason.")

    class Meta:
        icon = "plus"
        label = "Reason"


class WhyChooseUsBlock(StructBlock):
    """
    A heading followed by a list of reasons with icons.
    Great for differentiating the business.
    """
    heading = CharBlock(max_length=200, default="Why Choose Us?")
    reasons = ListBlock(ReasonBlock())

    class Meta:
        template = "home/blocks/why_choose_us_block.html"
        icon = "pick"
        label = "Why Choose Us"
        description = "A list of reasons visitors should choose your business — helps differentiate you."


# ---------------------------------------------------------------------------
# TestimonialBlock (existing)
# ---------------------------------------------------------------------------

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
        description = "A client quote/review — adds social proof and builds trust."


# ---------------------------------------------------------------------------
# NewsItemBlock (existing)
# ---------------------------------------------------------------------------

class NewsItemBlock(StructBlock):
    """A news or event entry displayed on the homepage."""
    title = CharBlock(max_length=200, help_text="News headline or event name.")
    date = DateBlock(help_text="Date of the news item or event.")
    summary = TextBlock(help_text="Short description (1-2 sentences).")
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
        description = "A news or event entry with a date and summary."


# ---------------------------------------------------------------------------
# FAQPreviewBlock
# ---------------------------------------------------------------------------

class FAQPreviewBlock(StructBlock):
    """
    Auto-pulls FAQ items from the FAQ page and displays them as
    expandable accordions. Shows a 'View all FAQs' link at the bottom.
    """
    heading = CharBlock(max_length=200, default="Frequently Asked Questions")
    max_items = IntegerBlock(
        default=5,
        help_text="Maximum number of FAQ items to display.",
    )

    class Meta:
        template = "home/blocks/faq_preview_block.html"
        icon = "help"
        label = "FAQ Preview"
        description = "Automatically shows a few FAQ questions from your FAQ page — visitors can expand to read the answers."


# ---------------------------------------------------------------------------
# CallToActionBlock (existing — kept for backwards compatibility)
# ---------------------------------------------------------------------------

class CallToActionBlock(StructBlock):
    """A highlighted banner with a heading and button."""
    heading = CharBlock(max_length=200)
    text = TextBlock(required=False)
    button_text = CharBlock(max_length=50, default="Book Now")
    button_link = CharBlock(max_length=200, default="/booking/", help_text="e.g. /booking/ or https://example.com")

    class Meta:
        template = "home/blocks/cta_block.html"
        icon = "plus-inverse"
        label = "Call to Action"
        description = "A highlighted banner with a heading and button — use to encourage visitors to book or contact you."


# ---------------------------------------------------------------------------
# BigCTABlock
# ---------------------------------------------------------------------------

class BigCTABlock(StructBlock):
    """
    A full-width CTA section with optional background image, overlay,
    heading, body text, and a prominent button. Larger and more dramatic
    than the standard CallToActionBlock.
    """
    heading = CharBlock(max_length=200)
    text = TextBlock(required=False)
    button_text = CharBlock(max_length=50, default="Book Your Screening")
    button_link = CharBlock(max_length=200, default="/booking/", help_text="e.g. /booking/ or https://example.com")
    background_image = ImageChooserBlock(
        required=False,
        help_text="Background image — a dark overlay will be added for readability.",
    )

    class Meta:
        template = "home/blocks/big_cta_block.html"
        icon = "bold"
        label = "Big CTA"
        description = "A dramatic full-width call-to-action with an optional background image — great for the bottom of the page."


# ---------------------------------------------------------------------------
# ProcessStepsBlock
# ---------------------------------------------------------------------------

class StepBlock(StructBlock):
    """A single step in a process."""
    heading = CharBlock(max_length=100, help_text="Step title (e.g. 'Book Online', 'Visit Us', 'Get Results').")
    text = TextBlock(help_text="Short description of this step (1-2 sentences).")

    class Meta:
        icon = "order"
        label = "Step"


class ProcessStepsBlock(StructBlock):
    """
    A horizontal 'How It Works' section with 3–4 numbered steps.
    Reduces uncertainty and drives conversions.
    """
    heading = CharBlock(max_length=200, default="How It Works")
    steps = ListBlock(StepBlock())

    class Meta:
        template = "home/blocks/process_steps_block.html"
        icon = "order"
        label = "Process Steps"
        description = "A numbered 'How It Works' section — shows visitors the booking process step by step."