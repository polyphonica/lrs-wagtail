"""Newsletter: sign-up, unsubscribe, the emails, and sending in batches (see the note in models.py)."""
import html as html_lib
import logging
import mimetypes
import re
import smtplib
from datetime import timedelta

from django import forms
from django.conf import settings
from django.core import mail, signing
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_exempt
from wagtail.models import Site
from wagtail.rich_text import expand_db_html

from .models import NewsletterDelivery, NewsletterIndexPage, NewsletterSend, SiteSettings, Subscriber

logger = logging.getLogger(__name__)

CONFIRM_SALT = "lrs.newsletter.confirm"
CONFIRM_DAYS = 7
UNSUBSCRIBE = "%%UNSUBSCRIBE_URL%%"  # filled in per recipient
MAX_FAILURES = 3  # then that address is skipped for this newsletter


def site_url(path=""):
    return settings.WAGTAILADMIN_BASE_URL.rstrip("/") + path


# --- Sign-up and unsubscribe -------------------------------------------------------
class SignupForm(forms.Form):
    name = forms.CharField(label="Your name (optional)", max_length=200, required=False)
    email = forms.EmailField(label="Email address")


def start_signup(index_page, data):
    """Email a confirmation link. Nobody is stored until they click it, so a mistyped or
    someone else's address never ends up on the list."""
    email = data["email"].strip().lower()
    if Subscriber.objects.filter(email=email).exists():
        return  # the page says the same either way, and existing subscribers get no extra email
    token = signing.dumps({"e": email, "n": data["name"].strip()}, salt=CONFIRM_SALT, compress=True)
    context = {"name": data["name"].strip(), "url": site_url(reverse("newsletter_confirm", args=[token])),
               "days": CONFIRM_DAYS}
    try:
        mail.send_mail("Please confirm your subscription to the LRS newsletter",
                       render_to_string("core/email/newsletter_confirm.txt", context), None, [email])
    except Exception:
        logger.exception("Newsletter sign-up: confirmation email not sent")


def unsubscribe_token(subscriber):
    # The email is part of the signature, so a token can never match someone given the same id later.
    return signing.Signer(salt=f"lrs.newsletter.unsubscribe:{subscriber.email}").sign(str(subscriber.pk))


def subscriber_for_token(token):
    pk = token.split(":", 1)[0]
    subscriber = Subscriber.objects.filter(pk=pk).first() if pk.isdigit() else None
    if subscriber:
        try:
            if signing.Signer(salt=f"lrs.newsletter.unsubscribe:{subscriber.email}").unsign(token) == pk:
                return subscriber
        except signing.BadSignature:
            pass
    return None


def unsubscribe_url(subscriber):
    return site_url(reverse("newsletter_unsubscribe", args=[unsubscribe_token(subscriber)]))


def action_page(request, step, **context):
    return render(request, "newsletter_action.html",
                  {"step": step, "newsletter_page": NewsletterIndexPage.objects.live().first(), **context})


def confirm(request, token):
    """The link in the confirmation email. Opening it only shows a button, because some mail
    systems open every link in an email to check it; pressing the button subscribes."""
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=timedelta(days=CONFIRM_DAYS))
    except signing.BadSignature:  # includes expired
        return action_page(request, "bad-confirm")
    if request.method == "POST":
        subscriber, _ = Subscriber.objects.get_or_create(email=data["e"], defaults={"name": data["n"], "source": "form"})
        return action_page(request, "subscribed", subscriber=subscriber)
    return action_page(request, "confirm", email=data["e"])


@csrf_exempt  # mail programs' one-click unsubscribe (RFC 8058) posts here without a form; the token is the proof
def unsubscribe(request, token):
    subscriber = subscriber_for_token(token)
    if request.method == "POST":
        if subscriber:
            logger.info("Newsletter: unsubscribed")
            subscriber.delete()  # also removes their unsent deliveries
        return action_page(request, "unsubscribed")
    if not subscriber:
        return action_page(request, "not-found")  # already gone, or a test email's link
    return action_page(request, "unsubscribe", email=subscriber.email)


# --- The email ---------------------------------------------------------------------
def absolute_links(body):
    """Emails need full addresses for links and pictures, and pictures must not overflow a phone."""
    body = re.sub(r'(href|src)="/(?!/)', lambda m: f'{m[1]}="{site_url()}/', body)
    return body.replace("<img ", '<img style="max-width:100%;height:auto" ')


def html_to_text(body):
    """A plain-text copy of the newsletter, for mail programs that don't show HTML."""
    def link(m):
        url, label = m[1], strip_tags(m[2]).strip()
        return url if label in ("", url) else f"{label} ({url})"
    text = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', link, body, flags=re.S)
    text = re.sub(r"<li[^>]*>", "\n- ", text)
    text = re.sub(r"<hr[^>]*>", "\n\n----\n\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</(p|h[1-6]|ul|ol)>", "\n\n", text)
    text = html_lib.unescape(strip_tags(text))
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def render_newsletter(page):
    """Subject, HTML and text of the email, with UNSUBSCRIBE where each recipient's link goes."""
    body = absolute_links(expand_db_html(page.body))
    context = {"page": page, "body": body, "web_url": site_url(page.get_url_parts()[2]),
               "unsubscribe_url": UNSUBSCRIBE, "site": SiteSettings.for_site(page.get_site())}
    return {"subject": page.title,
            "html": render_to_string("core/email/newsletter.html", context),
            "text": render_to_string("core/email/newsletter.txt", {**context, "body": html_to_text(body)})}


