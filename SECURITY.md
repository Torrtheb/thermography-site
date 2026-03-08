# Security & Privacy — Thermography Site

This document describes how client data and secrets are protected. **Client names and emails are stored in the database (Neon Postgres)**; treating them as sensitive is a priority.

---

## 1. Client data (PII)

- **Where it lives**: The `clients` app stores client records (name, phone, email, notes) in the **Neon PostgreSQL** database.
- **Encryption at rest**: All PII fields use **Fernet symmetric encryption** via `clients.fields.EncryptedCharField` / `EncryptedTextField`. The DB stores ciphertext; only the app with `FIELD_ENCRYPTION_KEY` can decrypt.
- **Key management**:
  - Set `FIELD_ENCRYPTION_KEY` in production (see `.env.example`). Generate once with:
    ```bash
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```
  - **Back up this key securely** (e.g. password manager). If it is lost, encrypted client and contact-submission data cannot be recovered. See `BACKUP.md` for key storage and Neon backup steps.
  - Never commit the key to the repo or store it in code.
- **Access**: Client data is only available in the **Wagtail admin** (staff only). There are no public URLs that return client PII. The “Send Email” screen is protected by `require_admin_access`.

---

## 2. Secrets and environment

- **Never commit**: `.env` is in `.gitignore`. All secrets (e.g. `DJANGO_SECRET_KEY`, `DATABASE_URL`, `FIELD_ENCRYPTION_KEY`, `GCS_CREDENTIALS_BASE64`, `BREVO_API_KEY`) must come from **environment variables** in production.
- **Railway**: Set all secrets in the Railway project **Variables** (or linked env groups). Do not bake them into the image or code.
- **Neon**: Use the connection string from Neon’s dashboard with `?sslmode=require`. Restrict Neon DB access (e.g. IP allowlist or Neon’s own controls) if available.

---

## 3. HTTPS and security headers

- **HTTPS only**: The app expects TLS at the edge (e.g. Railway’s proxy). Production settings set `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and HSTS.
- **Headers**: `SECURE_CONTENT_TYPE_NOSNIFF`, `X-Frame-Options`, `Referrer-Policy`, and Content-Security-Policy (CSP) are configured in `thermography_site.settings.production`.

---

## 4. Logging and PII

- **Production logging**: Default level is WARNING. Avoid logging request bodies, session data, or client identifiers (names, emails) in custom code.
- **Contact form**: Only the submission primary key is logged on email failure (no names/emails in logs).
- **Send-email failures**: The admin “Send Email” view does not put client names in the HTTP response; failure details are logged by client id so staff can retry from the admin list.
- **Newsletter/Brevo**: Some INFO-level logs may include email addresses. If you need to avoid that in production, set the `newsletter` (and related) loggers to WARNING in production.

---

## 5. Contact form submissions

- Contact form submissions (name, email, phone, message) use the **same Fernet encryption** as the clients app (`FIELD_ENCRYPTION_KEY`). Stored in `contact.ContactSubmission`; viewable in **Wagtail admin → Contact submissions** (staff only).
- Rate limiting (per-IP hash) is in place to reduce abuse.

---

## 6. Database and deployment

- **Neon**: Use a dedicated DB user with minimal required privileges. Keep the connection string secret.
- **Railway**: The app runs with `DEBUG=False`. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are set from env (and Railway’s `RAILWAY_PUBLIC_DOMAIN` when present).
- **Admin URL**: Wagtail admin is at `/admin/`. Use a strong password and consider 2FA when Wagtail/Django support it.

---

## 7. Quick checklist before go-live

- [ ] `DJANGO_SECRET_KEY` set and not default/dev
- [ ] `FIELD_ENCRYPTION_KEY` set and backed up securely
- [ ] `DATABASE_URL` from Neon with `?sslmode=require`
- [ ] `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` include your production domain
- [ ] No `.env` or secrets in the repo or Docker image
- [ ] Strong admin password; only trusted users have staff access
