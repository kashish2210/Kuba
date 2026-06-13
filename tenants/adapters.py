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


def _is_member(user, cafe):
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return profile is not None and profile.cafe_id == cafe.id


class KubaAccountAdapter(DefaultAccountAdapter):
    """Subdomain-locked auth.

    A user signs in on *their own* cafe's subdomain — login never auto-detects or
    jumps to a different subdomain. New-cafe signup is only allowed on the root host.
    """

    def is_open_for_signup(self, request):
        # Only the public root host offers new-cafe registration; an existing
        # cafe's subdomain (or the admin host) shows the "signup closed" page.
        return getattr(request, "cafe", None) is None and not getattr(request, "is_admin_host", False)

    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_superuser and getattr(request, "is_admin_host", False):
            return "/admin/"
        cafe = getattr(request, "cafe", None)
        if cafe is not None:
            # Member logging in on their own cafe host -> same-host landing.
            return _landing_path(user)
        return "/"

    def get_signup_redirect_url(self, request):
        from .models import Cafe

        cafe = None
        cafe_id = request.session.pop("signup_cafe_id", None)
        if cafe_id:
            cafe = Cafe.objects.filter(pk=cafe_id).first()
        if cafe is None:
            cafe = _user_cafe(request.user)
        if cafe is not None:
            # A fresh signup created this cafe on the root host -> send the new
            # owner to their cafe's own subdomain dashboard.
            return cafe.dashboard_url(request)
        return super().get_signup_redirect_url(request)
