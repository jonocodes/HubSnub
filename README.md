# HubSnub

A Django-based GitHub App for intelligent notification filtering. HubSnub listens to GitHub webhooks, evaluates your notification preferences, and unsubscribes you from threads you don't care about — like team-only review requests when you weren't personally asked.

## Problem

GitHub's email notifications lack the granularity of the Slack integration. There's no way to distinguish between "your review was personally requested" and "a team you're on was requested." This creates noise for developers on teams auto-assigned via CODEOWNERS.

## How It Works

1. GitHub sends webhook events to HubSnub
2. HubSnub evaluates each event against your preferences
3. If the event is low-priority (e.g., team-only review request), HubSnub unsubscribes you from that thread
4. GitHub's own email system handles all delivery — HubSnub only controls what you're subscribed to

## Setup

### Prerequisites

- Python 3.10+
- A GitHub account
- A server with a public HTTPS endpoint (for webhook delivery)

### Installation

```bash
git clone https://github.com/jonocodes/HubSnub.git
cd HubSnub
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Environment Variables

| Variable | Description |
|---|---|
| `GITHUB_APP_ID` | GitHub App ID |
| `GITHUB_WEBHOOK_SECRET` | Secret for verifying webhook signatures |
| `GITHUB_PRIVATE_KEY_PATH` | Path to GitHub App private key `.pem` file |
| `GITHUB_PAT` | Personal Access Token with `notifications` scope |
| `GITHUB_USERNAME` | Your GitHub login (e.g., `jonocodes`) |
| `DJANGO_SECRET_KEY` | Django secret key |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hosts |

### Register a GitHub App

1. Go to **Settings → Developer settings → GitHub Apps → New GitHub App**
2. Set the webhook URL to `https://your-domain.com/webhooks/github/`
3. Generate a webhook secret and add it to your `.env`
4. Set permissions:
   - **Pull requests**: Read
   - **Issues**: Read
   - **Metadata**: Read
5. Subscribe to events:
   - `pull_request`
   - `pull_request_review`
   - `pull_request_review_comment`
   - `issue_comment`
   - `issues`
6. Generate a private key, download the `.pem` file, and set `GITHUB_PRIVATE_KEY_PATH`
7. Install the app on your organization/repos

### Create a Personal Access Token

HubSnub needs a PAT with the `notifications` scope to manage your thread subscriptions (GitHub App tokens can't do this).

1. Go to **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Create a token with the `notifications` scope
3. Add it to your `.env` as `GITHUB_PAT`

## Required GitHub Notification Settings

### GitHub Settings → Notifications

Email notifications must be enabled. HubSnub controls your thread subscriptions — GitHub sends emails based on those.

At `github.com/settings/notifications`:

- **Participating:** Email ✅
- **Watching:** Email ✅

### Team Notification Settings

Do **NOT** disable team notifications at the org/team level. HubSnub needs the webhook events that team review requests generate.

- At `github.com/orgs/{org}/teams/{team}/settings` → Team notifications → keep **Enabled**
- Code review settings → do **NOT** enable "Only notify requested team members" (let HubSnub handle the filtering)

### Watched Repositories

Watch repos normally. HubSnub filters noise from repos in your Watched Repos list. Repos not managed by HubSnub behave as usual.

## Admin UI

Access the admin at `/admin/` to:

- **Notification Preferences** — configure which notification types to allow or suppress
- **Watched Repos** — manage which repos HubSnub filters, with optional per-repo overrides
- **Notification Log** — view a log of every webhook event and what HubSnub decided
- **Dry Run** — preview what HubSnub would do with your current notifications (no actions taken)
- **Cache Viewer** — inspect the in-memory thread ID cache

## Deployment

```bash
pip install gunicorn
gunicorn hubsnub.wsgi:application --bind 0.0.0.0:8000
```

Use nginx or Caddy as a reverse proxy to provide HTTPS.

## Running Tests

```bash
python manage.py test notifications
```
