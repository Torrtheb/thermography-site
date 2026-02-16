# Step 3 - Repo and App Structure (v1)

## Goal
Define a clean Django/Wagtail project layout so each feature lives in its own app and is easy to maintain.

## 1) Top-Level Structure

thermography/
- docs/
- .env.example
- .gitignore
- README.md
- requirements.txt
- manage.py
- config/
- apps/
- templates/
- static/
- media/
- tests/

## 2) What Each Folder Is For

- `docs/`: project decisions and step-by-step notes (`01_mvp_scope.md`, `02_content_model.md`, etc.)
- `config/`: Django project settings, urls, asgi/wsgi
- `apps/`: all feature apps (modular code)
- `templates/`: shared base templates
- `static/`: css/js/images used by frontend
- `media/`: uploaded files (Wagtail images/docs)
- `tests/`: integration tests across apps

## 3) App Modules (v1)

Inside `apps/`:

- `core/`  
  Shared utilities, shared blocks, site settings, base mixins
- `home/`  
  HomePage and homepage flexible sections
- `services/`  
  Services index + individual service pages/pricing display
- `people/`  
  Meet your technician page/profile content
- `articles/`  
  Blog index + blog post pages
- `events/`  
  News/events index + event/news pages
- `faq/`  
  FAQ page and FAQ blocks/snippets
- `contact/`  
  Contact page + optional contact form logic
- `booking/`  
  Booking page + embed/provider config

## 4) App Ownership Rules

- Each app owns its own `models.py`, `templates`, and tests.
- Shared reusable blocks belong in `apps/core`.
- Cross-app references are allowed only through clear page relationships.
- Do not put all page models in one giant file.

## 5) Template Structure

- Shared layout in `templates/base.html`
- App-specific templates in:
  - `apps/home/templates/home/`
  - `apps/services/templates/services/`
  - `apps/articles/templates/articles/`
  - etc.

## 6) URL Strategy

- Keep one main `config/urls.py`
- Mount Wagtail page routing for CMS pages
- Keep API endpoints (if added later) namespaced separately, e.g. `/api/...`
- Reserve `/admin` for owner editing

## 7) Environment Strategy

- Local env uses `.env`
- Keep secrets out of git
- Use `.env.example` with placeholders only

## 8) Testing Strategy (v1)

- App-level tests near each app or in root `tests/`
- Minimum for v1:
  - page creation tests
  - publish/render tests
  - booking page render test
  - permission/access tests for admin roles

## 9) v2 Extension Slots (planned now, built later)

- `apps/assistant/` for owner AI assistant
- `apps/payments/` if paywall added
- `apps/scheduling/` if custom Python booking backend replaces embed

## 10) Naming Conventions

- App names: lowercase, singular/plural as above
- Model names: PascalCase (`ServicePage`, `NewsEventPage`)
- Template names: snake_case
- Slugs: lowercase-hyphen format

## 11) Done Criteria

- You can explain what each app owns in one sentence.
- No app responsibility overlaps.
- Structure supports adding/removing features without rewriting everything.
