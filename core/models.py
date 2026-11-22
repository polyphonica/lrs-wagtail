"""The stable content model. Themes only read from these; they never define content."""
import logging
import re
import time
from html import unescape
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.text import Truncator
from modelcluster.fields import ParentalKey
from PIL import Image as PILImage, ImageOps
from wagtail.admin.mail import send_mail
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel, TitleFieldPanel
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from wagtail.contrib.forms.panels import FormSubmissionsPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.documents import get_document_model
from wagtail.fields import RichTextField, StreamField
from wagtail.images.models import Image
from wagtail.models import Collection, Orderable, Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from .blocks import TEXT_FEATURES, ButtonBlock, ConcertBody, PageBody

logger = logging.getLogger(__name__)

# Document collections members can browse, in display order. "Audio" holds concert samples.
DOCUMENT_COLLECTIONS = ["Public", "Members", "Committee"]


def image_field(help_text=""):
    return models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+", help_text=help_text)


@register_snippet
class Composer(index.Indexed, models.Model):
    name = models.CharField(max_length=200)
    dates = models.CharField(max_length=40, blank=True, help_text="e.g. c.1540–1623")
    region = models.CharField(max_length=200, blank=True)

    panels = [FieldPanel("name"), FieldRowPanel([FieldPanel("dates"), FieldPanel("region")])]
    search_fields = [index.SearchField("name"), index.AutocompleteField("name")]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.dates})" if self.dates else self.name


@register_setting(icon="cog")
class SiteSettings(BaseSiteSetting):
    """What the footer shows on every page (Settings → Site settings in the admin)."""
    footer_text = models.CharField(max_length=300, blank=True, help_text="A sentence about the choir.")
    charity_number = models.CharField(max_length=40, blank=True)
    footer_links = StreamField([("link", ButtonBlock())], blank=True, help_text="The footer's 'Useful links'.")
    contact_email = models.EmailField(blank=True, help_text="Also where replies to newsletters go.")
    donate_url = models.URLField("Donate link", blank=True)
    donate_label = models.CharField(max_length=80, blank=True, help_text="e.g. Give As You Live")
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)

    panels = [
        MultiFieldPanel([FieldPanel("footer_text"), FieldPanel("charity_number")], heading="About the choir"),
        FieldPanel("footer_links"),
        MultiFieldPanel([FieldPanel("contact_email"),
                         FieldRowPanel([FieldPanel("donate_url"), FieldPanel("donate_label")])],
                        heading="Contact and support"),
        MultiFieldPanel([FieldPanel("facebook"), FieldPanel("instagram"), FieldPanel("youtube")],
                        heading="Social media"),
    ]


class BasePage(Page):
    """Fields every ordinary page has."""
    intro = models.TextField(blank=True, help_text="One or two sentences shown at the top and in search results.")
    image = image_field("Main image. Click 'Focal point' on the image to control how it is cropped.")

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("image")]

    class Meta:
        abstract = True


class HomePage(BasePage):
    quote = models.CharField(max_length=200, blank=True,
                             help_text="A short review quote shown under the intro, without quotation marks.")
    body = StreamField(PageBody(), blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro", heading="Strapline"), FieldPanel("quote"),
                                            FieldPanel("image"), FieldPanel("body")]
    max_count = 1
    subpage_types = ["core.ConcertIndexPage", "core.StandardPage", "core.ComposersPage",
                     "core.GalleryPage", "core.DocumentsPage", "core.ContactPage", "core.NewsletterIndexPage"]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["upcoming"] = ConcertPage.upcoming()[:3]
        return context


class StandardPage(BasePage):
    """About, Join, Donate, FAQ, Links and any other general page."""
    body = StreamField(PageBody(), blank=True)

    content_panels = BasePage.content_panels + [FieldPanel("body")]
    search_fields = Page.search_fields + [index.SearchField("intro"), index.SearchField("body")]
    subpage_types = ["core.StandardPage"]


class ConcertIndexPage(RoutablePageMixin, BasePage):
    subpage_types = ["core.ConcertPage"]
    max_count = 1

    @path("")
    def upcoming_concerts(self, request):
        return self.render(request, context_overrides={"concerts": ConcertPage.upcoming(), "past": False})

    @path("past/")
    def past_concerts(self, request):
        concerts = ConcertPage.objects.live().public().filter(date__lt=timezone.localdate()).order_by("-date")
        page = Paginator(concerts, 12).get_page(request.GET.get("page"))
        return self.render(request, context_overrides={"concerts": page, "past": True})


