import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"token {settings.GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_notifications(repo_full_name=None):
    """Fetch current notifications from GitHub. Optionally filter by repo."""
    url = f"{GITHUB_API}/notifications"
    params = {"all": "false"}
    if repo_full_name:
        params["repo"] = repo_full_name
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_thread_id(repo_full_name, thread_number):
    """Find the notification thread ID for a given repo and PR/issue number."""
    notifications = fetch_notifications(repo_full_name)
    number_str = str(thread_number)
    for notification in notifications:
        subject = notification.get("subject", {})
        subject_url = subject.get("url", "")
        # URL ends with /pulls/{number} or /issues/{number}
        if subject_url.endswith(f"/{number_str}"):
            return notification["id"]
    return None


def set_thread_subscription(thread_id, subscribed=False, ignored=False):
    """Set subscription state for a notification thread."""
    url = f"{GITHUB_API}/notifications/threads/{thread_id}/subscription"
    data = {"subscribed": subscribed, "ignored": ignored}
    resp = requests.put(url, headers=_headers(), json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def suppress_thread(thread_id, suppress_mode="unsubscribe"):
    """Suppress a notification thread using the configured mode."""
    if suppress_mode == "ignore":
        return set_thread_subscription(thread_id, subscribed=False, ignored=True)
    else:
        return set_thread_subscription(thread_id, subscribed=False, ignored=False)
