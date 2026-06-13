"""Subdomain validation/generation and audit logging helpers.

Imports of the ORM models are done lazily inside functions to avoid a circular
import with ``tenants.models`` (which imports ``generate_subdomain`` at module load).
"""
import re
import secrets

from django.conf import settings

# Reserved even if the ReservedSubdomain table is empty. ``admin`` is the Django
# admin host and must never be claimable by a cafe.
HARD_RESERVED = {
    "admin", "www", "api", "app", "static", "media", "mail", "smtp", "ftp",
    "kuba", "support", "help", "billing", "blog", "docs", "status", "cdn",
    "assets", "dashboard", "account", "accounts", "login", "signup", "register",
}

SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MIN_LEN = 3
MAX_LEN = 63


def normalize_subdomain(value):
    """Lowercase, trim, collapse to a DNS-safe label (no validation)."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:MAX_LEN]


def reserved_names():
    """HARD_RESERVED plus any ReservedSubdomain rows, plus the admin subdomain."""
    names = set(HARD_RESERVED)
    names.add(getattr(settings, "KUBA_ADMIN_SUBDOMAIN", "admin"))
    try:
        from .models import ReservedSubdomain

        names.update(ReservedSubdomain.objects.values_list("name", flat=True))
    except Exception:
        # Table may not exist yet (e.g. during initial migrate).
        pass
    return names


def validate_subdomain(value):
    """Return (ok, reason). Reason is a user-facing string when not ok."""
    norm = normalize_subdomain(value)
    if not norm:
        return False, "Please enter a subdomain."
    if len(norm) < MIN_LEN:
        return False, f"Too short — use at least {MIN_LEN} characters."
    if not SUBDOMAIN_RE.match(norm):
        return False, "Use only lowercase letters, numbers and hyphens."
    if norm in reserved_names():
        return False, "That subdomain is reserved."
    return True, ""


def is_subdomain_available(value, exclude_pk=None):
    """Return (available, reason). Validates format/reservation then checks the DB."""
    ok, reason = validate_subdomain(value)
    if not ok:
        return False, reason
    norm = normalize_subdomain(value)
    from .models import Cafe

    qs = Cafe.objects.filter(subdomain=norm)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        return False, "That subdomain is already taken."
    return True, "Available!"


def generate_subdomain(name=""):
    """Build an available subdomain from ``name`` (or random when unusable)."""
    base = normalize_subdomain(name)
    if len(base) < MIN_LEN or base in reserved_names():
        base = ""
    candidate = base or f"cafe-{secrets.token_hex(3)}"
    if is_subdomain_available(candidate)[0]:
        return candidate
    # Append short random suffixes until one is free.
    for _ in range(50):
        candidate = f"{(base or 'cafe')}-{secrets.token_hex(3)}"
        if is_subdomain_available(candidate)[0]:
            return candidate
    return f"cafe-{secrets.token_hex(6)}"


def client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(action, *, cafe=None, actor=None, request=None, target=None, message="", **metadata):
    """Write an AuditLog row. Never raises — auditing must not break the request."""
    try:
        from .models import AuditLog

        target_type = ""
        target_repr = ""
        if target is not None:
            target_type = target.__class__.__name__
            target_repr = str(target)[:255]
        if actor is None and request is not None and getattr(request, "user", None):
            if request.user.is_authenticated:
                actor = request.user
        return AuditLog.objects.create(
            cafe=cafe,
            actor=actor,
            action=action,
            target_type=target_type,
            target_repr=target_repr,
            message=message,
            metadata=metadata or {},
            ip_address=client_ip(request),
        )
    except Exception:
        return None
