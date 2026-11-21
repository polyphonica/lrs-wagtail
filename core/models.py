"""The stable content model. Themes only read from these; they never define content."""
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import models
from django.utils import timezone
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from wagtail.contrib.forms.panels import FormSubmissionsPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.documents import get_document_model
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Collection, Orderable, Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from .blocks import TEXT_FEATURES, ConcertBody, PageBody

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
    body = StreamField(PageBody(), blank=True)

    content_panels = BasePage.content_panels + [FieldPanel("body")]
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
