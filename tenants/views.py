from django.http import JsonResponse

from .utils import is_subdomain_available, normalize_subdomain


def subdomain_available(request):
    """Public endpoint used by the signup page to check a desired subdomain."""
    value = request.GET.get("value", "")
    ok, reason = is_subdomain_available(value)
    return JsonResponse(
        {"available": ok, "reason": reason, "normalized": normalize_subdomain(value)}
    )
