from django.conf import settings


def tenant(request):
    """Expose tenant context (cafe, base domain, host flags) to all templates."""
    return {
        "cafe": getattr(request, "cafe", None),
        "base_domain": getattr(settings, "KUBA_BASE_DOMAIN", "kuba.com"),
        "admin_subdomain": getattr(settings, "KUBA_ADMIN_SUBDOMAIN", "admin"),
        "is_admin_host": getattr(request, "is_admin_host", False),
        "is_root_host": getattr(request, "is_root_host", False),
    }
