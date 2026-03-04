import logging

from django.conf import settings

from .models import NotificationPreferences, RepoOverride, WatchedRepo

logger = logging.getLogger(__name__)

# Preference fields that can be overridden per-repo
PREF_FIELDS = [
    "review_requested_direct",
    "review_requested_team",
    "pr_approved_or_changes",
    "assigned",
    "comment_on_your_pr",
    "mentioned",
    "pr_merged",
    "pr_failed_checks",
    "suppress_mode",
]


def get_watched_repo(owner, repo):
    """Check if a repo is watched (active). Supports wildcard repos."""
    # Try exact match first
    watched = WatchedRepo.objects.filter(owner=owner, repo=repo, is_active=True).first()
    if watched:
        return watched
    # Try wildcard match
    watched = WatchedRepo.objects.filter(owner=owner, repo="*", is_active=True).first()
    return watched


def resolve_preferences(watched_repo):
    """Resolve effective preferences: global defaults + per-repo overrides."""
    global_prefs = NotificationPreferences.load()
    effective = {}
    for field in PREF_FIELDS:
        effective[field] = getattr(global_prefs, field)

    # Apply per-repo overrides
    try:
        override = watched_repo.override
        for field in PREF_FIELDS:
            val = getattr(override, field)
            if val is not None:
                effective[field] = val
    except RepoOverride.DoesNotExist:
        pass

    return effective


def _is_me(login):
    """Check if the given login matches the configured GitHub username."""
    return login and login.lower() == settings.GITHUB_USERNAME.lower()


def evaluate_event(event_type, action, payload):
    """
    Evaluate a webhook event against preferences.

    Returns a dict with:
        - decision: "allow", "suppress", or "skip"
        - reason: human-readable explanation
        - pref_key: which preference field was consulted (or None)
        - repo_full_name: "owner/repo"
        - thread_number: PR/issue number (or None)
    """
    repo_data = payload.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    owner = repo_data.get("owner", {}).get("login", "")
    repo_name = repo_data.get("name", "")

    result = {
        "decision": "skip",
        "reason": "",
        "pref_key": None,
        "repo_full_name": repo_full_name,
        "thread_number": None,
    }

    # Check if repo is watched
    watched = get_watched_repo(owner, repo_name)
    if not watched:
        result["reason"] = f"Repo {repo_full_name} is not in watched repos"
        return result

    prefs = resolve_preferences(watched)

    # Extract thread number from PR or issue
    pr = payload.get("pull_request")
    issue = payload.get("issue")
    thread_number = None
    if pr:
        thread_number = pr.get("number")
    elif issue:
        thread_number = issue.get("number")
    result["thread_number"] = thread_number

    # Evaluate based on event type and action
    if event_type == "pull_request" and action == "review_requested":
        return _eval_review_requested(payload, prefs, result)

    if event_type == "pull_request_review" and action == "submitted":
        return _eval_review_submitted(payload, prefs, result)

    if event_type in ("issue_comment", "pull_request_review_comment") and action == "created":
        return _eval_comment(payload, prefs, result, event_type)

    if event_type == "pull_request" and action == "closed":
        return _eval_pr_closed(payload, prefs, result)

    if event_type in ("pull_request", "issues") and action == "assigned":
        return _eval_assigned(payload, prefs, result)

    result["reason"] = f"Unhandled event: {event_type}.{action}"
    return result


def _eval_review_requested(payload, prefs, result):
    requested_reviewer = payload.get("requested_reviewer")
    requested_team = payload.get("requested_team")

    if requested_reviewer and _is_me(requested_reviewer.get("login")):
        result["pref_key"] = "review_requested_direct"
        if prefs["review_requested_direct"]:
            result["decision"] = "allow"
            result["reason"] = "Direct review request — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = "Direct review request — suppressed by preference"
        return result

    if requested_team and not requested_reviewer:
        result["pref_key"] = "review_requested_team"
        if prefs["review_requested_team"]:
            result["decision"] = "allow"
            result["reason"] = f"Team review request ({requested_team.get('name', '?')}) — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = f"Team review request ({requested_team.get('name', '?')}) — suppressed by preference"
        return result

    result["reason"] = "Review requested for someone else"
    return result