class ConcertPage(BasePage):
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=200)
    venue_address = models.CharField(max_length=300, blank=True, help_text="Used for the map link.")
    price = models.CharField(max_length=120, blank=True, help_text="e.g. £15, concessions £10, under-18s free")
    booking_url = models.URLField("Booking link", blank=True, help_text="Link to the ticket page, e.g. TicketSource.")
    body = StreamField(ConcertBody(), blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel([FieldRowPanel([FieldPanel("date"), FieldPanel("start_time")]),
                         FieldPanel("venue"), FieldPanel("venue_address")], heading="When and where"),
        MultiFieldPanel([FieldPanel("price"), FieldPanel("booking_url")], heading="Tickets"),
        FieldPanel("intro", heading="Summary"),
        FieldPanel("image"),
        FieldPanel("body", heading="Concert page content"),
    ]
    search_fields = Page.search_fields + [index.SearchField("intro"), index.SearchField("body"),
                                          index.FilterField("date")]
    parent_page_types = ["core.ConcertIndexPage"]
    subpage_types = []

    class Meta:
        ordering = ["date"]

    @classmethod
    def upcoming(cls):
        return cls.objects.live().public().filter(date__gte=timezone.localdate()).order_by("date", "start_time")

    @property
    def is_past(self):
        return self.date < timezone.localdate()


class ComposersPage(BasePage):
    max_count = 1
    subpage_types = []

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["composers"] = Composer.objects.all()
        return context


class GalleryPage(BasePage):
    """Photos of the choir, concerts and committee, shown in the order set in the admin."""
    content_panels = BasePage.content_panels + [InlinePanel("photos", heading="Photos", label="Photo")]
    max_count = 1
    subpage_types = []


class GalleryPhoto(Orderable):
    page = ParentalKey(GalleryPage, on_delete=models.CASCADE, related_name="photos")
    image = models.ForeignKey("wagtailimages.Image", on_delete=models.CASCADE, related_name="+")
    caption = models.CharField(max_length=250, blank=True, help_text="Also used as the description for screen readers.")

    panels = [FieldPanel("image"), FieldPanel("caption")]


class DocumentsPage(BasePage):
    """Members' area: lists only the documents the signed-in member is allowed to download."""
    max_count = 1
    subpage_types = []

    def serve(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return super().serve(request, *args, **kwargs)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        Document = get_document_model()
        groups = []
        for collection in Collection.objects.filter(name__in=DOCUMENT_COLLECTIONS):
            if all(r.accept_request(request) for r in collection.get_view_restrictions()):
                docs = Document.objects.filter(collection=collection).prefetch_related("tags").order_by("-created_at")
                groups.append((collection.name, docs))
        groups.sort(key=lambda g: DOCUMENT_COLLECTIONS.index(g[0]))
        context["document_groups"] = groups
        return context


class FormGuard:
    """Spam protection for public forms, no outside service. Two checks that people never notice:
    - a "website" box hidden from people (screen readers and keyboards skip it too); bots fill it in;
    - a signed time stamp in the form; a reply sent within seconds of the page loading is a bot.
    Both stay outside the real form, so they are never stored or emailed. Spam gets the normal
    thank-you reply (so bots learn nothing) but nothing is saved or sent."""
    TRAP_FIELD = "website"
    STARTED_FIELD = "started"
    MIN_SECONDS = 3
    MAX_SECONDS = 2 * 24 * 60 * 60

    def __init__(self, salt):
        self.salt = salt

    def context(self):
        """Template variables for includes/form_guard.html."""
        return {"trap_field": self.TRAP_FIELD, "started_field": self.STARTED_FIELD,
                "started": signing.dumps(time.time(), salt=self.salt)}

    def check(self, data):
        """Return "spam", "expired" (a person who left the page open too long) or "" (fine)."""
        if data.get(self.TRAP_FIELD):
            return "spam"
        try:
            started = signing.loads(data.get(self.STARTED_FIELD, ""), salt=self.salt, max_age=self.MAX_SECONDS)
        except signing.SignatureExpired:
            return "expired"
        except signing.BadSignature:
            return "spam"
        return "spam" if time.time() - started < self.MIN_SECONDS else ""


EXPIRED_FORM = "This page was open for a long time. Please press Send again."


class ContactFormField(AbstractFormField):
    page = ParentalKey("ContactPage", on_delete=models.CASCADE, related_name="form_fields")


class ContactPage(AbstractEmailForm):
    intro = RichTextField(blank=True, features=TEXT_FEATURES)
    thank_you_text = RichTextField(blank=True, features=TEXT_FEATURES)

    content_panels = AbstractEmailForm.content_panels + [
        FormSubmissionsPanel(),
        FieldPanel("intro"),
        InlinePanel("form_fields", label="Form fields"),
        FieldPanel("thank_you_text"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("from_address"), FieldPanel("to_address")]),
                         FieldPanel("subject")], heading="Email"),
    ]
    max_count = 1
    subpage_types = []
    guard = FormGuard("lrs.contact")  # the trap box and time stamp are outside the Wagtail form

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context.update(self.guard.context())
        return context

    def serve(self, request, *args, **kwargs):
        if request.method == "POST":
            verdict = self.guard.check(request.POST)
            if verdict == "spam":
                logger.info("Contact form: spam blocked")
                return self.render_landing_page(request, None, *args, **kwargs)
            if verdict == "expired":
                form = self.get_form(request.POST, request.FILES, page=self, user=request.user)
                form.is_valid()
                form.add_error(None, EXPIRED_FORM)
                context = self.get_context(request)
                context["form"] = form
                return TemplateResponse(request, self.get_template(request), context)
        return super().serve(request, *args, **kwargs)

    def send_mail(self, form):
        # Pressing Reply answers the visitor: the first email-type field they filled in
        # (found by type, so editors can rename or reorder the form fields).
        email_fields = [f.clean_name for f in self.get_form_fields() if f.field_type == "email"]
        reply_to = next((form.cleaned_data[n] for n in email_fields if form.cleaned_data.get(n)), None)
        addresses = [x.strip() for x in self.to_address.split(",") if x.strip()]
        send_mail(self.subject, self.render_email(form), addresses, self.from_address,
                  reply_to=[reply_to] if reply_to else None)


