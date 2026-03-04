from django.test import TestCase, override_settings

from notifications.models import (
    NotificationPreferences,
    RepoOverride,
    WatchedRepo,
)
from notifications.rules import evaluate_event, get_watched_repo, resolve_preferences


@override_settings(GITHUB_USERNAME="testuser")
class TestGetWatchedRepo(TestCase):
    def test_exact_match(self):
        wr = WatchedRepo.objects.create(owner="myorg", repo="myrepo", is_active=True)
        self.assertEqual(get_watched_repo("myorg", "myrepo"), wr)

    def test_wildcard_match(self):
        wr = WatchedRepo.objects.create(owner="myorg", repo="*", is_active=True)
        self.assertEqual(get_watched_repo("myorg", "anyrepo"), wr)

    def test_inactive_not_matched(self):
        WatchedRepo.objects.create(owner="myorg", repo="myrepo", is_active=False)
        self.assertIsNone(get_watched_repo("myorg", "myrepo"))

    def test_no_match(self):
        self.assertIsNone(get_watched_repo("unknown", "repo"))


@override_settings(GITHUB_USERNAME="testuser")
class TestResolvePreferences(TestCase):
    def setUp(self):
        self.prefs = NotificationPreferences.load()
        self.wr = WatchedRepo.objects.create(owner="myorg", repo="myrepo", is_active=True)

    def test_global_defaults(self):
        result = resolve_preferences(self.wr)
        self.assertTrue(result["review_requested_direct"])
        self.assertFalse(result["review_requested_team"])
        self.assertEqual(result["suppress_mode"], "unsubscribe")

    def test_override_applied(self):
        RepoOverride.objects.create(
            watched_repo=self.wr,
            review_requested_team=True,
            suppress_mode="ignore",
        )
        result = resolve_preferences(self.wr)
        self.assertTrue(result["review_requested_team"])
        self.assertEqual(result["suppress_mode"], "ignore")
        # Non-overridden fields keep global values
        self.assertTrue(result["review_requested_direct"])


@override_settings(GITHUB_USERNAME="testuser")
class TestEvaluateEvent(TestCase):
    def setUp(self):
        NotificationPreferences.load()
        WatchedRepo.objects.create(owner="myorg", repo="myrepo", is_active=True)

    def _make_payload(self, **kwargs):
        payload = {
            "repository": {
                "full_name": "myorg/myrepo",
                "name": "myrepo",
                "owner": {"login": "myorg"},
            },
        }
        payload.update(kwargs)
        return payload

    def test_skip_unwatched_repo(self):
        payload = {
            "repository": {
                "full_name": "other/repo",
                "name": "repo",
                "owner": {"login": "other"},
            },
            "action": "review_requested",
        }
        result = evaluate_event("pull_request", "review_requested", payload)
        self.assertEqual(result["decision"], "skip")

    def test_direct_review_request_allowed(self):
        payload = self._make_payload(
            action="review_requested",
            requested_reviewer={"login": "testuser"},
            pull_request={"number": 42, "user": {"login": "author"}},
        )
        result = evaluate_event("pull_request", "review_requested", payload)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["pref_key"], "review_requested_direct")

    def test_team_review_request_suppressed(self):
        payload = self._make_payload(
            action="review_requested",
            requested_team={"name": "backend", "slug": "backend"},
            pull_request={"number": 42, "user": {"login": "author"}},
        )
        result = evaluate_event("pull_request", "review_requested", payload)
        self.assertEqual(result["decision"], "suppress")
        self.assertEqual(result["pref_key"], "review_requested_team")

    def test_review_submitted_on_your_pr(self):
        payload = self._make_payload(
            action="submitted",
            review={"state": "approved"},
            pull_request={"number": 42, "user": {"login": "testuser"}},
        )
        result = evaluate_event("pull_request_review", "submitted", payload)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["pref_key"], "pr_approved_or_changes")

    def test_comment_on_your_pr(self):
        payload = self._make_payload(
            action="created",
            issue={"number": 10, "user": {"login": "testuser"}},
            comment={"body": "Looks good!", "user": {"login": "other"}},
        )
        result = evaluate_event("issue_comment", "created", payload)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["pref_key"], "comment_on_your_pr")

    def test_mentioned_in_comment(self):
        payload = self._make_payload(
            action="created",
            issue={"number": 10, "user": {"login": "other"}},
            comment={"body": "Hey @testuser check this out", "user": {"login": "someone"}},
        )
        result = evaluate_event("issue_comment", "created", payload)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["pref_key"], "mentioned")

    def test_pr_merged_suppressed_by_default(self):
        payload = self._make_payload(
            action="closed",
            pull_request={
                "number": 42,
                "user": {"login": "testuser"},
                "merged": True,
            },
        )
        result = evaluate_event("pull_request", "closed", payload)
        self.assertEqual(result["decision"], "suppress")
        self.assertEqual(result["pref_key"], "pr_merged")

    def test_assigned_to_you(self):
        payload = self._make_payload(
            action="assigned",
            assignee={"login": "testuser"},
            pull_request={"number": 42, "user": {"login": "other"}},
        )
        result = evaluate_event("pull_request", "assigned", payload)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["pref_key"], "assigned")

    def test_assigned_to_someone_else(self):
        payload = self._make_payload(
            action="assigned",
            assignee={"login": "someone_else"},
            pull_request={"number": 42, "user": {"login": "other"}},
        )
        result = evaluate_event("pull_request", "assigned", payload)
        self.assertEqual(result["decision"], "skip")
