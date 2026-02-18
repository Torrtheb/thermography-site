# Use an official Python runtime based on Debian 12 "bookworm" as a parent image.
FROM python:3.13-slim-bookworm

# Add user that will be used in the container.
RUN useradd wagtail

# Port used by this container to serve HTTP.
EXPOSE 8000

# Set environment variables.
ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_SETTINGS_MODULE=thermography_site.settings.production

# Install system packages required by Wagtail and Django.
RUN apt-get update --yes --quiet && apt-get install --yes --quiet --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libwebp-dev \
 && rm -rf /var/lib/apt/lists/*

# Install the project requirements.
COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

# Use /app folder as a directory where the source code is stored.
WORKDIR /app

# Set this directory to be owned by the "wagtail" user.
RUN chown wagtail:wagtail /app

# Copy the source code of the project into the container.
COPY --chown=wagtail:wagtail . .

# Use user "wagtail" to run the build commands below and the server itself.
USER wagtail

# Collect static files (needs a dummy secret key for the build step).
RUN DJANGO_SECRET_KEY=build-placeholder python manage.py collectstatic --noinput --clear

# Runtime command: start gunicorn only.
# Migrations are run by deploy-gcloud.sh as a one-off Cloud Run Job before deploy.
# Cloud Run sets PORT=8000; gunicorn must bind to 0.0.0.0 (not 127.0.0.1).
CMD set -xe; gunicorn thermography_site.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
