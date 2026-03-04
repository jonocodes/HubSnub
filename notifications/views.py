import json
import logging

from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .webhook_handler import handle_webhook, verify_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def github_webhook(request):
    """Receive and process GitHub webhook events."""
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")

    if not verify_signature(request.body, signature):
        logger.warning("Invalid webhook signature")
        return HttpResponseForbidden("Invalid signature")

    if event_type == "ping":
        return JsonResponse({"status": "pong"})

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse("Invalid JSON", status=400)

    result = handle_webhook(event_type, payload)

    return JsonResponse({
        "status": "processed",
        "decision": result["decision"],
        "reason": result["reason"],
    })
