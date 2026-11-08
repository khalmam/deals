from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """Render's health check: 200 only when the database answers."""
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"ok": False}, status=503)
    return JsonResponse({"ok": True})
