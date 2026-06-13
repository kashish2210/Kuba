from allauth.account.adapter import DefaultAccountAdapter


def _user_cafe(user):
    """The cafe a user administers/works in, if any."""
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "cafe_id", None):
        return profile.cafe
    return user.owned_cafes.first()


class KubaAccountAdapter(DefaultAccountAdapter):
    """Route users to their own cafe's dashboard host after login/signup."""

    def _dashboard_redirect(self, request, cafe):
        # Already on the right cafe host -> plain dashboard path.
        if getattr(request, "cafe", None) and request.cafe.pk == cafe.pk:
            return "/"
        # Otherwise send them across to their subdomain host.
        return cafe.dashboard_url(request)

    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_superuser and getattr(request, "is_admin_host", False):
            return "/admin/"
        cafe = _user_cafe(user)
        if cafe is not None:
            return self._dashboard_redirect(request, cafe)
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
            return self._dashboard_redirect(request, cafe)
        return super().get_signup_redirect_url(request)
