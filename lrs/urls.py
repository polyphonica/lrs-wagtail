from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps import Sitemap
from wagtail.documents import urls as wagtaildocs_urls

urlpatterns = [
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("login/", auth_views.LoginView.as_view(template_name="login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Forgotten password: one themed template for all four steps; the email wording lives in core.
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="password_reset.html", extra_context={"step": "request"},
        email_template_name="core/email/password_reset.txt",
        subject_template_name="core/email/password_reset_subject.txt"), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="password_reset.html", extra_context={"step": "sent"}), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="password_reset.html", extra_context={"step": "confirm"}), name="password_reset_confirm"),
    path("password-reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="password_reset.html", extra_context={"step": "complete"}), name="password_reset_complete"),
    path("sitemap.xml", sitemap, {"sitemaps": {"pages": Sitemap}}),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns.append(path("", include(wagtail_urls)))
