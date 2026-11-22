"""Template variables every page needs."""


def footer(request):
    """The footer's newsletter sign-up: where it posts, and the spam checks (same as the Newsletter page)."""
    if request.path.startswith("/admin/"):
        return {}
    from .models import NewsletterIndexPage
    page = NewsletterIndexPage.objects.live().first()
    if not page:
        return {}
    return {"footer_signup": {"url": page.url, **page.guard.context()}}