# --- Newsletter ------------------------------------------------------------------
# People sign up on the Newsletter page and are only stored once they click the link in a
# confirmation email. A newsletter is a page under it, written like any other page; sending
# (admin: page menu → "Send newsletter") queues one delivery per subscriber, and the
# `send_newsletters` command, run every minute on the server, sends them in small batches.
# Sending logic and the emails themselves: core/newsletter.py.
NEWSLETTER_FEATURES = [*TEXT_FEATURES, "h2", "image", "hr"]


class Subscriber(models.Model):
    SOURCES = [("form", "Sign-up form"), ("admin", "Added by an editor"), ("old-site", "Old website")]
    email = models.EmailField(unique=True, help_text="Only add people who have asked to receive the newsletter.")
    name = models.CharField(max_length=200, blank=True)
    subscribed_at = models.DateTimeField(default=timezone.now, editable=False)
    source = models.CharField(max_length=10, choices=SOURCES, default="admin", editable=False)

    panels = [FieldPanel("email"), FieldPanel("name")]

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return f"{self.name} <{self.email}>" if self.name else self.email

    def clean(self):
        self.email = self.email.strip().lower()  # before the unique check, so case can't make duplicates

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class NewsletterIndexPage(RoutablePageMixin, BasePage):
    """Sign-up form, and the archive of newsletters already sent."""
    max_count = 1
    subpage_types = ["core.NewsletterPage"]
    guard = FormGuard("lrs.newsletter")

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["newsletters"] = (NewsletterPage.objects.child_of(self).live().public()
                                  .filter(send__isnull=False).select_related("send").order_by("-send__started_at"))
        return context

    @path("")
    def signup(self, request):
        from .newsletter import SignupForm, start_signup
        form = SignupForm(request.POST or None)
        if request.method == "POST":
            verdict = self.guard.check(request.POST)
            if verdict == "spam":
                logger.info("Newsletter sign-up: spam blocked")
                return self.render(request, context_overrides={"step": "check-email"})
            if verdict == "expired":
                form.is_valid()
                form.add_error(None, EXPIRED_FORM)
            elif form.is_valid():
                start_signup(self, form.cleaned_data)
                return self.render(request, context_overrides={"step": "check-email"})
        return self.render(request, context_overrides={"step": "form", "form": form, **self.guard.context()})


