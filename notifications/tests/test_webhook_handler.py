import hashlib
import hmac
import json

from django.test import TestCase, override_settings

from notifications.models import NotificationLog, NotificationPreferences, WatchedRepo
from notifications.webhook_handler import verify_signature


@override_settings(GITHUB_WEBHOOK_SECRET="test-secret")
class TestVerifySignature(TestCase):
    def test_valid_signature(self):
        body = b'{"test": true}'
        sig = "sha256=" + hmac.new(
            b"test-secret", body, hashlib.sha256
        ).hexdigest()
        self.assertTrue(verify_signature(body, sig))

    def test_invalid_signature(self):
        body = b'{"test": true}'
        self.assertFalse(verify_signature(body, "sha256=invalid"))

    def test_missing_signature(self):
        self.assertFalse(verify_signature(b"body", ""))


@override_settings(GITHUB_WEBHOOK_SECRET="test-secret", GITHUB_USERNAME="testuser")
class TestWebhookEndpoint(TestCase):
    def setUp(self):
        NotificationPreferences.load()
        WatchedRepo.objects.create(owner="myorg", repo="myrepo", is_active=True)

    def _sign(self, body):
        return "sha256=" + hmac.new(
            b"test-secret", body, hashlib.sha256
        ).hexdigest()

    def test_ping_event(self):
        body = b'{"zen": "test"}'
        resp = self.client.post(
            "/webhooks/github/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._sign(body),
            HTTP_X_GITHUB_EVENT="ping",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "pong")

    def test_invalid_signature_rejected(self):
        body = b'{"action": "opened"}'
        resp = self.client.post(
            "/webhooks/github/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=bad",
            HTTP_X_GITHUB_EVENT="pull_request",
        )
        self.assertEqual(resp.status_code, 403)

    def test_webhook_creates_log(self):
        payload = {
            "action": "review_requested",
            "requested_team": {"name": "backend", "slug": "backend"},
            "pull_request": {"number": 42, "user": {"login": "author"}},
            "repository": {
                "full_name": "myorg/myrepo",
                "name": "myrepo",
                "owner": {"login": "myorg"},
            },
        }
        body = json.dumps(payload).encode()
        resp = self.client.post(
            "/webhooks/github/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._sign(body),
            HTTP_X_GITHUB_EVENT="pull_request",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["decision"], "suppress")

        log = NotificationLog.objects.first()
        self.assertIsNotNone(log)
        self.assertEqual(log.repo, "myorg/myrepo")
        self.assertEqual(log.thread_number, 42)
        self.assertEqual(log.action_taken, "suppress")
