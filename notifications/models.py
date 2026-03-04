from django.db import models


SUPPRESS_MODE_CHOICES = [
    ("unsubscribe", "Unsubscribe"),
    ("ignore", "Ignore (hard mute)"),
]

ACTION_CHOICES = [
    ("allow", "Allow"),
    ("suppress", "Suppress"),
    ("skip", "Skip"),
]


class NotificationPreferences(models.Model):
    """Singleton model for global notification preferences."""

    review_requested_direct = models.BooleanField(
        default=True,
        help_text="Your PR review is requested personally",
    )
    review_requested_team = models.BooleanField(
        default=False,
        help_text="Review requests to a team you're on",
    )
    pr_approved_or_changes = models.BooleanField(
        default=True,
        help_text="Approval/changes requested on PRs you authored",
    )
    assigned = models.BooleanField(
        default=True,
        help_text="You are assigned to a PR or issue",
    )
    comment_on_your_pr = models.BooleanField(
        default=True,
        help_text="Comments on PRs you authored",
    )
    mentioned = models.BooleanField(
        default=True,
        help_text="Direct @mentions",
    )
    pr_merged = models.BooleanField(
        default=False,
        help_text="Merge notifications for your PRs",
    )
    pr_failed_checks = models.BooleanField(
        default=False,
        help_text="CI failure notifications",
    )
    suppress_mode = models.CharField(
        max_length=20,
        choices=SUPPRESS_MODE_CHOICES,
        default="unsubscribe",
        help_text="How to suppress: unsubscribe (can be re-subscribed) or ignore (hard mute)",
    )

    class Meta:
        verbose_name = "Notification Preferences"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return "Global Notification Preferences"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class WatchedRepo(models.Model):
    """Which orgs/repos the app manages."""

    owner = models.CharField(
        max_length=255,
        help_text="Org or user name",
    )
    repo = models.CharField(
        max_length=255,
        help_text="Repo name, or * for all repos in that org",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether filtering is enabled for this repo",
    )

    class Meta:
        verbose_name = "Watched Repo"
        verbose_name_plural = "Watched Repos"
        unique_together = ("owner", "repo")

    def __str__(self):
        return f"{self.owner}/{self.repo}"


class RepoOverride(models.Model):
    """Per-repo overrides of notification preferences. Null means inherit from global."""

    watched_repo = models.OneToOneField(
        WatchedRepo,
        on_delete=models.CASCADE,
        related_name="override",
    )
    review_requested_direct = models.BooleanField(null=True, blank=True, default=None)
    review_requested_team = models.BooleanField(null=True, blank=True, default=None)
    pr_approved_or_changes = models.BooleanField(null=True, blank=True, default=None)
    assigned = models.BooleanField(null=True, blank=True, default=None)
    comment_on_your_pr = models.BooleanField(null=True, blank=True, default=None)
    mentioned = models.BooleanField(null=True, blank=True, default=None)
    pr_merged = models.BooleanField(null=True, blank=True, default=None)
    pr_failed_checks = models.BooleanField(null=True, blank=True, default=None)
    suppress_mode = models.CharField(
        max_length=20,
        choices=SUPPRESS_MODE_CHOICES,
        null=True,
        blank=True,
        default=None,
        help_text="Null = use global default",
    )

    class Meta:
        verbose_name = "Repo Override"
        verbose_name_plural = "Repo Overrides"

    def __str__(self):
        return f"Override for {self.watched_repo}"


class NotificationLog(models.Model):
    """Webhook event log. Auto-populated, read-only."""

    repo = models.CharField(max_length=512, help_text="Full repo name (owner/repo)")
    thread_number = models.IntegerField(help_text="PR or issue number")
    event_type = models.CharField(
        max_length=100,
        help_text="e.g., review_requested, mentioned",
    )
    action_taken = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text="allow, suppress, or skip",
    )
    detail = models.TextField(
        blank=True,
        help_text="Human-readable reason for the decision",
    )
    github_url = models.URLField(
        blank=True,
        help_text="Link to the PR/issue on GitHub",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.repo}#{self.thread_number} — {self.event_type} → {self.action_taken}"