class NewsletterPage(Page):
    body = RichTextField(features=NEWSLETTER_FEATURES)

    content_panels = [TitleFieldPanel("title", help_text="Also the email's subject line."), FieldPanel("body")]
    promote_panels = []
    parent_page_types = ["core.NewsletterIndexPage"]
    subpage_types = []
    preview_modes = [("", "Web page"), ("email", "Email")]

    @property
    def intro(self):
        """The start of the text: the summary in search results and link previews (the theme expects one)."""
        return Truncator(" ".join(unescape(re.sub(r"<[^>]+>", " ", self.body)).split())).words(30)

    def serve_preview(self, request, mode_name):
        if mode_name == "email":
            from .newsletter import render_newsletter
            return HttpResponse(render_newsletter(self)["html"])
        return super().serve_preview(request, mode_name)


class NewsletterSend(models.Model):
    """One sending of a newsletter, with a copy of exactly what went out. Kept apart from the page,
    so editing or copying the page later never makes it look unsent."""
    newsletter = models.OneToOneField(NewsletterPage, on_delete=models.CASCADE, related_name="send")
    started_at = models.DateTimeField(default=timezone.now)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    subject = models.CharField(max_length=255)
    html = models.TextField()
    text = models.TextField()
    recipients = models.PositiveIntegerField(default=0)


class NewsletterDelivery(models.Model):
    """One email still to send, or sent. Deleted with the subscriber when they unsubscribe."""
    send = models.ForeignKey(NewsletterSend, on_delete=models.CASCADE, related_name="deliveries")
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="+")
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    failures = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["send", "subscriber"], name="one_delivery_each")]


# --- Photo privacy and size ----------------------------------------------------------
# Phone and camera photos carry hidden data (GPS location, camera, owner) that Wagtail copies into
# every resized version it serves, and are often far larger than the site ever shows, which makes
# every resized copy slow to make. Every new upload is re-saved without the hidden data, turned
# upright, and shrunk to MAX_ORIGINAL pixels on its long side (more than any size the theme uses).
CLEAN_QUALITY = 92
MAX_ORIGINAL = 3000


def cleaned_photo(file):
    """(bytes, (width, height)) of the photo without metadata and at most MAX_ORIGINAL on its long side,
    or None if it needs neither or can't be read."""
    try:
        file.seek(0)
        photo = PILImage.open(file)
        photo.load()
    except Exception:  # not an image Pillow can read; Wagtail's own checks deal with it
        return None
    finally:
        file.seek(0)
    has_metadata = photo.getexif() or any(key in photo.info for key in ("exif", "xmp", "XML:com.adobe.xmp"))
    if not has_metadata and max(photo.size) <= MAX_ORIGINAL:
        return None
    fmt = photo.format
    clean = ImageOps.exif_transpose(photo)
    icc = clean.info.get("icc_profile")  # keep colours, drop the rest
    clean.thumbnail((MAX_ORIGINAL, MAX_ORIGINAL), PILImage.Resampling.LANCZOS)
    clean.info = {}
    out = BytesIO()
    options = {"icc_profile": icc} if icc else {}
    if fmt != "PNG":
        options["quality"] = CLEAN_QUALITY
    clean.save(out, "JPEG" if fmt == "MPO" else fmt, **options)
    return out.getvalue(), clean.size


@receiver(pre_save, sender=Image)
def clean_photo(sender, instance, **kwargs):
    if not instance.file or getattr(instance.file, "_committed", True):
        return  # no new file in this save
    cleaned = cleaned_photo(instance.file)
    if cleaned is not None:
        data, size = cleaned
        instance.file.save(Path(instance.file.name).name, ContentFile(data), save=False)
        instance.width, instance.height = size  # set after the save, which clears them; upright photos swap sides
        instance._set_image_file_metadata()  # size and hash of the cleaned file


def shrink_original(image):
    """Shrink an image uploaded before MAX_ORIGINAL existed: same cleaning as an upload, with the
    focal point moved to match, and the old file and resized copies removed. Returns True if shrunk."""
    if max(image.width, image.height) <= MAX_ORIGINAL:
        return False
    old_name, old_width = image.file.name, image.width
    with image.open_file() as f:
        data = f.read()
    image.file = ContentFile(data, name=Path(old_name).name)
    image.save()  # clean_photo shrinks it
    if image.focal_point_width:
        scale = image.width / old_width
        for field in ["focal_point_x", "focal_point_y", "focal_point_width", "focal_point_height"]:
            setattr(image, field, max(1, round(getattr(image, field) * scale)))
        image.save(update_fields=["focal_point_x", "focal_point_y", "focal_point_width", "focal_point_height"])
    image.renditions.all().delete()  # their files are removed with them
    if image.file.name != old_name:
        image.file.storage.delete(old_name)
    return True