def _eval_review_submitted(payload, prefs, result):
    pr = payload.get("pull_request", {})
    pr_author = pr.get("user", {}).get("login", "")

    if _is_me(pr_author):
        result["pref_key"] = "pr_approved_or_changes"
        if prefs["pr_approved_or_changes"]:
            result["decision"] = "allow"
            result["reason"] = "Review on your PR — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = "Review on your PR — suppressed by preference"
        return result

    result["reason"] = "Review submitted on someone else's PR"
    return result


def _eval_comment(payload, prefs, result, event_type):
    # Determine the PR/issue author
    if event_type == "issue_comment":
        item = payload.get("issue", {})
    else:
        item = payload.get("pull_request", {})
    item_author = item.get("user", {}).get("login", "")

    comment = payload.get("comment", {})
    comment_body = comment.get("body", "")
    username = settings.GITHUB_USERNAME

    # Check @mention first
    if username and f"@{username}" in comment_body:
        result["pref_key"] = "mentioned"
        if prefs["mentioned"]:
            result["decision"] = "allow"
            result["reason"] = "You were @mentioned in a comment — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = "You were @mentioned in a comment — suppressed by preference"
        return result

    # Check if you authored the PR/issue
    if _is_me(item_author):
        result["pref_key"] = "comment_on_your_pr"
        if prefs["comment_on_your_pr"]:
            result["decision"] = "allow"
            result["reason"] = "Comment on your PR/issue — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = "Comment on your PR/issue — suppressed by preference"
        return result

    result["reason"] = "Comment on someone else's PR/issue, not @mentioned"
    return result


def _eval_pr_closed(payload, prefs, result):
    pr = payload.get("pull_request", {})
    merged = pr.get("merged", False)
    pr_author = pr.get("user", {}).get("login", "")

    if merged and _is_me(pr_author):
        result["pref_key"] = "pr_merged"
        if prefs["pr_merged"]:
            result["decision"] = "allow"
            result["reason"] = "Your PR was merged — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = "Your PR was merged — suppressed by preference"
        return result

    result["reason"] = "PR closed (not a merge of your PR)"
    return result


def _eval_assigned(payload, prefs, result):
    assignee = payload.get("assignee", {})

    if _is_me(assignee.get("login")):
        result["pref_key"] = "assigned"
        if prefs["assigned"]:
            result["decision"] = "allow"
            result["reason"] = "You were assigned — allowed by preference"
        else:
            result["decision"] = "suppress"
            result["reason"] = "You were assigned — suppressed by preference"
        return result

    result["reason"] = "Someone else was assigned"
    return result


def evaluate_notification_for_dry_run(notification, prefs):
    """
    Evaluate a GitHub notification (from GET /notifications) against preferences.
    Used by the dry run page.

    Returns a dict with decision, reason, and pref_key.
    """
    subject = notification.get("subject", {})
    reason = notification.get("reason", "")
    repo = notification.get("repository", {})
    repo_full_name = repo.get("full_name", "")

    result = {
        "decision": "skip",
        "reason": "",
        "pref_key": None,
    }

    owner = repo.get("owner", {}).get("login", "")
    repo_name = repo.get("name", "")

    watched = get_watched_repo(owner, repo_name)
    if not watched:
        result["reason"] = f"Repo {repo_full_name} is not in watched repos"
        return result

    effective_prefs = resolve_preferences(watched)

    # Map GitHub notification reason to our preferences
    reason_map = {
        "review_requested": "review_requested_direct",
        "team_mention": "review_requested_team",
        "assign": "assigned",
        "mention": "mentioned",
        "comment": "comment_on_your_pr",
        "author": "comment_on_your_pr",
    }

    pref_key = reason_map.get(reason)
    if pref_key:
        result["pref_key"] = pref_key
        if effective_prefs.get(pref_key, True):
            result["decision"] = "allow"
            result["reason"] = f"Notification reason '{reason}' → {pref_key} is ON"
        else:
            result["decision"] = "suppress"
            result["reason"] = f"Notification reason '{reason}' → {pref_key} is OFF"
        return result

    result["reason"] = f"Notification reason '{reason}' has no matching preference rule"
    return result
