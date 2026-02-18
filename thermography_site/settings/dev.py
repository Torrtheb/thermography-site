"""
Development settings — the default when running locally via manage.py.
"""

from .base import *  # noqa: F401,F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: this key is for local development only.
SECRET_KEY = "django-insecure-jb0uck8i)g^^x^t3j4+*h$fdc+2jm83k=yma*v^+(yhp&v0fie"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
