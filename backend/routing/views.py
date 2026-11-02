import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import PlanRequestSerializer
from .services import ors
from .services.ors import RateLimitError, UpstreamError
from .services.planner import plan_trip

logger = logging.getLogger("routing")


def health(request):
    """Liveness probe used by Render's health check."""
    return JsonResponse({"status": "ok"})


def upstream_response(exc: Exception) -> Response:
    """Map upstream failures to friendly status codes."""
    if isinstance(exc, RateLimitError):
        return Response({"detail": str(exc)}, status=429)
    return Response({"detail": str(exc)}, status=502)


@api_view(["GET"])
def geocode(request):
    """Autocomplete proxy — keeps the ORS key server-side."""
    text = (request.query_params.get("text") or "").strip()
    if len(text) < 2:
        return Response({"results": []})

    try:
        results = ors.geocode(text)
    except UpstreamError as exc:
        return upstream_response(exc)
    return Response({"results": results})


@api_view(["POST"])
def plan(request):
    """Full weather-aware route analysis for one trip."""
    serializer = PlanRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        result = plan_trip(
            origin=data["origin"],
            destination=data["destination"],
            departure_epoch=int(data["departure_time"].timestamp()),
            load_lbs=data["load_weight_lbs"],
            interval_miles=data["sample_interval_miles"],
        )
    except LookupError as exc:
        return Response({"detail": str(exc)}, status=400)
    except UpstreamError as exc:
        return upstream_response(exc)
    return Response(result)
