#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# deploy-gcloud.sh — Deploy thermography site to Google Cloud Run
#
# First-time usage:
#   chmod +x deploy-gcloud.sh
#   ./deploy-gcloud.sh            ← prompts for secrets on first deploy
#
# Subsequent deployments (code changes):
#   ./deploy-gcloud.sh            ← detects existing service, skips prompts
#
# Prerequisites:
#   - gcloud CLI installed (https://cloud.google.com/sdk/docs/install)
#   - You've run: gcloud auth login
#   - You've set your project: gcloud config set project YOUR_PROJECT_ID
#   - Billing is linked to the project
# ──────────────────────────────────────────────────────────
set -euo pipefail

# ─── Configuration ───────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="thermography"
MIGRATION_JOB="${SERVICE_NAME}-migrate"
BUCKET_NAME="${PROJECT_ID}-media"
RUN_SA_NAME="${SERVICE_NAME}-runner"
RUN_SA_EMAIL="${RUN_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
AR_REPO="thermography-repo"   # Artifact Registry repository name
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO/$SERVICE_NAME"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Deploying: $SERVICE_NAME"
echo "  Project:   $PROJECT_ID"
echo "  Region:    $REGION"
echo "  Image:     $IMAGE"
echo "  Bucket:    $BUCKET_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ─── Detect first deploy vs. update ─────────────────────
FIRST_DEPLOY=false
if ! gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" --project="$PROJECT_ID" &>/dev/null; then
    FIRST_DEPLOY=true
    echo "🆕  First deployment detected — will prompt for secrets."
    echo ""

    # ─── Prompt for required secrets ─────────────────────
    if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
        echo "Generate a secret key with:"
        echo '  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
        echo ""
        read -r -p "Paste your DJANGO_SECRET_KEY: " DJANGO_SECRET_KEY
    fi

    if [ -z "${DATABASE_URL:-}" ]; then
        echo ""
        echo "Get this from https://console.neon.tech → your project → Connection Details"
        read -r -p "Paste your DATABASE_URL: " DATABASE_URL
    fi

    echo ""
    echo "✅  Secrets captured. Starting deployment..."
    echo ""
fi

# ─── 0. Build frontend CSS (Tailwind) ────────────────────
if command -v npm >/dev/null 2>&1; then
    echo "→ Building Tailwind CSS..."
    npm ci --no-audit --no-fund
    npm run build:css
else
    echo "⚠️  npm not found; skipping Tailwind build."
    echo "   Using committed static CSS at thermography_site/static/css/tailwind.css"
fi

# ─── 1. Enable required APIs ────────────────────────────
echo "→ Enabling Google Cloud APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    --project="$PROJECT_ID"

# ─── 1b. Ensure dedicated runtime service account exists ─
echo "→ Ensuring Cloud Run runtime service account exists..."
if ! gcloud iam service-accounts describe "$RUN_SA_EMAIL" \
    --project="$PROJECT_ID" &>/dev/null; then
    gcloud iam service-accounts create "$RUN_SA_NAME" \
        --display-name "Thermography Cloud Run Runtime" \
        --project="$PROJECT_ID"
fi

# ─── 2. Create Artifact Registry repo (if not exists) ───
echo "→ Creating Artifact Registry repository..."
gcloud artifacts repositories describe "$AR_REPO" \
    --location="$REGION" --project="$PROJECT_ID" 2>/dev/null || \
gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Thermography Docker images" \
    --project="$PROJECT_ID"

# ─── 3. Create GCS bucket for media (if not exists) ─────
echo "→ Creating GCS bucket for media uploads..."
if ! gsutil ls -b "gs://$BUCKET_NAME" 2>/dev/null; then
    gsutil mb -p "$PROJECT_ID" -l "$REGION" -b on "gs://$BUCKET_NAME"
    # Allow public read access for media files (images shown on website)
    gsutil iam ch allUsers:objectViewer "gs://$BUCKET_NAME"
    # Set CORS for the bucket (needed for some Wagtail features)
    cat > /tmp/cors.json << 'CORS'