def contact_email():
    """Replies to a newsletter go to the choir's contact address (Settings → Site settings)."""
    site = Site.objects.filter(is_default_site=True).first()
    return SiteSettings.for_site(site).contact_email if site else ""


class NewsletterEmail(mail.EmailMultiAlternatives):
    """An email whose pictures travel inside it ("related" parts the HTML refers to as cid:...), so they
    show as soon as it opens; linked pictures are hidden by Outlook and others until the reader asks."""
    def __init__(self, *args, pictures=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.pictures = pictures  # (content id, bytes, MIME type)

    def message(self, **kwargs):
        message = super().message(**kwargs)
        html = message.get_body(("html",))
        for cid, data, mime_type in self.pictures:
            html.add_related(data, *mime_type.split("/"), cid=f"<{cid}>", disposition="inline")
        return message


MAX_PICTURES_BYTES = 5 * 1024 * 1024  # beyond this, later pictures stay as links (mail servers refuse huge emails)


def built_in_pictures(html, cache):
    """Swap the site's pictures in the HTML for ones carried in the email. A picture whose file has
    gone (e.g. remade since) stays a link. `cache` keeps files read once per batch."""
    pictures, cids, total = [], {}, 0

    def swap(match):
        nonlocal total
        name = match[2]
        if name in cids:  # the same picture twice: carried once
            return f'src="cid:{cids[name]}"'
        if name not in cache:
            try:
                with default_storage.open(name) as f:
                    cache[name] = f.read()
            except OSError:
                cache[name] = None
        data = cache[name]
        mime_type = mimetypes.guess_type(name)[0] or ""
        if not data or not mime_type.startswith("image/") or total + len(data) > MAX_PICTURES_BYTES:
            return match[0]
        cids[name] = cid = f"picture{len(pictures) + 1}@lrs"
        pictures.append((cid, data, mime_type))
        total += len(data)
        return f'src="cid:{cid}"'

    return re.sub(r'src="(' + re.escape(site_url()) + r'/media/(images/[^"]+))"', swap, html), pictures


def build_message(email, to, unsubscribe_link, reply_to="", connection=None, cache=None):
    """`email` is render_newsletter()'s result or a NewsletterSend (same fields)."""
    get = email.get if isinstance(email, dict) else lambda k: getattr(email, k)
    html, pictures = built_in_pictures(get("html").replace(UNSUBSCRIBE, unsubscribe_link),
                                       {} if cache is None else cache)
    message = NewsletterEmail(
        get("subject"), get("text").replace(UNSUBSCRIBE, unsubscribe_link), to=[to],
        reply_to=[reply_to] if reply_to else None, connection=connection, pictures=pictures,
        headers={"List-Unsubscribe": f"<{unsubscribe_link}>",  # the unsubscribe button Gmail and others show
                 "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
    message.attach_alternative(html, "text/html")
    return message


def send_test(page, to):
    """A copy to one person, straight away. Its unsubscribe link does nothing."""
    build_message(render_newsletter(page), to, site_url(reverse("newsletter_unsubscribe", args=["test"])),
                  contact_email()).send()


# --- Sending -----------------------------------------------------------------------
@transaction.atomic
def queue(page, user):
    """Freeze what goes out and make one delivery per current subscriber. Returns the NewsletterSend."""
    send = NewsletterSend.objects.create(newsletter=page, started_by=user, **render_newsletter(page))
    NewsletterDelivery.objects.bulk_create(
        [NewsletterDelivery(send=send, subscriber=s) for s in Subscriber.objects.all()])
    send.recipients = send.deliveries.count()
    send.save(update_fields=["recipients"])
    return send


def sent_in_last_day():
    return NewsletterDelivery.objects.filter(sent_at__gte=timezone.now() - timedelta(days=1)).count()


def send_pending(batch=None, daily_limit=None):
    """Send up to `batch` waiting emails, keeping to the daily limit (Gmail allows about 500 a day,
    and password resets and contact messages need some of that). Returns how many were sent."""
    batch = batch or settings.NEWSLETTER_BATCH
    room = min(batch, (daily_limit or settings.NEWSLETTER_DAILY_LIMIT) - sent_in_last_day())
    if room <= 0:
        return 0
    pending = list(NewsletterDelivery.objects.filter(sent_at__isnull=True, failures__lt=MAX_FAILURES)
                   .select_related("send", "subscriber").order_by("send__started_at", "id")[:room])
    sent = 0
    if not pending:
        return sent
    reply_to = contact_email()
    cache = {}  # picture files, read once per batch
    with mail.get_connection() as connection:
        for delivery in pending:
            try:
                build_message(delivery.send, delivery.subscriber.email, unsubscribe_url(delivery.subscriber),
                              reply_to, connection, cache).send()
            except Exception as error:
                delivery.failures += 1
                delivery.error = str(error)[:300]
                delivery.save(update_fields=["failures", "error"])
                logger.warning("Newsletter: sending failed (%s)", delivery.error)
                if isinstance(error, smtplib.SMTPRecipientsRefused):
                    continue  # this address is refused; carry on with the others
                break  # the mail server is down, refusing or limiting us: try again next run
            delivery.sent_at = timezone.now()
            delivery.error = ""
            delivery.save(update_fields=["sent_at", "error"])
            sent += 1
    return sent


def progress(send):
    deliveries = send.deliveries
    return {"sent": deliveries.filter(sent_at__isnull=False).count(),
            "waiting": deliveries.filter(sent_at__isnull=True, failures__lt=MAX_FAILURES).count(),
            "failed": deliveries.filter(sent_at__isnull=True, failures__gte=MAX_FAILURES).count()}
