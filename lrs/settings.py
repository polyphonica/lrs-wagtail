"""Settings for the LRS website. Everything environment-specific comes from env vars."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


DEBUG = env("DEBUG", "0") == "1"
SECRET_KEY = env("SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY (or DEBUG=1 for local development).")
ALLOWED_HOSTS = env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

# The design layer. Each theme folder holds its own templates and static files;
# switching design = setting LRS_THEME to another folder under themes/.
THEME = env("LRS_THEME", "classic")
THEME_DIR = BASE_DIR / "themes" / THEME

INSTALLED_APPS = [
    "core",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.routable_page",
    "wagtail.contrib.settings",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "django_filters",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "lrs.urls"
WSGI_APPLICATION = "lrs.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [THEME_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "wagtail.contrib.settings.context_processors.settings",
        "core.context_processors.footer",
    ]},
}]

if env("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }}
    INSTALLED_APPS.append("django.contrib.postgres")  # Wagtail's search uses Postgres full-text search
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
WAGTAIL_FRONTEND_LOGIN_URL = "/login/"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_DIRS = [THEME_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": (
        "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "django.contrib.staticfiles.storage.ManifestStaticFilesStorage")},
}

# --- Wagtail -------------------------------------------------------------
WAGTAIL_SITE_NAME = "Liverpool Renaissance Singers"
WAGTAILADMIN_BASE_URL = env("SITE_URL", "http://localhost:8000")
WAGTAILSEARCH_BACKENDS = {"default": {"BACKEND": "wagtail.search.backends.database"}}
WAGTAIL_ENABLE_UPDATE_CHECK = False
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10_000

# Images: no SVG or GIF; originals are never served to the public (nginx), only resized copies.
WAGTAILIMAGES_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "avif", "heic"]
WAGTAILIMAGES_MAX_UPLOAD_SIZE = 20 * 1024 * 1024
WAGTAILIMAGES_MAX_IMAGE_PIXELS = 60_000_000
WAGTAILIMAGES_FORMAT_CONVERSIONS = {"heic": "jpeg", "avif": "avif", "webp": "webp", "png": "png"}

# Documents and audio samples. Every download goes through Wagtail's permission check.
AUDIO_EXTENSIONS = ["mp3", "m4a", "aac", "ogg", "oga", "opus"]
WAGTAILDOCS_EXTENSIONS = ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "odt", "ods", "txt", "csv", "zip",
                          *AUDIO_EXTENSIONS]
WAGTAILDOCS_MAX_UPLOAD_SIZE = 40 * 1024 * 1024
WAGTAILDOCS_SERVE_METHOD = "serve_view"
WAGTAILDOCS_INLINE_CONTENT_TYPES = ["application/pdf", "text/plain", "audio/mpeg", "audio/mp4",
                                    "audio/aac", "audio/ogg", "audio/opus"]
if env("NGINX_SENDFILE", "0") == "1":
    # After the permission check, nginx streams the file (fast, supports seeking in audio).
    SENDFILE_BACKEND = "core.sendfile_nginx"
    SENDFILE_URL = "/protected/"

# --- Email -----------------------------------------------------------------
# Locally (DEBUG=1) emails print to the terminal unless EMAIL_BACKEND is set to the SMTP backend.
EMAIL_BACKEND = env("EMAIL_BACKEND") or ("django.core.mail.backends.console.EmailBackend" if DEBUG
                                         else "django.core.mail.backends.smtp.EmailBackend")
EMAIL_TIMEOUT = 20
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost")

# Newsletter: emails sent per run of `send_newsletters` (every minute on the server), and at most per
# 24 hours. Gmail allows about 500 a day; the rest is kept for password resets and contact messages.
NEWSLETTER_BATCH = int(env("NEWSLETTER_BATCH", "20"))
NEWSLETTER_DAILY_LIMIT = int(env("NEWSLETTER_DAILY_LIMIT", "400"))

# --- Security --------------------------------------------------------------
X_FRAME_OPTIONS = "SAMEORIGIN"  # Wagtail's live preview needs same-origin frames
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
