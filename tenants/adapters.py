from allauth.account.adapter import DefaultAccountAdapter


def _user_cafe(user):
    """The cafe a user administers/works in, if any."""
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "cafe_id", None):
        return profile.cafe
    return user.owned_cafes.first()


def _landing_path(user):
    """Cashiers belong in the POS; admins/owners land on the dashboard."""
    profile = getattr(user, "profile", None)
    if profile is not None and profile.role == "cashier":
        return "/pos/"
    return "/"


class KubaAccountAdapter(DefaultAccountAdapter):
    """Route users to the right place after login/signup based on their role.

    Staff (cashiers) are recognised automatically and sent straight to the POS
    terminal; cafe admins/owners go to the admin dashboard; the platform
    superuser on the admin host goes to the Django admin.
    """

    def _role_redirect(self, request, cafe, user):
        path = _landing_path(user)
        # Already on the right cafe host -> a relative path is enough.
        if getattr(request, "cafe", None) and request.cafe.pk == cafe.pk:
            return path
        # Otherwise build an absolute URL on the cafe's own subdomain host.
        return cafe.dashboard_url(request).rstrip("/") + path

    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_superuser and getattr(request, "is_admin_host", False):
            return "/admin/"
        cafe = _user_cafe(user)
        if cafe is not None:
            return self._role_redirect(request, cafe, user)
        return super().get_login_redirect_url(request)

    def get_signup_redirect_url(self, request):
        from .models import Cafe

        cafe = None
        cafe_id = request.session.pop("signup_cafe_id", None)
        if cafe_id:
            cafe = Cafe.objects.filter(pk=cafe_id).first()
        if cafe is None:
            cafe = _user_cafe(request.user)
        if cafe is not None:
            # A fresh signup always creates the cafe's admin/owner -> dashboard.
            return self._role_redirect(request, cafe, request.user)
        return super().get_signup_redirect_url(request)
