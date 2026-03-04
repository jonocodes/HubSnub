import logging

from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path

from . import cache
from .github_client import fetch_notifications
from .models import NotificationLog, NotificationPreferences, RepoOverride, WatchedRepo
from .rules import evaluate_notification_for_dry_run

logger = logging.getLogger(__name__)


# --- NotificationPreferences (singleton) ---


@admin.register(NotificationPreferences)
class NotificationPreferencesAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Review",
            {
                "fields": ("review_requested_direct", "review_requested_team"),
            },
        ),
        (
            "Activity",
            {
                "fields": (
                    "pr_approved_or_changes",
                    "assigned",
                    "comment_on_your_pr",
                    "mentioned",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": ("pr_merged", "pr_failed_checks"),
            },
        ),
        (
            "Suppression",
            {
                "fields": ("suppress_mode",),
            },
        ),
    )

    def has_add_permission(self, request):
        # Only allow one instance
        return not NotificationPreferences.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# --- WatchedRepo + RepoOverride inline ---


class RepoOverrideInline(admin.StackedInline):
    model = RepoOverride
    extra = 0
    fieldsets = (
        (
            "Override Preferences (leave blank to inherit global defaults)",
            {
                "fields": (
                    "review_requested_direct",
                    "review_requested_team",
                    "pr_approved_or_changes",
                    "assigned",
                    "comment_on_your_pr",
                    "mentioned",
                    "pr_merged",
                    "pr_failed_checks",
                    "suppress_mode",
                ),
            },
        ),
    )


@admin.register(WatchedRepo)
class WatchedRepoAdmin(admin.ModelAdmin):
    list_display = ("owner", "repo", "is_active")
    list_filter = ("is_active",)
    search_fields = ("owner", "repo")
    inlines = [RepoOverrideInline]


# --- NotificationLog (read-only) ---


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "repo",
        "thread_number",
        "event_type",
        "action_taken",
        "github_link",
    )
    list_filter = ("action_taken", "event_type")
    search_fields = ("repo", "detail")
    readonly_fields = (
        "repo",
        "thread_number",
        "event_type",
        "action_taken",
        "detail",
        "github_url",
        "created_at",
    )
    ordering = ("-created_at",)

    def github_link(self, obj):
        if obj.github_url:
            from django.utils.html import format_html

            return format_html('<a href="{}" target="_blank">View on GitHub</a>', obj.github_url)
        return "-"

    github_link.short_description = "GitHub"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# --- Custom Admin Site with Dry Run and Cache Viewer ---


class HubSnubAdminSite(admin.AdminSite):
    site_header = "HubSnub Administration"
    site_title = "HubSnub"
    index_title = "Notification Management"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("dry-run/", self.admin_view(self.dry_run_view), name="dry_run"),
            path("cache-viewer/", self.admin_view(self.cache_viewer_view), name="cache_viewer"),
            path("cache-viewer/clear/", self.admin_view(self.cache_clear_view), name="cache_clear"),
        ]
        return custom_urls + urls

    def dry_run_view(self, request):
        notifications = []
        error = None

        if request.method == "POST" or request.GET.get("fetch"):
            try:
                raw_notifications = fetch_notifications()
                prefs = NotificationPreferences.load()

                for n in raw_notifications:
                    subject = n.get("subject", {})
                    repo = n.get("repository", {})
                    repo_full_name = repo.get("full_name", "")
                    subject_url = subject.get("url", "")

                    # Extract PR/issue number from API URL
                    number = ""
                    if subject_url:
                        number = subject_url.rstrip("/").split("/")[-1]

                    # Build GitHub URL
                    subject_type = subject.get("type", "")
                    if subject_type == "PullRequest" and number:
                        github_url = f"https://github.com/{repo_full_name}/pull/{number}"
                    elif number:
                        github_url = f"https://github.com/{repo_full_name}/issues/{number}"
                    else:
                        github_url = f"https://github.com/{repo_full_name}"

                    verdict = evaluate_notification_for_dry_run(n, prefs)

                    notifications.append({
                        "repo": repo_full_name,
                        "number": number,
                        "title": subject.get("title", ""),
                        "reason": n.get("reason", ""),
                        "type": subject_type,
                        "github_url": github_url,
                        "decision": verdict["decision"],
                        "verdict_reason": verdict["reason"],
                    })
            except Exception as e:
                logger.exception("Dry run fetch failed")
                error = str(e)

        context = {
            **self.each_context(request),
            "title": "Dry Run",
            "notifications": notifications,
            "error": error,
        }
        return TemplateResponse(request, "admin/dry_run.html", context)

    def cache_viewer_view(self, request):
        entries = []
        for key, thread_id in cache.items():
            # key format: "owner/repo:number"
            parts = key.split(":")
            repo_full_name = parts[0] if parts else ""
            number = parts[1] if len(parts) > 1 else ""
            github_url = ""
            if repo_full_name and number:
                github_url = f"https://github.com/{repo_full_name}/pull/{number}"
            entries.append({
                "key": key,
                "thread_id": thread_id,
                "github_url": github_url,
            })

        context = {
            **self.each_context(request),
            "title": "Cache Viewer",
            "entries": entries,
            "cache_size": cache.size(),
            "max_size": cache.max_size(),
        }
        return TemplateResponse(request, "admin/cache_viewer.html", context)

    def cache_clear_view(self, request):
        if request.method == "POST":
            cache.clear()
        from django.shortcuts import redirect

        return redirect("admin:cache_viewer")


# Create custom admin site instance
hubsnub_admin = HubSnubAdminSite(name="admin")

# Re-register models on custom admin site
hubsnub_admin.register(NotificationPreferences, NotificationPreferencesAdmin)
hubsnub_admin.register(WatchedRepo, WatchedRepoAdmin)
hubsnub_admin.register(NotificationLog, NotificationLogAdmin)

# Register Django's auth models
from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import UserAdmin, GroupAdmin

hubsnub_admin.register(User, UserAdmin)
hubsnub_admin.register(Group, GroupAdmin)
