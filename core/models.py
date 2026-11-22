"""The stable content model. Themes only read from these; they never define content."""
import logging
import time
from io import BytesIO
from pathlib import Path

from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.template.response import TemplateResponse
from django.utils import timezone
from modelcluster.fields import ParentalKey
from PIL import Image as PILImage, ImageOps
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
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

from .blocks import TEXT_FEATURES, ConcertBody, PageBody

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
    contact_email = models.EmailField(blank=True)
    charity_number = models.CharField(max_length=40, blank=True)
    footer_text = models.CharField(max_length=300, blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)


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
                     "core.GalleryPage", "core.DocumentsPage", "core.ContactPage"]

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

    # Spam protection, no outside service. Two checks that people never notice:
    # - a "website" box hidden from people (screen readers and keyboards skip it too); bots fill it in;
    # - a signed time stamp in the form; a reply sent within seconds of the page loading is a bot.
    # Both stay outside the Wagtail form, so they are never stored or emailed. Spam gets the normal
    # thank-you page (so bots learn nothing) but is not saved or sent.
    TRAP_FIELD = "website"
    STARTED_FIELD = "started"
    MIN_SECONDS = 3
    MAX_SECONDS = 2 * 24 * 60 * 60
    SIGNING_SALT = "lrs.contact"

    def spam_check(self, data):
        """Return "spam", "expired" (a person who left the page open too long) or "" (fine)."""
        if data.get(self.TRAP_FIELD):
            return "spam"
        try:
            started = signing.loads(data.get(self.STARTED_FIELD, ""), salt=self.SIGNING_SALT,
                                    max_age=self.MAX_SECONDS)
        except signing.SignatureExpired:
            return "expired"
        except signing.BadSignature:
            return "spam"
        return "spam" if time.time() - started < self.MIN_SECONDS else ""

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["trap_field"] = self.TRAP_FIELD
        context["started_field"] = self.STARTED_FIELD
        context["started"] = signing.dumps(time.time(), salt=self.SIGNING_SALT)
        return context

    def serve(self, request, *args, **kwargs):
        if request.method == "POST":
            verdict = self.spam_check(request.POST)
            if verdict == "spam":
                logger.info("Contact form: spam blocked")
                return self.render_landing_page(request, None, *args, **kwargs)
            if verdict == "expired":
                form = self.get_form(request.POST, request.FILES, page=self, user=request.user)
                form.is_valid()
                form.add_error(None, "This page was open for a long time. Please press Send again.")
                context = self.get_context(request)
                context["form"] = form
                return TemplateResponse(request, self.get_template(request), context)
        return super().serve(request, *args, **kwargs)


# --- Photo privacy ------------------------------------------------------------
# Phone and camera photos carry hidden data (GPS location, camera, owner) that Wagtail copies into
# every resized version it serves. Every new upload is re-saved without it, turned upright first.
CLEAN_QUALITY = 92


def without_metadata(file):
    """(bytes, (width, height)) of the photo with all metadata removed, or None if it has none or can't be read."""
    try:
        file.seek(0)
        photo = PILImage.open(file)
        photo.load()
    except Exception:  # not an image Pillow can read; Wagtail's own checks deal with it
        return None
    finally:
        file.seek(0)
    if not (photo.getexif() or any(key in photo.info for key in ("exif", "xmp", "XML:com.adobe.xmp"))):
        return None
    fmt = photo.format
    clean = ImageOps.exif_transpose(photo)
    clean.info = {k: v for k, v in clean.info.items() if k == "icc_profile"}  # keep colours, drop the rest
    out = BytesIO()
    options = {"icc_profile": clean.info["icc_profile"]} if "icc_profile" in clean.info else {}
    if fmt != "PNG":
        options["quality"] = CLEAN_QUALITY
    clean.save(out, "JPEG" if fmt == "MPO" else fmt, **options)
    return out.getvalue(), clean.size


@receiver(pre_save, sender=Image)
def strip_photo_metadata(sender, instance, **kwargs):
    if not instance.file or getattr(instance.file, "_committed", True):
        return  # no new file in this save
    cleaned = without_metadata(instance.file)
    if cleaned is not None:
        data, size = cleaned
        instance.file.save(Path(instance.file.name).name, ContentFile(data), save=False)
        instance.width, instance.height = size  # set after the save, which clears them; upright photos swap sides
        instance._set_image_file_metadata()  # size and hash of the cleaned file