[
  {
    "origin": ["*"],
    "method": ["GET"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
CORS
    gsutil cors set /tmp/cors.json "gs://$BUCKET_NAME"
    rm /tmp/cors.json
fi

# Ensure Cloud Run runtime identity can upload media files.
echo "→ Granting Cloud Run service account access to media bucket..."
gsutil iam ch "serviceAccount:${RUN_SA_EMAIL}:objectAdmin" "gs://$BUCKET_NAME"

# ─── 4. Build & push Docker image ───────────────────────
echo "→ Building Docker image with Cloud Build..."
gcloud builds submit \
    --tag "$IMAGE:latest" \
    --project="$PROJECT_ID" \
    --timeout=600

# ─── 5. Run DB migrations (Cloud Run Job) ───────────────
echo "→ Running database migrations..."
if gcloud run jobs describe "$MIGRATION_JOB" \
    --region "$REGION" --project="$PROJECT_ID" &>/dev/null; then
    # Keep existing env vars on the job, only refresh image + command.
    gcloud run jobs update "$MIGRATION_JOB" \
        --image "$IMAGE:latest" \
        --region "$REGION" \
        --service-account "$RUN_SA_EMAIL" \
        --command "python" \
        --args "manage.py,migrate,--noinput" \
        --project="$PROJECT_ID"
else
    if [ "$FIRST_DEPLOY" = true ]; then
        # First deploy: create job with the required env vars.
        gcloud run jobs create "$MIGRATION_JOB" \
            --image "$IMAGE:latest" \
            --region "$REGION" \
            --service-account "$RUN_SA_EMAIL" \
            --task-timeout 300 \
            --max-retries 1 \
            --command "python" \
            --args "manage.py,migrate,--noinput" \
            --set-env-vars "DJANGO_SETTINGS_MODULE=thermography_site.settings.production" \
            --set-env-vars "DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY" \
            --set-env-vars "DATABASE_URL=$DATABASE_URL" \
            --set-env-vars "GS_BUCKET_NAME=$BUCKET_NAME" \
            --project="$PROJECT_ID"
    else
        # Existing service but missing job: bootstrap job from service env vars.
        SERVICE_ENV_VARS=$(gcloud run services describe "$SERVICE_NAME" \
            --region "$REGION" --project="$PROJECT_ID" --format=json | \
            python3 -c '
import json, sys
data = json.load(sys.stdin)
env = {e["name"]: e.get("value", "") for e in data["spec"]["template"]["spec"]["containers"][0].get("env", [])}
keys = ["DJANGO_SETTINGS_MODULE", "DJANGO_SECRET_KEY", "DATABASE_URL", "GS_BUCKET_NAME"]
missing = [k for k in keys if not env.get(k)]
if missing:
    print("ERROR: Missing required env vars on service: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
print(",".join(f"{k}={env[k]}" for k in keys))
')

        gcloud run jobs create "$MIGRATION_JOB" \
            --image "$IMAGE:latest" \
            --region "$REGION" \
            --service-account "$RUN_SA_EMAIL" \
            --task-timeout 300 \
            --max-retries 1 \
            --command "python" \
            --args "manage.py,migrate,--noinput" \
            --set-env-vars "$SERVICE_ENV_VARS" \
            --project="$PROJECT_ID"
    fi
fi

gcloud run jobs execute "$MIGRATION_JOB" \
    --region "$REGION" \
    --wait \
    --project="$PROJECT_ID"

# ─── 6. Deploy to Cloud Run ─────────────────────────────
echo "→ Deploying to Cloud Run..."

if [ "$FIRST_DEPLOY" = true ]; then
    # First deploy: include all secrets so the container can start
    gcloud run deploy "$SERVICE_NAME" \
        --image "$IMAGE:latest" \
        --region "$REGION" \
        --platform managed \
        --allow-unauthenticated \
        --service-account "$RUN_SA_EMAIL" \
        --port 8000 \
        --memory 512Mi \
        --cpu 1 \
        --min-instances 0 \
        --max-instances 3 \
        --timeout 300 \
        --startup-cpu-boost \
        --set-env-vars "DJANGO_SETTINGS_MODULE=thermography_site.settings.production" \
        --set-env-vars "DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY" \
        --set-env-vars "DATABASE_URL=$DATABASE_URL" \
        --set-env-vars "GS_BUCKET_NAME=$BUCKET_NAME" \
        --project="$PROJECT_ID"
else
    # Subsequent deploys: just update the image, keep existing env vars
    gcloud run deploy "$SERVICE_NAME" \
        --image "$IMAGE:latest" \
        --region "$REGION" \
        --platform managed \
        --service-account "$RUN_SA_EMAIL" \
        --project="$PROJECT_ID"
fi

# ─── 7. Get the URL & set ALLOWED_HOSTS on first deploy ─
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" --project="$PROJECT_ID" \
    --format="value(status.url)")

SERVICE_HOST=$(echo "$SERVICE_URL" | sed 's|https://||')

if [ "$FIRST_DEPLOY" = true ]; then
    echo "→ Setting ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS..."
    gcloud run services update "$SERVICE_NAME" \
        --region "$REGION" \
        --update-env-vars "\
ALLOWED_HOSTS=$SERVICE_HOST,\
CSRF_TRUSTED_ORIGINS=$SERVICE_URL,\
WAGTAILADMIN_BASE_URL=$SERVICE_URL\
" \
        --project="$PROJECT_ID"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Deployed successfully!"
echo ""
echo "  URL: $SERVICE_URL"
echo "  Admin: $SERVICE_URL/admin/"
echo ""
if [ "$FIRST_DEPLOY" = true ]; then
echo "  ⚠️  NEXT STEP: Create your superuser"
echo "  Run this command:"
echo ""
echo "  gcloud run jobs create create-superuser \\"
echo "      --image \"$IMAGE:latest\" \\"
echo "      --region $REGION \\"
echo "      --task-timeout 120 \\"
echo "      --set-env-vars \"\\"
echo "DJANGO_SETTINGS_MODULE=thermography_site.settings.production,\\"
echo "DJANGO_SECRET_KEY=\$DJANGO_SECRET_KEY,\\"
echo "DATABASE_URL=\$DATABASE_URL,\\"
echo "GS_BUCKET_NAME=$BUCKET_NAME,\\"
echo "DJANGO_SUPERUSER_PASSWORD=<CHANGE-ME-use-a-strong-password>,\\"
echo "DJANGO_SUPERUSER_USERNAME=admin,\\"
echo "DJANGO_SUPERUSER_EMAIL=your@email.com\\"
echo "\" \\"
echo "      --command \"python\" \\"
echo "      --args \"manage.py,createsuperuser,--noinput\" \\"
echo "      --execute-now"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
