# Thermography — Google Cloud Deployment Guide

> **Total time**: ~45 minutes | **Cost**: $0/month on free tier  
> **Stack**: Cloud Run + Neon PostgreSQL + Google Cloud Storage + GoatCounter

---

## What You're Setting Up

```
┌─────────────────────────────────────────────────────────────┐
│                        INTERNET                             │
│                           │                                 │
│              ┌────────────▼────────────┐                    │
│              │   Google Cloud Run      │  ← Your Django app │
│              │   (free: 2M req/mo)     │                    │
│              └─────┬──────────┬────────┘                    │
│                    │          │                              │
│         ┌─────────▼──┐  ┌────▼──────────────┐              │
│         │  Neon DB    │  │  Google Cloud     │              │
│         │ PostgreSQL  │  │  Storage (GCS)    │              │
│         │ (free 0.5GB)│  │  (free 5GB)       │              │
│         └────────────┘  └───────────────────┘              │
│                                                             │
│         ┌────────────────────────────┐                      │
│         │  GoatCounter Analytics     │  ← Privacy-friendly  │
│         │  (free, no cookies)        │                      │
│         └────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 0: Install the Google Cloud CLI

If you don't have the `gcloud` CLI yet:

```bash
# macOS (Homebrew)
brew install --cask google-cloud-sdk

# Verify it works
gcloud --version
```

Then log in:

```bash
gcloud auth login
```

This opens your browser — log in with your Google account.

---

## Step 1: Create a Google Cloud Project

### Option A: Via the Console (easier for beginners)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top → **"New Project"**
3. Name it something like `thermography-site`
4. Click **Create**
5. Wait ~30 seconds, then select it from the dropdown

### Option B: Via the terminal

```bash
gcloud projects create thermography-site --name="Thermography Site"
```

Then set it as your active project:

```bash
gcloud config set project thermography-site
```

> **⚠️ Billing**: Google requires a billing account even for the free tier.  
> Go to [console.cloud.google.com/billing](https://console.cloud.google.com/billing)  
> → Link your project. **You will NOT be charged** if you stay within free tier limits.

---

## Step 2: Set Up Neon PostgreSQL (Free Database)

1. Go to [neon.tech](https://neon.tech) and sign up (GitHub login works)
2. Click **"Create Project"**
   - **Name**: `thermography`
   - **Region**: Pick the closest to `us-central1` (e.g., **US East (Ohio)**)
   - **PostgreSQL version**: latest (16+)
3. Click **Create Project**
4. You'll see a **Connection Details** page. Copy the connection string that looks like:

```
postgresql://neondb_owner:abc123xyz@ep-cool-name-12345.us-east-2.aws.neon.tech/neondb?sslmode=require
```

> **📋 Save this string** — you'll need it in Step 6. This is your `DATABASE_URL`.

### Why Neon?

| Feature | Free Tier |
|---------|-----------|
| Storage | 0.5 GB (plenty for a business site) |
| Compute | Always-on, auto-suspend after 5 min idle |
| Branches | Great for testing changes |
| SSL | Built-in, required |

---

## Step 3: Set Up Google Cloud Storage (Media Uploads)

This is where Wagtail stores images and documents that the site owner uploads.

### Generate a secret key first (you'll need it soon)

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**📋 Copy and save the output** — this is your `DJANGO_SECRET_KEY`.

### Create the storage bucket

Run ``deploy-gcloud.sh`` and it will create the bucket automatically, OR create it manually:

```bash
# Replace "thermography-site" with your actual project ID
PROJECT_ID=$(gcloud config get-value project)

# Create the bucket
gsutil mb -p "$PROJECT_ID" -l us-central1 -b on "gs://${PROJECT_ID}-media"

# Allow public read access (so website visitors can see images)
gsutil iam ch allUsers:objectViewer "gs://${PROJECT_ID}-media"
```

> **Cost**: First 5 GB free. A typical business site uses <1 GB.  
> **Security**: Only the site owner can *upload* via Wagtail admin. The public can only *view*.

---

## Step 4: Set Up GoatCounter Analytics (Free)

1. Go to [goatcounter.com](https://www.goatcounter.com)
2. Click **"Sign up for free"**
3. Pick a **site code** (e.g., `mythermography`)
   - Your dashboard will be at `mythermography.goatcounter.com`
4. Enter the domain you'll use for the site
5. Click **Create**

That's it! **📋 Save your site code** (e.g., `mythermography`).

### What GoatCounter gives you

- Page views, referrers, browser/OS stats
- No cookies (GDPR-friendly — no cookie banner needed!)
- Free for personal/small business use
- Dashboard at `yourcode.goatcounter.com`

---

## Step 5: Deploy to Cloud Run

### 5a. Enable APIs and configure Docker auth

```bash
# Enable the required Google Cloud APIs
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    cloudbuild.googleapis.com

# Create a Docker repository in Artifact Registry
gcloud artifacts repositories create thermography-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Thermography Docker images"

# Configure Docker to push to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### 5b. Build and push your Docker image

