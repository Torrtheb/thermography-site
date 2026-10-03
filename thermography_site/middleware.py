"""
Project-wide custom middleware.

``BlockScannersMiddleware`` short-circuits automated vulnerability/scanner
requests (e.g. ``/wp-login.php``, ``/xmlrpc.php``, ``/.env``) with a cheap 404
*before* they reach Wagtail's page-serving view and ``RedirectMiddleware``.

Why this matters for cost:
    This site runs on Neon's scale-to-zero Postgres. Wagtail resolves every
    unknown URL by querying the database, and ``RedirectMiddleware`` does a
    *second* DB lookup on every 404 to check for a configured redirect. Bots
    hammer the site with hundreds of requests for paths that never exist on a
    Django/Wagtail site, and each one wakes (or keeps awake) the database.

    None of the blocked patterns correspond to any real URL on this site, so
    returning 404 immediately is functionally identical to what Wagtail would
    return anyway — just without touching the database.

The middleware is intentionally conservative: it only matches path shapes that
are impossible on this site (PHP files, WordPress paths, dotfiles, well-known
admin/exploit probes). Legitimate Wagtail pages, static/media files, the admin,
the sitemap, robots.txt and the health check are never affected.
"""

import re

from django.http import HttpResponseNotFound

# Each pattern is matched (case-insensitively) against ``request.path``.
# Keep these strict: only shapes that can NEVER be a real page on this site.
_BLOCKED_PATTERNS = (
    # Any PHP / classic-CMS script extension (this site serves none).
    r"\.(?:php\d?|phtml|asp|aspx|jsp|cgi|cfm)(?:$|[/?])",
    # WordPress probes: /wp-login.php, /wp-admin/, /wp-content/, /wp-json, etc.
    r"(?:^|/)wp[-/]",
    r"(?:^|/)wordpress(?:$|/)",
    r"(?:^|/)xmlrpc(?:$|\.)",
    # Exposed dotfiles / VCS / secrets probes: /.env, /.git/, /.aws, etc.
    r"(?:^|/)\.(?:env|git|svn|hg|aws|ssh|htaccess|htpasswd|DS_Store)",
    # Common admin-panel / tooling / exploit probes.
    r"(?:^|/)(?:phpmyadmin|phpunit|pma|adminer|dbadmin|mysqladmin|"
    r"cgi-bin|vendor|solr|actuator|telescope|owa|autodiscover|"
    r"boaform|hudson|jenkins|_ignition|eval-stdin)(?:$|/|\.)",
    # NOTE: deliberately NOT blocking archive/backup extensions (.zip, .sql,
    # .bak, …) because Wagtail serves legitimate uploaded documents at
    # /documents/<id>/<filename> and those could use such extensions.
)

_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)


class BlockScannersMiddleware:
    """Return a DB-free 404 for obvious automated scanner paths."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _BLOCKED_RE.search(request.path):
            response = HttpResponseNotFound("Not Found")
            # Don't let this junk 404 be cached, and don't advertise anything.
            response["Cache-Control"] = "no-cache, no-store"
            return response
        return self.get_response(request)
