from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from notifications.github_client import find_thread_id, suppress_thread


@override_settings(GITHUB_PAT="fake-token")
class TestFindThreadId(TestCase):
    @patch("notifications.github_client.fetch_notifications")
    def test_finds_matching_thread(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": "thread-123",
                "subject": {
                    "title": "Fix bug",
                    "url": "https://api.github.com/repos/myorg/myrepo/pulls/42",
                    "type": "PullRequest",
                },
                "repository": {"full_name": "myorg/myrepo"},
            },
            {
                "id": "thread-456",
                "subject": {
                    "title": "Other PR",
                    "url": "https://api.github.com/repos/myorg/myrepo/pulls/99",
                    "type": "PullRequest",
                },
                "repository": {"full_name": "myorg/myrepo"},
            },
        ]
        result = find_thread_id("myorg/myrepo", 42)
        self.assertEqual(result, "thread-123")

    @patch("notifications.github_client.fetch_notifications")
    def test_returns_none_when_not_found(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": "thread-456",
                "subject": {
                    "title": "Other PR",
                    "url": "https://api.github.com/repos/myorg/myrepo/pulls/99",
                    "type": "PullRequest",
                },
                "repository": {"full_name": "myorg/myrepo"},
            },
        ]
        result = find_thread_id("myorg/myrepo", 42)
        self.assertIsNone(result)


@override_settings(GITHUB_PAT="fake-token")
class TestSuppressThread(TestCase):
    @patch("notifications.github_client.set_thread_subscription")
    def test_unsubscribe_mode(self, mock_set):
        mock_set.return_value = {"subscribed": False, "ignored": False}
        suppress_thread("thread-123", "unsubscribe")
        mock_set.assert_called_once_with("thread-123", subscribed=False, ignored=False)

    @patch("notifications.github_client.set_thread_subscription")
    def test_ignore_mode(self, mock_set):
        mock_set.return_value = {"subscribed": False, "ignored": True}
        suppress_thread("thread-123", "ignore")
        mock_set.assert_called_once_with("thread-123", subscribed=False, ignored=True)