```bash
cd /path/to/thermography

# Build using Cloud Build (no local Docker needed!)
gcloud builds submit \
    --tag us-central1-docker.pkg.dev/$(gcloud config get-value project)/thermography-repo/thermography:latest \
    --timeout=600
```

> **☕ This takes 3-5 minutes** the first time. Cloud Build builds your Docker image on Google's servers and pushes it to Artifact Registry.

### 5c. Deploy to Cloud Run

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud run deploy thermography \
    --image us-central1-docker.pkg.dev/$PROJECT_ID/thermography-repo/thermography:latest \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated \
    --port 8000 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --timeout 300 \
    --set-env-vars "DJANGO_SETTINGS_MODULE=thermography_site.settings.production" \
    --set-env-vars "GS_BUCKET_NAME=${PROJECT_ID}-media"
```

When it finishes, you'll see:

```
Service URL: https://thermography-xxxxx-uc.a.run.app
```

**📋 Copy this URL** — you'll need it in the next step.

---

## Step 6: Set the Environment Variables (Secrets)

Now add all the secrets. Replace the placeholder values below with your actual values:

```bash
SERVICE_URL="https://thermography-xxxxx-uc.a.run.app"   # ← from Step 5
PROJECT_ID=$(gcloud config get-value project)

gcloud run services update thermography \
    --region us-central1 \
    --set-env-vars "\
DJANGO_SETTINGS_MODULE=thermography_site.settings.production,\
DJANGO_SECRET_KEY=YOUR_SECRET_KEY_FROM_STEP_3,\
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require,\
ALLOWED_HOSTS=$(echo $SERVICE_URL | sed 's|https://||'),\
CSRF_TRUSTED_ORIGINS=${SERVICE_URL},\
WAGTAILADMIN_BASE_URL=${SERVICE_URL},\
GS_BUCKET_NAME=${PROJECT_ID}-media,\
GOATCOUNTER_SITE_CODE=your-goatcounter-code\
"
```

> **⚠️ Important**: 
> - Replace `YOUR_SECRET_KEY_FROM_STEP_3` with the key you generated
> - Replace the `DATABASE_URL` with your Neon connection string from Step 2
> - Replace `your-goatcounter-code` with your code from Step 4
> - Make sure there are **no spaces** around the commas

The service will automatically redeploy with the new variables (~30 seconds).

---

## Step 7: Create Your Admin Superuser

You need a one-time command to create the Wagtail admin account. Cloud Run lets you run commands inside the container:

```bash
# Open a direct connection to the running container
gcloud run services proxy thermography --region us-central1 &

# Or use the exec command (requires Cloud Run Admin API)
gcloud run jobs create thermography-setup \
    --image us-central1-docker.pkg.dev/$(gcloud config get-value project)/thermography-repo/thermography:latest \
    --region us-central1 \
    --set-env-vars "DJANGO_SETTINGS_MODULE=thermography_site.settings.production" \
    --command "python" \
    --args "manage.py,createsuperuser,--noinput,--username,admin,--email,admin@example.com" \
    --set-env-vars "DJANGO_SUPERUSER_PASSWORD=TempPassword123!" \
    --execute-now
```

**Better alternative** — use the Django management shell:

```bash
# Option 1: Run a one-off Cloud Run Job for the superuser
PROJECT_ID=$(gcloud config get-value project)
IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/thermography-repo/thermography:latest"

gcloud run jobs create create-superuser \
    --image "$IMAGE" \
    --region us-central1 \
    --task-timeout 120 \
    --set-env-vars "\
DJANGO_SETTINGS_MODULE=thermography_site.settings.production,\
DJANGO_SECRET_KEY=YOUR_SECRET_KEY,\
DATABASE_URL=YOUR_DATABASE_URL,\
GS_BUCKET_NAME=${PROJECT_ID}-media,\
DJANGO_SUPERUSER_PASSWORD=ChooseAStrongPassword123!,\
DJANGO_SUPERUSER_USERNAME=admin,\
DJANGO_SUPERUSER_EMAIL=your@email.com\
" \
    --command "python" \
    --args "manage.py,createsuperuser,--noinput" \
    --execute-now

# Check if it worked
gcloud run jobs executions list --job create-superuser --region us-central1

# Clean up the job after
gcloud run jobs delete create-superuser --region us-central1 --quiet
```

> **🔒 After logging in**, immediately change your password at  
> `https://your-site/admin/password/change/`

---

## Step 8: Verify Everything Works

### ✅ Checklist

