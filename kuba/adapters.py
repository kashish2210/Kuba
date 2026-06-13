from allauth.account.adapter import DefaultAccountAdapter


class KubaAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        if request.user.is_superuser:
            return '/super-admin/organisations/'
        return '/organisation-admin/'
