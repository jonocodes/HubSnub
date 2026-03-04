# HubSnub — Project Plan

## Problem

GitHub's email notifications lack the granularity of the Slack integration. Specifically, there's no way to distinguish between "your review was personally requested" and "a team you're on was requested." This creates noise for developers on teams that are auto-assigned via CODEOWNERS. The Slack integration has separate toggles for these, but email and the Notifications API do not. No existing tool solves this.

## Solution

A Django-based GitHub App that listens to webhooks, evaluates user-defined notification preferences, and toggles thread subscriptions via the GitHub API. When a low-priority event occurs (e.g., a team-only review request), the app unsubscribes the user from that thread. GitHub's own email system handles all delivery — the app only controls what you're subscribed to.

## Architecture

```
GitHub ──webhook──▶ Django App ──API call──▶ GitHub (subscribe/unsubscribe)
                        │
                     SQLite
                     (prefs, watched repos, logs)
                        │
                   Django Admin
                   (configuration + dry run + cache viewer)
```

Single Django process. No IMAP. No second process. No email parsing. The app is stateless with respect to thread participation — GitHub handles re-subscribing you when you comment, get @mentioned, or are directly requested as a reviewer.

## Key Insight

The `pull_request` webhook with `action: review_requested` includes either a `requested_reviewer` object (specific user) OR a `requested_team` object. This gives us the team-vs-personal distinction that email headers and the Notifications API lack. The Slack integration uses internal GitHub APIs for this; we get it from webhooks.

## Subscription Strategy

- Default suppress mode: `subscribed: false` (unsubscribe). GitHub will automatically re-subscribe you if someone @mentions you, requests your review directly, or you comment on the thread.
- Optional hard mute mode: `ignored: true`. Nothing re-subscribes you. Configurable per-repo.
- One "leaked" email per suppressed thread is expected (GitHub sends the email before the webhook arrives). Acceptable for Phase 1; IMAP cleanup is a Phase 2 option.

---

## Tech Stack

- **Python / Django** — web server, admin UI, ORM
- **SQLite** — database
- **PyGithub** — GitHub REST API client (subscribe/unsubscribe, fetch PR details, fetch notifications)
- **GitHub App** — webhook delivery + API authentication via installation tokens

## Credentials / Config (env vars)

| Variable | Description |
|---|---|
| `GITHUB_APP_ID` | GitHub App ID |
| `GITHUB_WEBHOOK_SECRET` | Secret for verifying webhook signatures |
| `GITHUB_PRIVATE_KEY_PATH` | Path to GitHub App private key `.pem` file |
| `GITHUB_PAT` | Personal Access Token with `notifications` scope (for subscribe/unsubscribe) |
| `GITHUB_USERNAME` | Your GitHub login (e.g., `jonocodes`) |
| `DJANGO_SECRET_KEY` | Django secret key |
| `ALLOWED_HOSTS` | Django allowed hosts |

---

## Database Schema

### `NotificationPreferences` (singleton — one row)

Global notification preferences, modeled after the GitHub Slack integration toggles.

| Field | Type | Default | Description |
|---|---|---|---|
| review_requested_direct | bool | True | Your PR review is requested personally |
| review_requested_team | bool | False | Review requests to a team you're on |
| pr_approved_or_changes | bool | True | Approval/changes requested on PRs you authored |
| assigned | bool | True | You are assigned to a PR |
| comment_on_your_pr | bool | True | Comments on PRs you authored |
| mentioned | bool | True | Direct @mentions |
| pr_merged | bool | False | Merge notifications for your PRs |
| pr_failed_checks | bool | False | CI failure notifications |
| suppress_mode | choice | `unsubscribe` | `unsubscribe` or `ignore` |

### `WatchedRepo`

Which orgs/repos the app manages. Only repos listed here are processed.

| Field | Type | Description |
|---|---|---|
| owner | string | Org or user name |
| repo | string | Repo name, or `*` for all repos in that org |
| is_active | bool | Whether filtering is enabled |

### `RepoOverride`

Per-repo overrides of any notification preference. Nullable fields — null means inherit from global.

| Field | Type | Description |
|---|---|---|
| watched_repo | FK | Link to WatchedRepo |
| (same boolean fields as NotificationPreferences) | bool/null | Null = use global default |
| suppress_mode | choice/null | Null = use global default |

### `NotificationLog`

Webhook event log. Auto-populated, read-only in admin.

| Field | Type | Description |
|---|---|---|
| repo | string | Full repo name |
| thread_number | int | PR or issue number |
| event_type | string | e.g., `review_requested`, `mentioned` |
| action_taken | string | `allow`, `suppress`, or `skip` |
| detail | text | Human-readable reason for the decision |
| github_url | url | Link to the PR/issue on GitHub |
| created_at | datetime | Timestamp |

---

## GitHub App Setup

### Permissions

