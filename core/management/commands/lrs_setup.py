"""Set up groups, document collections, access rules and the page tree; optionally import the old site.

    python manage.py lrs_setup
    python manage.py lrs_setup --import lrs_export.json --media /path/to/old/media

Create the export on the old server with:
    python manage.py dumpdata auth.group auth.user frontend.concert frontend.composer frontend.faq \
        frontend.links frontend.homepagecontent documents --indent 1 > lrs_export.json
Run it only once against a fresh database; setup itself is safe to repeat.
"""
import json
from html import escape
import re
from datetime import date, time
from pathlib import Path

from django.contrib.auth.models import Group, Permission, User
from django.core.files import File
from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from wagtail.admin.rich_text.converters.contentstate import ContentstateConverter
from wagtail.documents import get_document_model
from wagtail.images import get_image_model
from wagtail.models import Collection, CollectionViewRestriction, GroupCollectionPermission, Page, Site
from wagtail.rich_text import RichText

from core.blocks import TEXT_FEATURES
from core.models import (Composer, ConcertIndexPage, ConcertPage, ComposersPage, ContactFormField, ContactPage,
                         DocumentsPage, HomePage, StandardPage)

DOC_PERMS = ["add_document", "change_document", "delete_document", "choose_document"]


def clean_html(html):
    """Reduce old CKEditor HTML to what the new editor supports (drops inline styles, images, scripts)."""
    if not html:
        return ""
    html = re.sub(r"<(img|br|hr|input|meta|link)\b[^>]*>", lambda m: "<br/>" if m.group(1) == "br" else "", html, flags=re.I)
    converter = ContentstateConverter(TEXT_FEATURES)
    try:
        return converter.to_database_format(converter.from_database_format(html))
    except AssertionError:  # badly nested HTML: keep the words, lose the formatting
        text = re.sub(r"<[^>]+>", "\n", html)
        return "".join(f"<p>{escape(line.strip())}</p>" for line in text.splitlines() if line.strip())


def parse_time(raw):
    match = re.search(r"(\d{1,2})(?:[.:](\d{2}))?\s*(am|pm)?", (raw or "").lower())
    if not match:
        return None
    hour, minute, suffix = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if suffix == "pm" and hour < 12 or (not suffix and 1 <= hour <= 9):
        hour += 12  # concerts are evenings unless stated otherwise
    return time(hour, minute) if hour < 24 and minute < 60 else None