| Test | How |
|------|-----|
| Site loads | Visit your Cloud Run URL |
| Admin works | Go to `/admin/` and log in |
| Image upload | Admin → Images → Add an image |
| Document upload | Admin → Documents → Add a document |
| Analytics | Check `yourcode.goatcounter.com` after visiting a few pages |
| HTTPS | URL should start with `https://` |
| Security headers | Visit [securityheaders.com](https://securityheaders.com) and enter your URL |

---

## Step 9: Custom Domain (Optional)

### Option A: Via Google Cloud Console (easiest)

1. Go to [console.cloud.google.com/run](https://console.cloud.google.com/run)
2. Click your **thermography** service
3. Click **"Manage Custom Domains"** at the top
4. Click **"Add Mapping"**
5. Enter your domain (e.g., `www.example.com`)
6. Google will give you a DNS record to add at your domain registrar
7. Wait for DNS propagation (can take up to 48 hours, usually <1 hour)

### Option B: Via terminal

```bash
gcloud beta run domain-mappings create \
    --service thermography \
    --domain www.yourdomain.com \
    --region us-central1
```

**After adding the custom domain**, update your env vars:

```bash
gcloud run services update thermography \
    --region us-central1 \
    --update-env-vars "\
ALLOWED_HOSTS=www.yourdomain.com,\
CSRF_TRUSTED_ORIGINS=https://www.yourdomain.com,\
WAGTAILADMIN_BASE_URL=https://www.yourdomain.com\
"
```

---

## Ongoing: How to Deploy Updates

After making code changes locally:

```bash
cd /path/to/thermography

# 1. Rebuild and push (3-5 min)
gcloud builds submit \
    --tag us-central1-docker.pkg.dev/$(gcloud config get-value project)/thermography-repo/thermography:latest \
    --timeout=600

# 2. Redeploy (30 sec)
gcloud run deploy thermography \
    --image us-central1-docker.pkg.dev/$(gcloud config get-value project)/thermography-repo/thermography:latest \
    --region us-central1

# Or use the script:
# chmod +x deploy-gcloud.sh && ./deploy-gcloud.sh
```

---

## Uploading Images & Documents (For the Site Owner)

The site owner manages all content through the **Wagtail admin panel**:

1. Go to `https://your-site.com/admin/`
2. Log in with the superuser credentials

### Images
- **Sidebar → Images → Add an image**
- Drag-and-drop or click to upload
- Images are automatically stored in Google Cloud Storage
- Wagtail auto-generates thumbnails and responsive sizes

### Documents (PDFs, etc.)
- **Sidebar → Documents → Add a document**
- Upload PDFs, Word docs, Excel files, etc.
- Allowed formats: CSV, DOCX, PDF, PPTX, RTF, TXT, XLSX, ZIP

### Adding images to pages
- Edit any page → click the image icon in the editor
- Choose an existing image or upload a new one

> **Storage limit**: GCS free tier is 5 GB. A typical business site with hundreds of images uses ~500 MB.

---

## Cost Summary

| Service | Free Tier Limit | Typical Usage | Monthly Cost |
|---------|----------------|---------------|-------------|
| Cloud Run | 2M requests, 180k vCPU-sec | ~10k visits | **$0** |
| Neon PostgreSQL | 0.5 GB storage | ~50 MB | **$0** |
| Google Cloud Storage | 5 GB | ~500 MB | **$0** |
| GoatCounter | Unlimited | All pageviews | **$0** |
| Cloud Build | 120 min/day | ~5 min/deploy | **$0** |
| **Total** | | | **$0/month** |

> When you outgrow free tier: Cloud Run scales to $0.00002400/vCPU-second. A site doing 100k visits/month would cost ~$2-5/month.

---

## Troubleshooting

### "Service Unavailable" or blank page
```bash
# Check the logs
gcloud run services logs read thermography --region us-central1 --limit 50
```

### "CSRF verification failed"
Make sure `CSRF_TRUSTED_ORIGINS` includes `https://` and your exact domain:
```bash
gcloud run services update thermography --region us-central1 \
    --update-env-vars "CSRF_TRUSTED_ORIGINS=https://your-exact-url.run.app"
```

### "DisallowedHost"
Make sure `ALLOWED_HOSTS` has your domain **without** `https://`:
```bash
gcloud run services update thermography --region us-central1 \
    --update-env-vars "ALLOWED_HOSTS=your-exact-url.run.app"
```

### Database connection errors
Check your Neon connection string:
- Must include `?sslmode=require` at the end
- Must use `postgresql://` (not `postgres://`)
- Check that Neon project is not suspended (visit the Neon dashboard)

### Images not showing
```bash
# Check bucket exists and is public
gsutil ls -b gs://YOUR-PROJECT-ID-media
gsutil iam get gs://YOUR-PROJECT-ID-media | grep objectViewer
```

### Cold start delay
Cloud Run scales to zero after ~15 min. First request after idle takes ~3-5 seconds. This is normal for free tier. To avoid it:
```bash
# Set minimum 1 instance (costs ~$5/month)
gcloud run services update thermography --region us-central1 --min-instances 1
```

---

## Security Summary

| Protection | How |
|-----------|-----|
| HTTPS | Automatic on Cloud Run (free SSL certificate) |
| HSTS | Enabled (1 year, preload) |
| Database SSL | Neon requires SSL by default |
| CSRF protection | Django's built-in + `CSRF_TRUSTED_ORIGINS` |
| Secrets | Stored as Cloud Run env vars (not in code) |
| File uploads | Only authenticated admins via Wagtail |
| Content-Type sniffing | Blocked via `X-Content-Type-Options: nosniff` |
| Clickjacking | Blocked via `X-Frame-Options` middleware |
| Cookie security | `Secure` + `HttpOnly` flags set |
| Analytics | GoatCounter: no cookies, no personal data |
