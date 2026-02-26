"""
Data migration: populate the HomePage StreamField with the recommended
section order and placeholder copy.

Everything inserted here is fully editable from Wagtail admin → Home Page.
The owner can reorder, edit, or delete any section at any time.
"""

import json
from django.db import migrations


HOMEPAGE_BODY = json.dumps([
    # ── 1. Hero ────────────────────────────────────────────────────────
    {
        "type": "hero",
        "value": {
            "heading": "Discover What Your Body Is Telling You",
            "subheading": (
                "Clinical thermography — a gentle, radiation-free way to "
                "reveal hidden inflammation and support your health journey. "
                "Serving communities across Vancouver Island."
            ),
            "button_text": "Book Your Appointment",
            "button_link": "/booking/",
            "background_image": None,
        },
    },

    # ── 2. Why Thermography – three columns ───────────────────────────
    {
        "type": "three_column_feature",
        "value": {
            "section_heading": "Why Thermography?",
            "column_1": {
                "heading": "Non-Invasive & Painless",
                "text": (
                    "No radiation, no compression, no contact. "
                    "A safe screening experience you can feel comfortable with."
                ),
            },
            "column_2": {
                "heading": "Early Risk Awareness",
                "text": (
                    "Detect inflammation patterns before symptoms appear. "
                    "Knowledge is a powerful step toward prevention."
                ),
            },
            "column_3": {
                "heading": "For Every Body",
                "text": (
                    "Safe during pregnancy, with implants, fibrocystic tissue, "
                    "or dense breasts. No age restrictions."
                ),
            },
        },
    },

    # ── 3. Services Grid (auto-pulls from ServicePage) ────────────────
    {
        "type": "services_grid",
        "value": {
            "heading": "Our Services",
            "subheading": (
                "Explore the thermography scans we offer and find the right "
                "fit for your health goals."
            ),
            "featured_only": False,
        },
    },

    # ── 4. What Is Thermography? – text with image ────────────────────
    {
        "type": "text_with_image",
        "value": {
            "heading": "What Is Thermography?",
            "text": (
                "<p>Thermography (also known as DITI — Digital Infrared "
                "Thermal Imaging) uses a specialized camera to capture heat "
                "patterns on the surface of your body. These thermal images "
                "can highlight areas of inflammation, circulatory changes, or "
                "unusual activity — offering valuable insights that support "
                "proactive health decisions.</p>"
                "<p>Unlike X-rays or mammograms, thermography uses no "
                "radiation and involves no physical contact. It\u2019s a "
                "functional screening tool that looks at how your body is "
                "responding, not just its structure.</p>"
            ),
            "image": None,
            "image_position": "right",
        },
    },

    # ── 5. What to Expect – process steps ─────────────────────────────
    {
        "type": "process_steps",
        "value": {
            "heading": "What to Expect",
            "steps": [
                {
                    "type": "item",
                    "value": {
                        "heading": "Choose Your Location",
                        "text": (
                            "We serve multiple communities across Vancouver "
                            "Island. Select the clinic nearest you."
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "heading": "Book Online",
                        "text": (
                            "Browse available services and appointment times, "
                            "then reserve your spot in minutes."
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "heading": "Your Visit",
                        "text": (
                            "Arrive scent-free. Your session is gentle, "
                            "private, and typically takes 30\u201360 minutes."
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "heading": "Your Report",
                        "text": (
                            "A certified thermologist interprets your images. "
                            "You\u2019ll receive a detailed report to discuss "
                            "with your healthcare provider."
                        ),
                    },
                },
            ],
        },
    },

    # ── 6. Upcoming Clinics (auto-pulls featured Locations) ───────────
    {
        "type": "upcoming_clinics",
        "value": {
            "heading": "Upcoming Clinics",
            "subheading": (
                "We bring thermography to you. "
                "See when we\u2019ll be in your area."
            ),
        },
    },

    # ── 7. Why Choose Us ──────────────────────────────────────────────
    {
        "type": "why_choose_us",
        "value": {
            "heading": "Your Comfort Is Our Priority",
            "reasons": [
                {
                    "type": "item",
                    "value": {
                        "heading": "Certified & Experienced",
                        "text": (
                            "Our technician holds professional certification "
                            "in clinical thermography and has years of "
                            "hands-on experience."
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "heading": "Personalized Attention",
                        "text": (
                            "Every session includes time for your questions. "
                            "You\u2019ll never feel rushed."
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "heading": "Accessible Locations",
                        "text": (
                            "We bring thermography to communities across "
                            "Vancouver Island so you don\u2019t have to "
                            "travel far."
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "heading": "Empowering, Not Alarming",
                        "text": (
                            "We help you understand your results clearly, "
                            "supporting informed conversations with your "
                            "healthcare team."
                        ),
                    },
                },
            ],
        },
    },

    # ── 8. Testimonials Carousel (auto-pulls featured snippets) ───────
    {
        "type": "testimonials",
        "value": {
            "heading": "What Our Clients Say",
            "show_count": 3,
        },
    },

    # ── 9. Preparing checklist ────────────────────────────────────────
    {
        "type": "checklist",
        "value": {
            "heading": "Preparing for Your Appointment",
            "intro": (
                "To ensure the most accurate results, please keep "
                "these guidelines in mind:"
            ),
            "items": [
                {
                    "type": "item",
                    "value": {
                        "text": (
                            "Avoid sun exposure and tanning on the area "
                            "being scanned for 5 days prior"
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "text": (
                            "Do not use lotions, creams, or deodorant on "
                            "the scan area the day of your visit"
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "text": (
                            "Avoid intensive exercise for 4 hours before "
                            "your appointment"
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "text": (
                            "Our clinic is scent-free \u2014 please refrain "
                            "from wearing perfume or strong scents"
                        ),
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "text": "Wear loose, comfortable clothing",
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "text": (
                            "Payment accepted: cash, cheque, or e-transfer"
                        ),
                    },
                },
            ],
        },
    },

    # ── 10. FAQ Preview (auto-pulls from FAQ page) ────────────────────
    {
        "type": "faq_preview",
        "value": {
            "heading": "Common Questions",
            "max_items": 5,
        },
    },

    # ── 11. Big CTA – closing ─────────────────────────────────────────
    {
        "type": "big_cta",
        "value": {
            "heading": "Ready to Take the Next Step?",
            "text": (
                "Whether it\u2019s your first thermography experience or a "
                "routine follow-up, we\u2019re here to support you. Book your "
                "appointment online in just a few clicks."
            ),
            "button_text": "Book Now",
            "button_link": "/booking/",
            "background_image": None,
        },
    },
])


def populate_homepage(apps, schema_editor):
    HomePage = apps.get_model("home", "HomePage")
    page = HomePage.objects.first()
    if page is None:
        return
    page.body = HOMEPAGE_BODY
    page.save(update_fields=["body"])


def clear_homepage(apps, schema_editor):
    """Reverse: reset body to empty."""
    HomePage = apps.get_model("home", "HomePage")
    page = HomePage.objects.first()
    if page is None:
        return
    page.body = "[]"
    page.save(update_fields=["body"])


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0015_sitesettings_logo_alter_sitesettings_business_name"),
    ]

    operations = [
        migrations.RunPython(populate_homepage, clear_homepage),
    ]