class Command(BaseCommand):
    help = "Set up the LRS site structure and optionally import data exported from the old site."

    def add_arguments(self, parser):
        parser.add_argument("--import", dest="export", help="dumpdata JSON file from the old site")
        parser.add_argument("--media", help="the old site's media folder")

    @transaction.atomic
    def handle(self, *args, export=None, media=None, **options):
        self.groups = self.setup_groups()
        self.collections = self.setup_collections()
        self.home = self.setup_pages()
        if export:
            if not media:
                raise CommandError("--media is required with --import")
            self.import_old_site(json.loads(Path(export).read_text()), Path(media))
        self.stdout.write(self.style.SUCCESS("LRS setup complete."))

    # --- structure ---------------------------------------------------------
    def setup_groups(self):
        groups = {name: Group.objects.get_or_create(name=name)[0]
                  for name in ["Editors", "Moderators", "Committee", "Singers"]}
        access_admin = Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
        groups["Committee"].permissions.add(access_admin)
        return groups

    def setup_collections(self):
        root = Collection.get_first_root_node()
        collections = {}
        for name in ["Public", "Members", "Committee", "Audio"]:
            existing = root.get_children().filter(name=name).first()
            collections[name] = existing or root.add_child(name=name)

        g = self.groups
        for name, allowed in [("Members", ["Singers", "Committee", "Editors", "Moderators"]),
                              ("Committee", ["Committee"])]:
            restriction, _ = CollectionViewRestriction.objects.get_or_create(
                collection=collections[name], defaults={"restriction_type": "groups"})
            restriction.restriction_type = "groups"
            restriction.save()
            restriction.groups.set([g[n] for n in allowed])

        # Editors manage public, member and audio files; only the Committee manages committee files.
        doc_perms = list(Permission.objects.filter(content_type__app_label="wagtaildocs", codename__in=DOC_PERMS))
        GroupCollectionPermission.objects.filter(permission__in=doc_perms, collection=root).delete()
        for group_name, names in [("Editors", ["Public", "Members", "Audio"]),
                                  ("Moderators", ["Public", "Members", "Audio"]),
                                  ("Committee", ["Committee"])]:
            for name in names:
                for perm in doc_perms:
                    GroupCollectionPermission.objects.get_or_create(
                        group=g[group_name], collection=collections[name], permission=perm)
        return collections

    def setup_pages(self):
        home = HomePage.objects.first()
        if home:
            return home
        root = Page.get_first_root_node()
        for page in root.get_children().exact_type(Page):  # Wagtail's placeholder welcome page
            page.delete()
        home = root.add_child(instance=HomePage(
            title="Liverpool Renaissance Singers", slug="home",
            intro="Renaissance polyphony, sung in Liverpool."))
        Site.objects.update_or_create(is_default_site=True, defaults={
            "hostname": "localhost", "root_page": home, "site_name": "Liverpool Renaissance Singers"})

        home.add_child(instance=ConcertIndexPage(title="Concerts", slug="concerts",
                                                 intro="Our forthcoming performances."))
        home.add_child(instance=ComposersPage(title="Our music", slug="our-music",
                                              intro="Composers whose music we sing."))
        for title in ["About", "Join", "Donate", "FAQ", "Links"]:
            home.add_child(instance=StandardPage(title=title, slug=slugify(title)))
        home.add_child(instance=DocumentsPage(title="Members", slug="members", show_in_menus=False,
                                              intro="Documents for choir members."))
        home.add_child(instance=ContactPage(
            title="Contact", slug="contact", subject="Website enquiry",
            form_fields=[ContactFormField(label="Your name", field_type="singleline", required=True),
                         ContactFormField(label="Email", field_type="email", required=True),
                         ContactFormField(label="Message", field_type="multiline", required=True)]))
        for title in ["Concerts", "Our music", "About", "Join", "Donate", "FAQ", "Contact"]:
            Page.objects.filter(title=title).update(show_in_menus=True)
        return home

    # --- import ------------------------------------------------------------
    def import_old_site(self, records, media):
        rows = {}
        for r in records:
            rows.setdefault(r["model"], []).append({"pk": r["pk"], **r["fields"]})
        old_groups = {g["pk"]: g["name"] for g in rows.get("auth.group", [])}

        for u in rows.get("auth.user", []):
            if User.objects.filter(username=u["username"]).exists():
                continue
            user = User.objects.create(**{k: u[k] for k in [
                "username", "email", "first_name", "last_name", "password",
                "is_superuser", "is_staff", "is_active", "date_joined"]})
            for name in (old_groups.get(pk) for pk in u.get("groups", [])):
                if name == "Admins":
                    user.groups.add(self.groups["Editors"], self.groups["Committee"])
                elif name == "Singers":
                    user.groups.add(self.groups["Singers"])

        composers = {c["pk"]: Composer.objects.create(name=c["name"], dates=c.get("dates") or "",
                                                      region=c.get("region_of_origin") or "")
                     for c in rows.get("frontend.composer", [])}

        index = ConcertIndexPage.objects.get()
        for c in rows.get("frontend.concert", []):
            body = [("text", RichText(clean_html(c.get("description"))))] if c.get("description") else []
            when = parse_time(c.get("start_time"))
            if c.get("instructions"):
                body.append(("text", RichText("<h3>Getting there</h3>" + "".join(
                    f"<p>{escape(line)}</p>" for line in c["instructions"].splitlines() if line.strip()))))
            page = ConcertPage(
                title=c["title"], slug=slugify(f"{c['title']}-{c['concert_date']}")[:200],
                date=date.fromisoformat(c["concert_date"]), start_time=when,
                venue=c.get("location") or "To be confirmed", price=c.get("cost") or "",
                booking_url=c.get("booking_link") or "", intro=c.get("short_description") or "",
                image=self.import_image(media, c.get("image"), c["title"]), body=body)
            index.add_child(instance=page)
            page.save_revision().publish()

        faqs = sorted(rows.get("frontend.faq", []), key=lambda f: f.get("position") or 0)
        if faqs:
            self.fill_page("FAQ", [("faq", {"question": f["question"] or "",
                                            "answer": RichText(clean_html(f.get("answer")))}) for f in faqs])
        links = rows.get("frontend.links", [])
        if links:
            self.fill_page("Links", [("link_card", {"title": l["title"] or l["website"], "url": l["website"],
                                                    "description": l.get("description") or ""})
                                     for l in links if l.get("website")])
        home_text = rows.get("frontend.homepagecontent", [])
        if home_text:
            self.home.body = [("text", RichText(clean_html(home_text[0]["text"])))]
            self.home.save_revision().publish()

        categories = {c["pk"]: c["name"] for c in rows.get("documents.category", [])}
        Document = get_document_model()
        skipped = []
        for d in rows.get("documents.document", []):
            path = media / (d.get("file") or "")
            if not d.get("file") or not path.is_file():
                skipped.append(d.get("title") or d.get("external_url"))
                continue
            category = categories.get(d["category"], "")
            collection = self.collections["Committee" if category.lower() == "committee" else "Members"]
            with path.open("rb") as fh:
                doc = Document(title=d.get("title") or path.stem, collection=collection)
                doc.file.save(path.name, File(fh), save=True)
            if category:
                doc.tags.add(category)
            Document.objects.filter(pk=doc.pk).update(created_at=f"{d['date']}T12:00:00Z")

        self.stdout.write(f"Imported {len(composers)} composers, {len(rows.get('frontend.concert', []))} concerts, "
                          f"{len(faqs)} FAQs, {len(links)} links, "
                          f"{len(rows.get('documents.document', [])) - len(skipped)} documents.")
        if skipped:
            self.stdout.write(self.style.WARNING(
                "Not imported (external links or missing files): " + "; ".join(map(str, skipped))))

    def import_image(self, media, name, title):
        path = media / (name or "")
        if not name or not path.is_file():
            return None
        Image = get_image_model()
        with path.open("rb") as fh:
            image = Image(title=title, collection=Collection.get_first_root_node())
            image.file.save(path.name, ImageFile(fh), save=True)
        return image

    def fill_page(self, title, blocks):
        page = StandardPage.objects.get(title=title)
        page.body = blocks
        page.save_revision().publish()
