"""
AutismCare settings.

Values come from a local .env file (see .env.example). If no PostgreSQL
credentials are set, a local SQLite file is used so the project still runs.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", DEV_SECRET_KEY)
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# --- Production server (SRS 2.4; NFR 3 encryption in transit) ---------------
if not DEBUG:
    if SECRET_KEY == DEV_SECRET_KEY:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG is False.")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # the host's proxy handles HTTPS
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SSL_REDIRECT", "True") == "True"
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if SECURE_SSL_REDIRECT else 0

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "accounts",
    "directory",
    "screening",
    "learning",
]

MIDDLEWARE = [
    "config.middleware.ServerTimingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # serves compressed CSS/JS (NFR 2)
    "django.middleware.gzip.GZipMiddleware",        # compresses pages and API replies (NFR 2)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database (SRS 2.4: PostgreSQL) -----------------------------------------
# DATABASE_URL is what hosts such as Neon and Render give; DB_* is for a local PostgreSQL.
if os.getenv("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.parse(
        os.environ["DATABASE_URL"], conn_max_age=600, conn_health_checks=True)}
    if "-pooler." in os.environ["DATABASE_URL"]:
        # Neon's pooler (PgBouncer, transaction mode) can't keep server-side cursors open
        DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
elif os.getenv("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,  # reuse connections between requests
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Authentication (FR 1.2) -------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
# Only the lockout backend: it is used by the API, the web pages and /admin.
AUTHENTICATION_BACKENDS = ["accounts.backends.LockoutBackend"]
MAX_FAILED_LOGIN_ATTEMPTS = 5

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}

# --- Geocoding (SRS 3.3 / 3.4) ----------------------------------------------
GEOCODER_URL = os.getenv("GEOCODER_URL", "https://nominatim.openstreetmap.org/search")
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "AutismCare/0.1 (student project)")
EXTERNAL_API_TIMEOUT_SECONDS = 5

# --- AI teaching assistant (SRS 3.3) ----------------------------------------
# New cards come from a local Qwen model run by Ollama, in the background.
# Leave OLLAMA_URL empty to turn AI off. The built-in cards always work.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
AI_FLASHCARDS_MODEL = os.getenv("AI_FLASHCARDS_MODEL", "qwen3.5:2b")
AI_FLASHCARDS_ENABLED = os.getenv("AI_FLASHCARDS_ENABLED", "True") == "True"
AI_FLASHCARDS_TIMEOUT_SECONDS = int(os.getenv("AI_FLASHCARDS_TIMEOUT_SECONDS", "120"))  # for the background job
AI_FLASHCARDS_BACKGROUND = True  # False runs it straight away (used in tests)
# "ollama" (local AI model) or "wordbank" (rule-based cards from the database, for the cloud server)
AI_FLASHCARDS_PROVIDER = os.getenv("AI_FLASHCARDS_PROVIDER", "ollama")

# --- Search limits (FR 3.1) --------------------------------------------------
SEARCH_MIN_RADIUS_KM = 5
SEARCH_MAX_RADIUS_KM = 50
SEARCH_MAX_RESULTS = 30             # nearest N therapists returned per search
SEARCH_MAX_CLINICS_PER_RESULT = 3   # nearest clinics shown per therapist
SEARCH_CACHE_SECONDS = 30           # how long the list of verified therapists is reused (NFR 1)

# --- Files ---------------------------------------------------------------------
# Licence documents are private: only staff can open them, through the admin.
MEDIA_ROOT = BASE_DIR / "private_media"
LICENSE_MAX_UPLOAD_MB = 5

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # filled by collectstatic on the server
# On the server, file names carry a content hash so browsers can cache them for a year (NFR 2).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage" if DEBUG
                    else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
