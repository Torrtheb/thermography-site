# Step 2 - Content Model (v1)

## Goal
Define exactly what content exists, where it lives, and what the owner can edit in admin.

## 1) Global Site Settings (single place in admin)
Model: `SiteSettings`

| Field | Type | Required | Notes |
|---|---|---|---|
| business_name | short text | yes | Public brand name |
| phone | short text | yes | Display in header/footer/contact |
| email | short text | yes | Public contact email |
| address | long text | no | Business address |
| booking_url | URL | yes | External booking link/embed |
| emergency_banner_text | short text | no | Optional urgent notice |
| facebook_url | URL | no | Social link |
| instagram_url | URL | no | Social link |
| default_seo_description | short text | no | Default meta description |

## 2) Page Types

### Home Page
Model: `HomePage` (single page)
- `hero_title` (short text, required)
- `hero_subtitle` (long text, optional)
- `hero_image` (image, required)
- `body_sections` (flexible block field, required)
- `featured_services` (list/relationship, optional)
- `featured_articles` (list/relationship, optional)
- `featured_news_events` (list/relationship, optional)

### Services
Model: `ServicesIndexPage` (listing page)
- `intro` (long text, optional)

Model: `ServicePage` (child pages under Services)
- `title` (required)
- `slug` (required)
- `short_summary` (short text, required)
- `description` (rich text, required)
- `price_label` (short text, required) Example: "$150"
- `duration_label` (short text, optional) Example: "60 minutes"
- `service_image` (image, optional)
- `is_featured` (boolean, optional)

### Meet Your Technician
Model: `TechnicianPage` (single page)
- `full_name` (short text, required)
- `headshot` (image, required)
- `bio` (rich text, required)
- `credentials` (rich text, optional)
- `years_experience` (number, optional)

### Articles/Blog
Model: `BlogIndexPage`
- `intro` (long text, optional)

Model: `BlogPage`
- `title` (required)
- `publish_date` (date, required)
- `author_name` (short text, required)
- `cover_image` (image, optional)
- `excerpt` (short text, required)
- `body` (rich text or block field, required)
- `is_featured` (boolean, optional)

### News/Events
Model: `NewsEventsIndexPage`
- `intro` (long text, optional)

Model: `NewsEventPage`
- `title` (required)
- `item_type` (choice: `news` or `event`, required)
- `start_date` (date, required)
- `end_date` (date, optional)
- `location` (short text, optional)
- `excerpt` (short text, required)
- `body` (rich text, required)
- `image` (image, optional)
- `is_featured` (boolean, optional)

### FAQ
Model: `FAQPage`
- `intro` (long text, optional)
- `faq_items` (repeatable question/answer blocks, required)

### Contact
Model: `ContactPage`
- `intro` (long text, optional)
- `contact_email` (short text, required)
- `contact_phone` (short text, required)
- `address` (long text, optional)
- `map_embed_url` (URL, optional)
- `contact_form_enabled` (boolean, required)

### Booking
Model: `BookingPage`
- `headline` (short text, required)
- `instructions` (long text, optional)
- `booking_provider` (choice: `calendly` or `cal_com`, required)
- `booking_url` (URL, required)
- `show_embed` (boolean, required)

## 3) Home Flexible Sections (owner can add/reorder)
Block library for `HomePage.body_sections`:
- Hero CTA block
- Text + image block
- Image gallery block
- Featured services block
- Featured articles block
- Featured news/events block
- FAQ teaser block
- Contact CTA block

## 4) Editorial Rules
- Owner edits only through admin UI; no code.
- Every image must have alt text.
- Draft -> review -> publish workflow for all pages.
- Slugs use lowercase and hyphens.
- Do not delete published pages without replacement.

## 5) Relationships and Navigation
- `HomePage` can feature items from Services, Blog, News/Events.
- Header nav: Home, Services, Technician, Articles, News/Events, FAQ, Contact, Book.
- Footer includes contact + social links from `SiteSettings`.

## 6) v1 Boundaries
- No client accounts.
- No custom booking database logic yet.
- No payment/paywall yet.
- No AI assistant yet.
