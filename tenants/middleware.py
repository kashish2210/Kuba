from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotFound


def _admin_subdomain():
    return getattr(settings, "KUBA_ADMIN_SUBDOMAIN", "admin")


def _known_bases():
    # Recognise both the configured production base and localhost for dev.
    return [getattr(settings, "KUBA_BASE_DOMAIN", "kuba.com").lower(), "localhost"]


def split_host(hostname):
    """Return (subdomain, matched_base). subdomain is '' for a bare/base host.

    matched_base is None when the host is not under any known base (e.g. a fully
    external custom domain or a raw IP).
    """
    hostname = (hostname or "").lower()
    if hostname in {"127.0.0.1", "0.0.0.0", "[::1]", "localhost"}:
        return "", "localhost"
    for base in _known_bases():
        if hostname == base or hostname == f"www.{base}":
            return "", base
        suffix = f".{base}"
        if hostname.endswith(suffix):
            label = hostname[: -len(suffix)]
            return label.split(".")[0], base
    return "", None


class TenantMiddleware:
    """Resolve the request host to a Cafe and attach context to the request.

    Sets ``request.cafe`` (Cafe or None), ``request.is_admin_host`` (the Django
    admin subdomain), and ``request.is_root_host`` (the public/marketing host).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.cafe = None
        request.is_admin_host = False
        request.is_root_host = False

        hostname = request.get_host().split(":")[0]
        subdomain, base = split_host(hostname)

        if subdomain == _admin_subdomain():
            request.is_admin_host = True
            return self.get_response(request)

        if subdomain in ("", "www"):
            if base is not None:
                request.is_root_host = True
                return self.get_response(request)
            # Unknown host — maybe a fully external custom domain.
            from .models import Cafe

            cafe = Cafe.objects.filter(custom_domain=hostname, is_active=True).first()
            if cafe:
                request.cafe = cafe
                return self.get_response(request)
            request.is_root_host = True
            return self.get_response(request)

        # A real cafe subdomain.
        from .models import Cafe

        cafe = Cafe.objects.filter(subdomain=subdomain, is_active=True).first()
        if cafe is None:
            return HttpResponseNotFound(
                "<h1>Cafe not found</h1>"
                f"<p>No active cafe is registered at <code>{hostname}</code>.</p>"
            )
        request.cafe = cafe
        return self.get_response(request)


class AdminAccessMiddleware:
    """Restrict the Django admin to superusers, and (in production) to the admin host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            # In production the admin lives only on admin.<base>. Locally (DEBUG)
            # it is reachable on any host so plain localhost works.
            if not settings.DEBUG and not getattr(request, "is_admin_host", False):
                return HttpResponseNotFound("Not found")
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and not user.is_superuser:
                raise PermissionDenied("Only platform administrators can access this area.")
        return self.get_response(request)
