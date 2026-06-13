"""Access control for the per-cafe dashboard.

A dashboard page is only served on a cafe host (``request.cafe`` set) to a user
who is a member (admin) of that cafe. Superusers may access any cafe.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def cafe_admin_required(view_func=None, *, require_admin=True):
    def decorator(fn):
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            # The Django admin host is not a cafe area.
            if getattr(request, "is_admin_host", False):
                return redirect("/admin/")
            cafe = getattr(request, "cafe", None)
            if cafe is None or not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.is_superuser:
                profile = getattr(request.user, "profile", None)
                if profile is None or profile.cafe_id != cafe.id:
                    raise PermissionDenied("You don't have access to this cafe.")
                if require_admin and profile.role != profile.Role.ADMIN:
                    raise PermissionDenied("Cafe admin access required.")
                # Kitchen-only users are sent to the KDS panel
                if profile.role == "kitchen" and require_admin is False:
                    from django.urls import reverse
                    kds_url = "/pos/kds/"
                    if request.path not in (kds_url,):
                        return redirect(kds_url)
            return fn(request, *args, **kwargs)

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator


def cafe_kds_required(fn):
    """Allow admin, cashier, AND kitchen roles. Block everyone else."""
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "is_admin_host", False):
            return redirect("/admin/")
        cafe = getattr(request, "cafe", None)
        if cafe is None or not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            profile = getattr(request.user, "profile", None)
            if profile is None or profile.cafe_id != cafe.id:
                raise PermissionDenied("You don't have access to this cafe.")
        return fn(request, *args, **kwargs)
    return wrapper
