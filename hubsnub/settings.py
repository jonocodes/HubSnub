import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hubsnub.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hubsnub.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Unfold admin configuration
UNFOLD = {
    "SITE_TITLE": "HubSnub",
    "SIDEBAR": {
        "navigation": [
            {
                "title": "Notifications",
                "separator": True,
                "items": [
                    {
                        "title": "Preferences",
                        "icon": "tune",
                        "link": "/admin/notifications/notificationpreferences/",
                    },
                    {
                        "title": "Watched Repos",
                        "icon": "visibility",
                        "link": "/admin/notifications/watchedrepo/",
                    },
                    {
                        "title": "Event Log",
                        "icon": "list_alt",
                        "link": "/admin/notifications/notificationlog/",
                    },
                ],
            },
            {
                "title": "Tools",
                "separator": True,
                "items": [
                    {
                        "title": "Dry Run",
                        "icon": "play_circle",
                        "link": "/admin/dry-run/",
                    },
                    {
                        "title": "Cache Viewer",
                        "icon": "cached",
                        "link": "/admin/cache-viewer/",
                    },
                ],
            },
            {
                "title": "Auth",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": "/admin/auth/user/",
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": "/admin/auth/group/",
                    },
                ],
            },
        ],
    },
}

# GitHub App configuration
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
GITHUB_PRIVATE_KEY_PATH = os.environ.get("GITHUB_PRIVATE_KEY_PATH", "")
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")
