import json
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from io import BytesIO
from wagtail.images.models import Image as WagtailImage
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.documents.models import Document
from wagtail.models import Collection
from wagtail.rich_text import RichText

from core.blocks import AudioBlock, YouTubeBlock, youtube_id
from core.models import (ConcertIndexPage, ConcertPage, ContactPage, GalleryPage, HomePage, NewsletterIndexPage,
                         NewsletterPage, NewsletterSend, SiteSettings, Subscriber)
from core.newsletter import send_pending

TMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class SiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("lrs_setup", stdout=open("/dev/null", "w"))
        cls.docs = {}
        for name in ["Public", "Members", "Committee", "Audio"]:
            doc = Document(title=f"{name} doc", collection=Collection.objects.get(name=name))
            doc.file.save(f"{name.lower()}.{'mp3' if name == 'Audio' else 'pdf'}", ContentFile(b"x"), save=True)
            cls.docs[name] = doc
        cls.users = {}
        for group in ["Singers", "Committee", "Editors"]:
            user = User.objects.create_user(group.lower(), password="pw-12345678")
            user.groups.add(Group.objects.get(name=group))
            cls.users[group] = user
        index = ConcertIndexPage.objects.get()
        today = timezone.localdate()
        for title, delta in [("Future", 30), ("Past", -30)]:
            index.add_child(instance=ConcertPage(title=title, date=today + timedelta(days=delta), venue="St X"))

    def download(self, name, user=None):
        self.client.logout()
        if user:
            self.client.force_login(user)
        return self.client.get(self.docs[name].url)

    def test_document_access_levels(self):
        expected = {  # who: (Public, Members, Committee)
            None: (200, 302, 302),
            "Singers": (200, 200, 302),
            "Editors": (200, 200, 302),
            "Committee": (200, 200, 200),
        }
        for who, codes in expected.items():
            user = self.users.get(who)
            got = tuple(self.download(n, user).status_code for n in ["Public", "Members", "Committee"])
            self.assertEqual(got, codes, who)

    def test_audio_is_public(self):
        self.assertEqual(self.download("Audio").status_code, 200)

    def test_members_page_lists_only_allowed_documents(self):
        self.assertEqual(self.client.get("/members/").status_code, 302)
        self.client.force_login(self.users["Singers"])
        html = self.client.get("/members/").content.decode()
        self.assertIn("Members doc", html)
        self.assertNotIn("Committee doc", html)
        self.client.force_login(self.users["Committee"])
        self.assertIn("Committee doc", self.client.get("/members/").content.decode())

    def test_upcoming_and_past_concerts(self):
        upcoming = self.client.get("/concerts/").content.decode()
        past = self.client.get("/concerts/past/").content.decode()
        self.assertIn("Future", upcoming)
        self.assertNotIn(">Past<", upcoming)
        self.assertIn("Past", past)
        self.assertNotIn("Future", past)
        self.assertEqual(self.client.get(ConcertPage.objects.get(title="Future").url).status_code, 200)

    def test_youtube_links(self):
        for url in ["https://www.youtube.com/watch?v=abcdefghijk", "https://youtu.be/abcdefghijk?t=3",
                    "https://www.youtube.com/shorts/abcdefghijk", "https://m.youtube.com/watch?app=x&v=abcdefghijk"]:
            self.assertEqual(youtube_id(url), "abcdefghijk", url)
        with self.assertRaises(StructBlockValidationError):
            YouTubeBlock().clean({"url": "https://vimeo.com/123", "caption": ""})

    def test_audio_block_rejects_non_audio(self):
        block = AudioBlock()
        block.clean({"file": self.docs["Audio"], "title": "ok", "note": ""})
        with self.assertRaises(StructBlockValidationError):
            block.clean({"file": self.docs["Public"], "title": "pdf", "note": ""})

    def test_import_old_site(self):
        media = Path(tempfile.mkdtemp())
        (media / "documents").mkdir()
        (media / "documents" / "minutes.pdf").write_bytes(b"%PDF")
        (media / "img" / "portfolio").mkdir(parents=True)
        Image.new("RGB", (40, 30), "white").save(media / "img" / "portfolio" / "choir.png")
        export = [
            {"model": "auth.group", "pk": 1, "fields": {"name": "Admins"}},
            {"model": "auth.user", "pk": 1, "fields": {
                "username": "olduser", "email": "", "first_name": "", "last_name": "", "password": "x",
                "is_superuser": False, "is_staff": False, "is_active": True,
                "date_joined": "2024-01-01T00:00:00Z", "groups": [1]}},
            {"model": "frontend.concert", "pk": 1, "fields": {
                "title": "Old concert", "short_description": "", "concert_date": "2024-05-01",
                "start_time": "7.30pm", "description": "<p>Hi<img src='x'></p>", "image": "",
                "location": "Hall", "cost": "", "booking_link": None, "instructions": ""}},
            {"model": "documents.category", "pk": 1, "fields": {"name": "Committee"}},
            {"model": "documents.document", "pk": 1, "fields": {
                "title": "Minutes", "date": "2024-02-02", "category": 1, "file": "documents/minutes.pdf"}},
            {"model": "frontend.portfolio", "pk": 4, "fields": {
                "image": "img/portfolio/choir.png", "category": "committee", "name": "Ann", "position": "Chair"}},
            {"model": "frontend.portfolio", "pk": 5, "fields": {
                "image": "img/portfolio/choir.png", "category": "choir", "name": "Choir", "position": "2"}},
        ]
        path = media / "export.json"
        path.write_text(json.dumps(export))
        call_command("lrs_setup", export=str(path), media=str(media), stdout=open("/dev/null", "w"))
        concert = ConcertPage.objects.get(title="Old concert")
        self.assertEqual(concert.start_time.hour, 19)
        self.assertTrue(User.objects.get(username="olduser").groups.filter(name="Committee").exists())
        minutes = Document.objects.get(title="Minutes")
        self.assertEqual(minutes.collection.name, "Committee")
        # Choir photos come first; a numeric position is an order, not part of the caption.
        self.assertEqual([p.caption for p in GalleryPage.objects.get().photos.all()], ["Choir", "Ann, Chair"])
        # Old addresses for each concert and document lead to the new ones.
        self.assertRedirects(self.client.get("/concert-details/1/"), concert.url, status_code=301,
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/document_register/download/1/"), minutes.url, status_code=301,
                             fetch_redirect_response=False)

    def test_old_site_addresses(self):
        for old, new, code in [("/past-concerts/", "/concerts/past/", 301), ("/our_music/", "/our-music/", 301),
                               ("/document_register/", "/members/", 301), ("/portfolio/", "/gallery/", 301),
                               ("/faq", "/faq/", 301), ("/calendar/", "/", 302)]:
            self.assertRedirects(self.client.get(old), new, status_code=code, fetch_redirect_response=False)
        self.assertEqual(self.client.get("/gallery/").status_code, 200)
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /admin/", robots)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", robots)
        self.assertContains(self.client.get("/googleda7e415623738d69.html"), "google-site-verification")

    def test_contact_form_spam_protection(self):
        contact = ContactPage.objects.get()
        contact.to_address = "choir@example.org"
        contact.save()
        page = self.client.get(contact.url)
        started = page.context["started"]
        message = {"your_name": "Ann", "email": "ann@example.org", "message": "Hello"}

        def send(seconds_ago=60, **extra):
            data = {**message, "started": started, **extra}
            with patch("core.models.time.time", return_value=time.time() + seconds_ago):
                return self.client.post(contact.url, data)

        # Bots: trap box filled, sent too fast, missing or forged time stamp. Thank-you page, nothing kept.
        for response in [send(website="http://spam.example"), send(seconds_ago=1),
                         self.client.post(contact.url, message),
                         self.client.post(contact.url, {**message, "started": "forged"})]:
            self.assertContains(response, "Thank you")
        self.assertEqual(contact.get_submissions().count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        # A person who left the page open for days is asked to send again; what they typed stays.
        response = send(seconds_ago=3 * 24 * 60 * 60)
        self.assertContains(response, "Please press Send again")
        self.assertContains(response, "Hello")
        # A real message is stored and emailed, without the spam-check fields.
        self.assertContains(send(), "Thank you")
        self.assertEqual(contact.get_submissions().get().get_data()["message"], "Hello")
        self.assertNotIn("started", mail.outbox[0].body)
        self.assertNotIn("website", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].reply_to, ["ann@example.org"])  # Reply answers the visitor

    def test_password_reset_by_email(self):
        singer = self.users["Singers"]
        singer.email = "singer@example.org"
        singer.save()
        self.assertContains(self.client.get("/login/"), "/password-reset/")
        # An unknown address gets the same reply and no email, so accounts can't be discovered.
        response = self.client.post("/password-reset/", {"email": "nobody@example.org"})
        self.assertRedirects(response, "/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 0)
        self.client.post("/password-reset/", {"email": "singer@example.org"})
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if "/password-reset/" in line)
        form_url = self.client.get(urlsplit(link.strip()).path).url  # Django swaps the token for a session
        response = self.client.post(form_url, {"new_password1": "a-new-choir-pw", "new_password2": "a-new-choir-pw"})
        self.assertRedirects(response, "/password-reset/done/")
        self.assertTrue(self.client.login(username="singers", password="a-new-choir-pw"))
        # The link works only once.
        self.client.logout()
        self.assertContains(self.client.get(form_url), "expired or has already been used")

    def test_uploaded_photos_lose_location_data(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # taken with the camera on its side
        exif[0x010F] = "Camera maker"
        exif.get_ifd(0x8825)[1] = "N"  # GPS
        for fmt in ["JPEG", "PNG", "WEBP"]:
            raw = BytesIO()
            Image.new("RGB", (60, 40), "red").save(raw, fmt, exif=exif.tobytes())
            image = WagtailImage(title=fmt, file=ImageFile(BytesIO(raw.getvalue()), name=f"photo.{fmt.lower()}"))
            image.save()
            with image.open_file() as f:
                stored = Image.open(f)
                self.assertEqual(dict(stored.getexif()), {}, fmt)
            self.assertEqual((image.width, image.height), (40, 60), fmt)  # turned upright
            self.assertEqual(image.file_size, image.file.size)
            rendition = image.get_rendition("width-30")
            with rendition.file.open() as f:
                self.assertEqual(dict(Image.open(f).getexif()), {}, fmt)

    def test_large_photos_are_shrunk_and_pictures_made_in_advance(self):
        from core.models import MAX_ORIGINAL, shrink_original
        raw = BytesIO()
        Image.new("RGB", (4000, 2000), "blue").save(raw, "JPEG")
        upload = WagtailImage(title="big", file=ImageFile(BytesIO(raw.getvalue()), name="big.jpg"))
        upload.save()
        self.assertEqual((upload.width, upload.height), (MAX_ORIGINAL, 1500))
        with upload.open_file() as f:
            self.assertEqual(Image.open(f).size, (MAX_ORIGINAL, 1500))
        # One stored before the limit existed: shrunk later, its focal point moved to match.
        old = WagtailImage(title="old", focal_point_x=2000, focal_point_y=1000, focal_point_width=400,
                           focal_point_height=200)
        old.file.save("old.jpg", ContentFile(raw.getvalue()), save=False)
        old.width, old.height = 4000, 2000
        WagtailImage.objects.bulk_create([old])  # skips the upload cleaning, like an old upload
        old = WagtailImage.objects.get(title="old")
        old_file = old.file.name
        old.get_rendition("width-100")
        self.assertTrue(shrink_original(old))
        old.refresh_from_db()
        self.assertEqual((old.width, old.focal_point_x, old.focal_point_width), (MAX_ORIGINAL, 1500, 300))
        self.assertFalse(old.renditions.exists())
        self.assertFalse(old.file.storage.exists(old_file))
        self.assertFalse(shrink_original(old))
        # warm_images visits the site and makes the pictures pages show, before any visitor does.
        concert = ConcertPage.objects.get(title="Past")
        concert.image = upload
        concert.save_revision().publish()
        upload.renditions.all().delete()
        call_command("warm_images", stdout=open("/dev/null", "w"))  # just published, so it runs
        made = upload.renditions.count()
        self.assertGreater(made, 4)
        response = self.client.get("/concerts/past/")
        self.assertEqual(upload.renditions.count(), made)  # nothing left for the visitor to make
        self.assertContains(response, "big")

    def test_image_beside_text_block(self):
        image = WagtailImage(title="choir", file=ImageFile(BytesIO(self.png()), name="choir.png"))
        image.save()
        home = HomePage.objects.get()
        home.body = [("image_text", {"image": image, "alt_text": "The choir", "image_side": "left",
                                     "text": RichText("<p>About us</p>")})]
        home.save_revision().publish()
        html = self.client.get("/").content.decode()
        self.assertIn('class="image-text"', html)
        self.assertIn('alt="The choir"', html)
        self.assertIn("About us", html)

    def test_newsletter_signup_and_unsubscribe(self):
        url = NewsletterIndexPage.objects.get().url
        self.assertEqual(url, "/newsletters/")  # the old site's address, so no redirect is needed
        started = self.client.get(url).context["started"]

        def sign_up(email, **extra):
            with patch("core.models.time.time", return_value=time.time() + 60):
                return self.client.post(url, {"name": "Ann", "email": email, "started": started, **extra})

        # Bots get the normal reply and nobody is emailed.
        self.assertContains(sign_up("bot@example.org", website="x"), "Please check your email")
        self.assertEqual(len(mail.outbox), 0)
        # A person gets a confirmation link; nobody is stored until it is used.
        self.assertContains(sign_up("Ann@Example.org"), "Please check your email")
        self.assertEqual(mail.outbox[0].to, ["ann@example.org"])
        self.assertFalse(Subscriber.objects.exists())
        link = next(line for line in mail.outbox[0].body.splitlines() if "/newsletter/confirm/" in line)
        confirm = urlsplit(link.strip()).path
        self.assertContains(self.client.get(confirm), "Confirm your subscription")  # opening only shows a button
        self.assertFalse(Subscriber.objects.exists())
        self.assertContains(self.client.post(confirm), "subscribed")
        ann = Subscriber.objects.get()
        self.assertEqual((ann.email, ann.name, ann.source), ("ann@example.org", "Ann", "form"))
        # Signing up again sends nothing more; a broken link is refused.
        sign_up("ann@example.org")
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.client.get("/newsletter/confirm/forged/"), "expired")
        # Unsubscribe: the button on the page, or a mail program's one-click post (no CSRF token).
        from core.newsletter import unsubscribe_url
        path = urlsplit(unsubscribe_url(ann)).path
        self.assertContains(self.client.get(path), "ann@example.org")
        self.assertContains(Client(enforce_csrf_checks=True).post(path, {"List-Unsubscribe": "One-Click"}),
                            "unsubscribed")
        self.assertFalse(Subscriber.objects.exists())
        self.assertContains(self.client.get(path), "Not on the list")
        # A token can't be reused for someone who later gets the same id.
        Subscriber.objects.create(pk=ann.pk, email="bob@example.org")
        self.assertContains(self.client.get(path), "Not on the list")

    @override_settings(NEWSLETTER_DAILY_LIMIT=3, WAGTAILADMIN_BASE_URL="https://choir.example")
    def test_sending_a_newsletter(self):
        settings = SiteSettings.for_site(HomePage.objects.get().get_site())
        settings.contact_email = "choir@example.org"
        settings.save()
        for email in ["a@example.org", "b@example.org", "c@example.org", "d@example.org"]:
            Subscriber.objects.create(email=email)
        picture = WagtailImage(title="flyer", file=ImageFile(BytesIO(self.png()), name="flyer.png"))
        picture.save()
        embed = f'<embed embedtype="image" format="left" id="{picture.id}" alt="Flyer"/>'
        issue = NewsletterIndexPage.objects.get().add_child(instance=NewsletterPage(
            title="Spring news", body=f'<p>See <a href="/concerts/">our concerts</a>.</p>{embed}{embed}'))
        send_url = f"/admin/newsletter/{issue.id}/send/"
        # Editors can write newsletters but not send them; sending needs publish rights.
        self.client.force_login(self.users["Editors"])
        self.assertRedirects(self.client.get(send_url), "/admin/", fetch_redirect_response=False)  # "no permission"
        self.client.post(send_url, {"action": "send", "confirm": "1"})
        self.assertFalse(NewsletterSend.objects.exists())
        boss = User.objects.create_superuser("boss", "boss@example.org", "pw-12345678")
        self.client.force_login(boss)
        self.assertContains(self.client.get(send_url), "Send to 4 subscribers")
        self.client.post(send_url, {"action": "test"})
        self.assertEqual(mail.outbox[0].to, ["boss@example.org"])
        self.client.post(send_url, {"action": "send"})  # without ticking the box
        self.assertFalse(NewsletterSend.objects.exists())
        self.client.post(send_url, {"action": "send", "confirm": "1"})
        self.client.post(send_url, {"action": "send", "confirm": "1"})  # pressed twice: still sent once
        self.assertEqual(NewsletterSend.objects.get().recipients, 4)
        # Batches, within the daily limit (3 here); the rest waits for the next day.
        mail.outbox.clear()
        self.assertEqual(send_pending(batch=2), 2)
        self.assertEqual(send_pending(batch=2), 1)
        self.assertEqual(send_pending(batch=2), 0)
        message = mail.outbox[0]
        self.assertEqual((message.subject, message.reply_to), ("Spring news", ["choir@example.org"]))
        html = message.alternatives[0].content
        self.assertIn('href="https://choir.example/concerts/"', html)  # links work from an email
        self.assertIn("our concerts (https://choir.example/concerts/)", message.body)
        unsubscribe = message.extra_headers["List-Unsubscribe"].strip("<>")
        self.assertTrue(unsubscribe.startswith("https://choir.example/newsletter/unsubscribe/"))
        self.assertIn(unsubscribe, html)
        self.assertEqual(message.extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertContains(self.client.get(send_url), "Waiting: 1")
        # Pictures travel inside the email, shown in place (no "download pictures" step in Outlook).
        sent = message.message()
        self.assertEqual(sent.get_content_type(), "multipart/alternative")
        related = sent.get_payload()[1]
        self.assertEqual(related.get_content_type(), "multipart/related")
        html_part, picture_part = related.get_payload()
        self.assertIn('src="cid:picture1@lrs"', html_part.get_content())
        self.assertNotIn("/media/images/", html_part.get_content())
        self.assertEqual(picture_part["Content-ID"], "<picture1@lrs>")
        self.assertEqual(picture_part.get_content_type(), "image/png")
        self.assertEqual(len(related.get_payload()), 2)  # the same picture twice is carried once
        # Unsubscribing removes their waiting email; the archive lists sent newsletters.
        Subscriber.objects.get(email="d@example.org").delete()
        self.assertContains(self.client.get(send_url), "Waiting: 0")
        self.assertContains(self.client.get("/newsletters/"), "Spring news")
        self.assertEqual(self.client.get(issue.url).status_code, 200)

    @staticmethod
    def png():
        raw = BytesIO()
        Image.new("RGB", (40, 30), "white").save(raw, "PNG")
        return raw.getvalue()