| Permission | Access | Why |
|---|---|---|
| Pull requests | Read | Inspect `requested_reviewers` vs `requested_teams` |
| Issues | Read | Inspect assignments and mentions |
| Metadata | Read | Required for all GitHub Apps |

Note: Thread subscription management uses the user's PAT via the Notifications API, not the App installation token.

### Webhook Events

- `pull_request` — opened, closed, merged, assigned, review_requested
- `pull_request_review` — submitted, dismissed
- `pull_request_review_comment` — created
- `issue_comment` — created
- `issues` — opened, closed, assigned

---

## Webhook Processing Flow

The app is stateless with respect to thread participation. GitHub handles re-subscribing you when you comment, get @mentioned, or are directly requested. The app only unsubscribes you from things you don't care about.

```
1. Receive POST at /webhooks/github/
2. Verify HMAC signature using GITHUB_WEBHOOK_SECRET
3. Parse event type + action from headers and payload
4. Extract repo name — check if it's in WatchedRepos (active). If not → skip.
5. Resolve effective preferences (global + repo override)
6. Evaluate the event against preferences using only the webhook payload:
   a. pull_request.review_requested:
      - If requested_reviewer.login == GITHUB_USERNAME → check review_requested_direct pref
      - If only requested_team → check review_requested_team pref
   b. pull_request_review.submitted:
      - If you are the PR author (payload.pull_request.user.login) → check pr_approved_or_changes pref
   c. issue_comment.created / pull_request_review_comment.created:
      - If you are the PR/issue author → check comment_on_your_pr pref
      - If you are @mentioned in body → check mentioned pref
   d. pull_request.closed (merged):
      - Check pr_merged pref
   e. pull_request.assigned / issues.assigned:
      - If assigned to you → check assigned pref
   f. Any event where you are @mentioned in body:
      - Check mentioned pref
7. If the preference is OFF:
      - Check in-memory cache for thread ID (key: repo:thread_number)
      - On cache miss: call GET /notifications to find the matching thread ID, store in cache
      - Call PUT /notifications/threads/{id}/subscription with subscribed: false (or ignored: true per suppress_mode)
8. If the preference is ON → do nothing (already subscribed via GitHub's default behavior)
9. Log to NotificationLog (include github_url for the PR/issue)
```

---

## Thread ID Cache

An in-memory LRU dict that maps `repo:thread_number` → GitHub notification thread ID. Avoids repeat API lookups.

