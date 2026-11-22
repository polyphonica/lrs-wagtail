"""Admin additions: the newsletter subscriber list, and the "Send newsletter" screen."""
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.widgets import Button
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from . import newsletter
from .models import NewsletterPage, NewsletterSend, Subscriber


class SubscriberViewSet(SnippetViewSet):
    model = Subscriber
    icon = "mail"
    menu_label = "Subscribers"
    menu_order = 250
    add_to_admin_menu = True
    list_display = ["email", "name", "subscribed_at", "source"]
    list_export = ["email", "name", "subscribed_at", "source"]  # download as CSV or Excel
    export_filename = "newsletter-subscribers"
    list_filter = ["source"]
    search_fields = ["email", "name"]
    search_backend_name = None  # plain database search, so no search index to keep up to date


register_snippet(SubscriberViewSet)


def can_send(page, user):
    """Sending goes to every subscriber, so it needs the same right as publishing (Moderators, superusers)."""
    return page.permissions_for_user(user).can_publish()


def send_view(request, page_id):
    page = get_object_or_404(NewsletterPage, id=page_id)
    if not can_send(page, request.user):
        raise PermissionDenied
    sent = NewsletterSend.objects.filter(newsletter=page).first()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "test":
            if not request.user.email:
                messages.error(request, "Your account has no email address. Add one under Account → Profile.")
            else:
                newsletter.send_test(page.get_latest_revision_as_object(), request.user.email)
                messages.success(request, f"A test copy of the latest draft was sent to {request.user.email}.")
        elif action == "send" and not sent:
            if not page.live or page.has_unpublished_changes:
                messages.error(request, "Publish the newsletter first, so that what is sent matches the web page.")
            elif not request.POST.get("confirm"):
                messages.error(request, "Tick the box to confirm.")
            else:
                sent = newsletter.queue(page, request.user)
                messages.success(request, f"Sending to {sent.recipients} subscribers has started.")
        return redirect("newsletter_send", page.id)
    count = Subscriber.objects.count()
    return TemplateResponse(request, "core/admin/send_newsletter.html", {
        "page": page, "page_title": f"Send: {page.title}", "header_icon": "mail",
        "sent": sent, "progress": newsletter.progress(sent) if sent else None, "subscribers": count,
        "daily_limit": settings.NEWSLETTER_DAILY_LIMIT,
        "batch": settings.NEWSLETTER_BATCH,
        "days": -(-count // settings.NEWSLETTER_DAILY_LIMIT) if count else 0,
        "ready": page.live and not page.has_unpublished_changes,
    })


@hooks.register("register_admin_urls")
def newsletter_admin_urls():
    return [path("newsletter/<int:page_id>/send/", send_view, name="newsletter_send")]


def send_button(page, user, priority):
    if page.specific_class is NewsletterPage and can_send(page, user):
        yield Button("Send newsletter", reverse("newsletter_send", args=[page.id]), icon_name="mail",
                     priority=priority)


@hooks.register("register_page_header_buttons")
def newsletter_header_button(page, user, view_name, next_url=None):
    yield from send_button(page, user, 55)


@hooks.register("register_page_listing_more_buttons")
def newsletter_listing_button(page, user, next_url=None):
    yield from send_button(page, user, 35)
