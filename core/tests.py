import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.documents.models import Document
from wagtail.models import Collection

from core.blocks import AudioBlock, YouTubeBlock, youtube_id
from core.models import ConcertIndexPage, ConcertPage

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
        ]
        path = media / "export.json"
        path.write_text(json.dumps(export))
        call_command("lrs_setup", export=str(path), media=str(media), stdout=open("/dev/null", "w"))
        concert = ConcertPage.objects.get(title="Old concert")
        self.assertEqual(concert.start_time.hour, 19)
        self.assertTrue(User.objects.get(username="olduser").groups.filter(name="Committee").exists())
        self.assertEqual(Document.objects.get(title="Minutes").collection.name, "Committee")
