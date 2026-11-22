"""Make every page's resized pictures before a visitor asks for them.

Wagtail makes each resized copy of a picture the first time a page shows it, which can make the
first visit to a page with many pictures take many seconds. This command visits the public site
itself (whatever the theme shows, so it needs no list of sizes), and first shrinks any original
larger than models.MAX_ORIGINAL (uploads made before that limit existed).

    python manage.py warm_images          # only if something was edited in the admin recently (every minute, lrs-jobs.timer)
    python manage.py warm_images --all    # the whole site now (after a deploy or a database copy)
"""
import re
import time
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test import Client
from django.utils import timezone
from wagtail.images import get_image_model
from wagtail.models import ModelLogEntry, PageLogEntry

from core.models import MAX_ORIGINAL, shrink_original

RECENT = timedelta(minutes=3)  # longer than the timer's interval, so no edit is missed
SKIP = ("/admin/", "/documents/", "/media/", "/static/", "/login/", "/logout/", "/password-reset/",
        "/newsletter/", "/sitemap.xml", "/robots.txt")
MAX_PAGES = 2000


class Command(BaseCommand):
    help = "Make the site's resized pictures in advance (and shrink oversized originals)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="visit the whole site even if nothing changed")

    def handle(self, *args, all=False, **options):
        since = timezone.now() - RECENT
        Image = get_image_model()
        edited = (PageLogEntry.objects.filter(timestamp__gte=since).exists()
                  or ModelLogEntry.objects.filter(timestamp__gte=since).exists()  # images, snippets, settings
                  or Image.objects.filter(created_at__gte=since).exists())
        if not (all or edited):
            return
        started = time.time()
        shrunk = sum(shrink_original(image) for image in Image.objects.all()
                     if max(image.width, image.height) > MAX_ORIGINAL)
        pictures_before = Image.get_rendition_model().objects.count()
        pages = self.visit_site()
        made = Image.get_rendition_model().objects.count() - pictures_before
        self.stdout.write(f"Pictures: {pages} pages visited, {made} pictures made, {shrunk} originals shrunk, "
                          f"{time.time() - started:.1f}s.")

    def visit_site(self):
        """Follow the site's own links from the home page, as a visitor would (but without logging in)."""
        host = urlsplit(settings.WAGTAILADMIN_BASE_URL).hostname or "localhost"
        base = f"https://{host}"
        client = Client(HTTP_HOST=host)
        seen, todo = set(), ["/"]
        while todo and len(seen) < MAX_PAGES:
            path = todo.pop()
            if path in seen:
                continue
            seen.add(path)
            response = client.get(path, secure=True)
            if response.status_code != 200 or not response.get("Content-Type", "").startswith("text/html"):
                continue
            for href in re.findall(r'href="([^"#]+)', response.content.decode()):
                url = urlsplit(urljoin(base + path, href.replace("&amp;", "&")))
                if url.hostname == host and not url.path.startswith(SKIP):
                    todo.append(url.path + (f"?{url.query}" if url.query else ""))
        return len(seen)
