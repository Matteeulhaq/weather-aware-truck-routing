from django.http import JsonResponse


def health(request):
    """Liveness probe used by Render's health check."""
    return JsonResponse({"status": "ok"})