- Keyed by `"{owner}/{repo}:{number}"` (e.g., `"terradot/infra:423"`)
- Capped at ~1000 entries, evicts oldest on overflow
- Lost on process restart (acceptable — it's just an optimization)
- Viewable via a custom admin page (read-only table showing current cache contents with links to the corresponding PRs/issues on GitHub)

---

## Django Admin Configuration

### Registered Models

**NotificationPreferences** — singleton, editable. Fieldsets grouping the toggles logically (Review, Activity, Status). Uses `django-solo` or custom save logic to enforce single row.

**WatchedRepo** — list view with search by owner/repo, filter by is_active. Add/edit/delete.

**RepoOverride** — inline on WatchedRepo detail page, or standalone with FK selector. Only shows fields that differ from global defaults.

**NotificationLog** — read-only list. Search by repo. Filter by action_taken, event_type. Most recent first. Each row includes a clickable link to the PR/issue on GitHub. Shows what the app is doing and why.

### Custom Admin Views

**Dry Run** — a custom admin page accessible from the admin sidebar. Fetches current notifications from `GET /notifications` using the PAT. For each notification:
- Displays: repo, PR/issue number, title, reason, sender (with link to the PR/issue on GitHub)
- Runs it through the rules engine using current preferences
- Shows the verdict: `allow`, `suppress`, or `skip`, with the reason
- No action is taken — purely read-only
- Includes a button to re-fetch / refresh
- Useful for testing and tuning preferences before enabling live webhook processing

**Cache Viewer** — a custom admin page showing the current contents of the in-memory thread ID cache.
- Displays: cache key (`repo:thread_number`), GitHub thread ID, and a clickable link to the PR/issue on GitHub
- Shows current cache size vs max size
- Includes a button to clear the cache
- Read-only (cache is only populated by the webhook handler)

---

## Links and URLs

Throughout the admin, PRs and issues should link directly to GitHub for easy navigation:
- `NotificationLog` entries include `github_url` linking to the PR/issue
- `Dry Run` results include clickable links to each notification's PR/issue
- `Cache Viewer` entries include clickable links to the PR/issue
- URL format: `https://github.com/{owner}/{repo}/pull/{number}` or `https://github.com/{owner}/{repo}/issues/{number}`

---

## README — Required GitHub Notification Settings

The README should include a section explaining what GitHub notification settings the user needs to configure for HubSnub to work correctly. Specifically:

### GitHub Settings → Notifications

**Email notifications must be enabled.** HubSnub doesn't send emails — it controls your GitHub thread subscriptions, and GitHub sends emails based on those subscriptions. So email delivery must be turned on.

Recommended settings at `github.com/settings/notifications`:

- **Participating:** Email ✅ — so you get emails for threads you're subscribed to
- **Watching:** Email ✅ — so you get emails when activity happens on watched repos (HubSnub will unsubscribe you from the ones you don't care about)

### GitHub Settings → Notification Routing (optional)

If you want GitHub notifications for specific orgs to go to a specific email address, configure that under "Custom routing" in notification settings. HubSnub doesn't affect which email address receives notifications — it only controls whether you're subscribed to a thread.

### Team Notification Settings

Do NOT disable team notifications at the org/team level. HubSnub needs to receive the webhook events that team mentions and team review requests generate. If you disable team notifications at the GitHub level, HubSnub won't see those events and can't filter them.

Specifically:
- At `github.com/orgs/{org}/teams/{team}/settings` → Team notifications → keep **Enabled**
- Code review settings → do NOT enable "Only notify requested team members" (this conflicts with HubSnub's approach — let HubSnub handle the filtering instead)

### Watched Repositories

You can watch repos normally. HubSnub will filter the noise from watched repos that are in your `WatchedRepo` list. For repos not managed by HubSnub, notifications behave as usual.

---

## Implementation Phases

### Phase 1: Core (MVP)

1. **Django project scaffolding** — project, app, settings, models, migrations, admin
2. **GitHub API client** — authenticate with PAT, fetch notifications, look up thread details, subscribe/unsubscribe
3. **Preference evaluation engine** — resolve global + override preferences, classify events
4. **Dry Run page** — custom admin view that fetches current notifications, runs them through the rules engine, and displays what would be allowed/suppressed. Build this first as a safe way to test and tune preferences before going live.
5. **Webhook endpoint** — receive, verify signature, parse events, dispatch to rules engine
6. **Subscription toggling** — look up notification thread ID (with in-memory cache), call GitHub API to unsubscribe
7. **Notification logging** — log every decision with GitHub links
8. **Cache viewer** — custom admin page showing in-memory cache contents
9. **Admin UI** — register all models, configure fieldsets, add custom views to sidebar
10. **README** — setup instructions, required GitHub settings, GitHub App registration guide
11. **Deployment** — gunicorn + nginx/caddy, HTTPS, GitHub App registration

### Phase 2: Polish

- IMAP cleanup layer for the one leaked email per suppressed thread
- Better admin dashboard (summary stats, charts of allow/suppress ratios over time)
- Dry-run mode toggle (process webhooks but log without actually unsubscribing)
- Bot filtering (suppress notifications from specific bot accounts like Dependabot, CodeRabbit)

### Phase 3: Scale

- Multi-user support (user model, GitHub OAuth, per-user preferences)
- Retroactive merge cleanup via IMAP (delete/archive old emails for merged PRs)
- IMAP IDLE listener as alternative to polling
- Webhook replay/backfill for missed events

---

## Resolved Questions

1. **PAT for Notifications API**: A Personal Access Token with `notifications` scope is required for subscribe/unsubscribe calls, since GitHub App installation tokens can't manage user notification subscriptions. Stored as `GITHUB_PAT` env var.

2. **Finding the notification thread ID**: After each suppress-worthy webhook, call `GET /notifications` filtered by repo to find the matching thread by subject/PR number. Results are cached in an in-memory LRU dict (keyed by `repo:thread_number`, capped at ~1000 entries) to avoid repeat lookups. Cache is lost on process restart, which is fine — it's just an optimization.

3. **Rate limits**: GitHub API rate limit is 5,000 requests/hour for authenticated users. For a single user on a moderately active org, this should be fine. Thread ID caching reduces repeat lookups.

---

## Hosting Requirements

- Public HTTPS endpoint for GitHub webhook delivery
- SQLite database (file-based, co-located with the app)
- Single process (gunicorn or similar)
- Minimal resources — a small VPS or even a free-tier cloud instance would work

---

## File Structure

```
hubsnub/
├── manage.py
├── requirements.txt
├── .env.example
├── README.md
├── hubsnub/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── notifications/
│   ├── models.py          # NotificationPreferences, WatchedRepo, RepoOverride, NotificationLog
│   ├── admin.py           # Admin configuration, custom views (dry run, cache viewer)
│   ├── views.py           # Webhook endpoint
│   ├── webhook_handler.py # Event parsing + dispatch
│   ├── rules.py           # Preference evaluation + decision logic
│   ├── github_client.py   # PyGithub wrapper: fetch notifications, subscribe/unsubscribe, PR details
│   ├── cache.py           # In-memory LRU thread ID cache
│   ├── urls.py            # App-level URL config
│   ├── migrations/
│   └── tests/
│       ├── test_rules.py
│       ├── test_webhook_handler.py
│       └── test_github_client.py
└── templates/
    └── admin/
        ├── dry_run.html       # Dry run results page
        └── cache_viewer.html  # Cache viewer page
```
