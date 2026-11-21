"""Content blocks admins stack to build pages. Themes decide how each one looks."""
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from wagtail import blocks
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.snippets.blocks import SnippetChooserBlock

TEXT_FEATURES = ["h3", "bold", "italic", "link", "ol", "ul", "document-link"]

YOUTUBE_ID = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})")


def youtube_id(url):
    match = YOUTUBE_ID.search(url or "")
    return match.group(1) if match else None


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    caption = blocks.CharBlock(required=False)
    alt_text = blocks.CharBlock(required=False, help_text="Describe the image for people using screen readers.")

    class Meta:
        icon = "image"


class ImageTextBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    alt_text = blocks.CharBlock(required=False, help_text="Describe the image for people using screen readers.")
    image_side = blocks.ChoiceBlock(choices=[("left", "Left"), ("right", "Right")], default="left",
                                    help_text="On phones the image always comes first.")
    text = blocks.RichTextBlock(features=TEXT_FEATURES)

    class Meta:
        icon = "image"
        label = "Image beside text"


class GalleryBlock(blocks.StructBlock):
    images = blocks.ListBlock(ImageChooserBlock(), min_num=2)
    caption = blocks.CharBlock(required=False)

    class Meta:
        icon = "grip"


class AudioBlock(blocks.StructBlock):
    file = DocumentChooserBlock(help_text="Upload an MP3, M4A or OGG file into the 'Audio' collection.")
    title = blocks.CharBlock(help_text="e.g. Byrd – Kyrie from the Mass for Four Voices")
    note = blocks.CharBlock(required=False, help_text="e.g. Recorded live at St John's, May 2025")

    def clean(self, value):
        value = super().clean(value)
        doc = value.get("file")
        if doc and Path(doc.file.name).suffix.lower().lstrip(".") not in settings.AUDIO_EXTENSIONS:
            raise StructBlockValidationError(block_errors={
                "file": ValidationError("Please choose an audio file (MP3, M4A, AAC or OGG).")})
        return value

    class Meta:
        icon = "media"


class YouTubeValue(blocks.StructValue):
    def video_id(self):
        return youtube_id(self.get("url"))


class YouTubeBlock(blocks.StructBlock):
    url = blocks.URLBlock(label="YouTube link", help_text="Paste the address of the video from YouTube.")
    caption = blocks.CharBlock(required=False)

    def clean(self, value):
        value = super().clean(value)
        if not youtube_id(value.get("url")):
            raise StructBlockValidationError(block_errors={
                "url": ValidationError("That doesn't look like a YouTube video link.")})
        return value

    class Meta:
        icon = "media"
        label = "YouTube video"
        value_class = YouTubeValue


class ProgrammeItemBlock(blocks.StructBlock):
    piece = blocks.CharBlock()
    composer = SnippetChooserBlock("core.Composer", required=False)
    note = blocks.CharBlock(required=False, help_text="e.g. soloist, or 'first performance'")


class ProgrammeBlock(blocks.StructBlock):
    heading = blocks.CharBlock(default="Programme")
    items = blocks.ListBlock(ProgrammeItemBlock())

    class Meta:
        icon = "list-ul"


class QuoteBlock(blocks.StructBlock):
    quote = blocks.TextBlock()
    attribution = blocks.CharBlock(required=False)

    class Meta:
        icon = "openquote"


class ButtonBlock(blocks.StructBlock):
    label = blocks.CharBlock()
    page = blocks.PageChooserBlock(required=False)
    url = blocks.URLBlock(required=False, help_text="Use this for links to other websites.")

    def clean(self, value):
        value = super().clean(value)
        if not value.get("page") and not value.get("url"):
            raise StructBlockValidationError(non_block_errors=ValidationError("Choose a page or enter a link."))
        return value

    class Meta:
        icon = "link"


class FAQBlock(blocks.StructBlock):
    question = blocks.CharBlock()
    answer = blocks.RichTextBlock(features=TEXT_FEATURES)

    class Meta:
        icon = "help"
        label = "Question and answer"


class LinkCardBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    url = blocks.URLBlock()
    description = blocks.TextBlock(required=False)

    class Meta:
        icon = "link-external"
        label = "Link card"


class CommonBody(blocks.StreamBlock):
    text = blocks.RichTextBlock(features=TEXT_FEATURES, icon="pilcrow")
    image = ImageBlock()
    gallery = GalleryBlock()
    audio = AudioBlock()
    video = YouTubeBlock()
    quote = QuoteBlock()
    button = ButtonBlock()


class ConcertBody(CommonBody):
    programme = ProgrammeBlock()


class PageBody(CommonBody):
    heading = blocks.CharBlock(icon="title", form_classname="title")
    image_text = ImageTextBlock()
    faq = FAQBlock()
    link_card = LinkCardBlock()
