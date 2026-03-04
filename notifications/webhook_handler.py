import hashlib
import hmac
import json
import logging

from django.conf import settings

from . import cache
from .github_client import find_thread_id, suppress_thread
from .models import NotificationLog
from .rules import evaluate_event

logger = logging.getLogger(__name__)


def verify_signature(payload_body, signature_header):
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    if not signature_header:
        return False
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured, skipping verification")
        return True
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def handle_webhook(event_type, payload):
    """
    Process a verified webhook event.

    1. Evaluate against preferences
    2. If suppress: look up thread ID (cached), call GitHub API
    3. Log the decision
    """
    action = payload.get("action", "")

    result = evaluate_event(event_type, action, payload)
    decision = result["decision"]
    repo_full_name = result["repo_full_name"]
    thread_number = result["thread_number"]

    # Build GitHub URL
    github_url = ""
    if repo_full_name and thread_number:
        pr = payload.get("pull_request")
        if pr:
            github_url = f"https://github.com/{repo_full_name}/pull/{thread_number}"
        else:
            github_url = f"https://github.com/{repo_full_name}/issues/{thread_number}"

    # If suppress, attempt to unsubscribe from the thread
    if decision == "suppress" and repo_full_name and thread_number:
        _suppress_notification(repo_full_name, thread_number, result)

    # Log the decision
    if thread_number:
        NotificationLog.objects.create(
            repo=repo_full_name,
            thread_number=thread_number,
            event_type=f"{event_type}.{action}" if action else event_type,
            action_taken=decision,
            detail=result["reason"],
            github_url=github_url,
        )

    logger.info(
        "Webhook %s.%s on %s#%s → %s: %s",
        event_type,
        action,
        repo_full_name,
        thread_number,
        decision,
        result["reason"],
    )

    return result


def _suppress_notification(repo_full_name, thread_number, result):
    """Look up thread ID and suppress the notification."""
    from .rules import resolve_preferences, get_watched_repo

    cache_key = f"{repo_full_name}:{thread_number}"
    thread_id = cache.get(cache_key)

    if not thread_id:
        try:
            thread_id = find_thread_id(repo_full_name, thread_number)
            if thread_id:
                cache.put(cache_key, thread_id)
        except Exception:
            logger.exception("Failed to find thread ID for %s", cache_key)
            return

    if not thread_id:
        logger.warning("Could not find thread ID for %s", cache_key)
        return

    # Determine suppress mode
    owner, repo_name = repo_full_name.split("/", 1)
    watched = get_watched_repo(owner, repo_name)
    prefs = resolve_preferences(watched) if watched else {}
    suppress_mode = prefs.get("suppress_mode", "unsubscribe")

    try:
        suppress_thread(thread_id, suppress_mode)
        logger.info("Suppressed thread %s (%s) via %s", cache_key, thread_id, suppress_mode)
    except Exception:
        logger.exception("Failed to suppress thread %s (%s)", cache_key, thread_id)
