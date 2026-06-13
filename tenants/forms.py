from allauth.account.forms import LoginForm, SignupForm
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Cafe
from .utils import is_subdomain_available, normalize_subdomain


class CafeLoginForm(LoginForm):
    """Refuse a login on a cafe subdomain unless the account belongs to that cafe."""

    def clean(self):
        cleaned = super().clean()
        user = getattr(self, "user", None)
        request = getattr(self, "request", None)
        cafe = getattr(request, "cafe", None) if request is not None else None
        if user is not None and cafe is not None and not user.is_superuser:
            profile = getattr(user, "profile", None)
            if profile is None or profile.cafe_id != cafe.id:
                raise forms.ValidationError(
                    f"This account doesn't belong to {cafe.name}. "
                    "Please sign in at your own cafe's address."
                )
        return cleaned


class CafeCreationForm(forms.ModelForm):
    """Django-admin add form: creates a Cafe AND its admin user in one step."""

    admin_username = forms.CharField(max_length=150, label="Cafe admin username")
    admin_email = forms.EmailField(label="Cafe admin email")
    admin_password = forms.CharField(
        label="Cafe admin password",
        widget=forms.PasswordInput(render_value=True),
    )

    class Meta:
        model = Cafe
        fields = ["name", "subdomain", "custom_domain", "logo_svg", "logo_image", "is_active"]
        widgets = {
            "subdomain": forms.TextInput(attrs={"placeholder": "leave blank to auto-generate"}),
            "logo_svg": forms.Textarea(attrs={"rows": 6, "style": "font-family:monospace"}),
        }

    def clean_subdomain(self):
        value = self.cleaned_data.get("subdomain", "")
        if not value:
            return ""  # model.save() will auto-generate
        ok, reason = is_subdomain_available(value)
        if not ok:
            raise forms.ValidationError(reason)
        return normalize_subdomain(value)

    def clean_admin_username(self):
        username = self.cleaned_data["admin_username"].strip()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def clean_admin_email(self):
        email = self.cleaned_data["admin_email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

    def clean_admin_password(self):
        password = self.cleaned_data["admin_password"]
        validate_password(password)
        return password


class CafeSignupForm(SignupForm):
    """Self-service signup: a new account also creates a cafe the user administers."""

    cafe_name = forms.CharField(max_length=150, label="Cafe name")
    desired_subdomain = forms.CharField(
        max_length=63,
        required=False,
        label="Subdomain",
        help_text="Optional. Your cafe will live at <this>.kuba.com. Leave blank to auto-generate.",
    )

    field_order = ["cafe_name", "desired_subdomain", "username", "email", "password1", "password2"]

    def clean_desired_subdomain(self):
        value = self.cleaned_data.get("desired_subdomain", "")
        if not value:
            return ""
        ok, reason = is_subdomain_available(value)
        if not ok:
            raise forms.ValidationError(reason)
        return normalize_subdomain(value)

    def save(self, request):
        from cafe_pos.models import Profile

        user = super().save(request)
        cafe = Cafe.objects.create(
            name=self.cleaned_data["cafe_name"],
            subdomain=self.cleaned_data.get("desired_subdomain", ""),
            owner=user,
        )
        Profile.objects.update_or_create(
            user=user,
            defaults={"cafe": cafe, "role": Profile.Role.ADMIN, "is_archived": False},
        )
        from .utils import log_action

        log_action(
            "signup",
            cafe=cafe,
            actor=user,
            request=request,
            target=cafe,
            message=f"Self-service signup created cafe '{cafe.name}'.",
        )
        # Stash for the adapter's post-signup redirect.
        request.session["signup_cafe_id"] = cafe.pk
        return user
