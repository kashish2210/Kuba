from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html

from .forms import CafeCreationForm
from .models import AuditLog, Cafe, ReservedSubdomain
from .utils import is_subdomain_available, log_action, normalize_subdomain


class CafeChangeForm(forms.ModelForm):
    class Meta:
        model = Cafe
        fields = [
            "name", "subdomain", "custom_domain", "logo_svg", "logo_image",
            "owner", "is_active",
        ]
        widgets = {
            "logo_svg": forms.Textarea(attrs={"rows": 6, "style": "font-family:monospace"}),
        }

    def clean_subdomain(self):
        value = self.cleaned_data.get("subdomain", "")
        if not value:
            return ""
        ok, reason = is_subdomain_available(value, exclude_pk=self.instance.pk)
        if not ok:
            raise forms.ValidationError(reason)
        return normalize_subdomain(value)


@admin.register(Cafe)
class CafeAdmin(admin.ModelAdmin):
    add_form = CafeCreationForm
    form = CafeChangeForm
    list_display = ("name", "subdomain", "custom_domain", "owner", "is_active", "created_at", "open_link")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "subdomain", "custom_domain", "owner__username", "owner__email")
    readonly_fields = ("slug", "created_at", "primary_url_display")
    actions = ("activate_cafes", "deactivate_cafes")

    class Media:
        js = ("tenants/js/subdomain_check.js",)

    # --- add vs change form ---------------------------------------------------
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                ("Cafe", {
                    "fields": ("name", "subdomain", "custom_domain", "is_active"),
                    "description": "Leave the subdomain blank to auto-generate one. "
                                   "Availability is checked live as you type.",
                }),
                ("Branding", {"fields": ("logo_svg", "logo_image")}),
                ("Cafe administrator account", {
                    "fields": ("admin_username", "admin_email", "admin_password"),
                    "description": "These credentials let the cafe owner sign in to their dashboard.",
                }),
            )
        return (
            ("Cafe", {"fields": ("name", "subdomain", "custom_domain", "is_active", "primary_url_display")}),
            ("Branding", {"fields": ("logo_svg", "logo_image")}),
            ("Ownership", {"fields": ("owner", "slug", "created_at")}),
        )

    # --- live availability endpoint ------------------------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "check-subdomain/",
                self.admin_site.admin_view(self.check_subdomain),
                name="tenants_cafe_check_subdomain",
            ),
        ]
        return custom + urls

    def check_subdomain(self, request):
        value = request.GET.get("value", "")
        exclude_pk = request.GET.get("exclude") or None
        ok, reason = is_subdomain_available(value, exclude_pk=exclude_pk)
        return JsonResponse(
            {"available": ok, "reason": reason, "normalized": normalize_subdomain(value)}
        )

    # --- create the linked user on add ---------------------------------------
    def save_model(self, request, obj, form, change):
        from cafe_pos.models import Profile

        if not change:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = User.objects.create_user(
                username=form.cleaned_data["admin_username"],
                email=form.cleaned_data["admin_email"],
                password=form.cleaned_data["admin_password"],
            )
            obj.owner = user
            super().save_model(request, obj, form, change)
            Profile.objects.update_or_create(
                user=user,
                defaults={"cafe": obj, "role": Profile.Role.ADMIN, "is_archived": False},
            )
            log_action(
                "create", cafe=obj, actor=request.user, request=request, target=obj,
                message=f"Cafe '{obj.name}' created with admin '{user.username}'.",
            )
        else:
            super().save_model(request, obj, form, change)
            log_action(
                "update", cafe=obj, actor=request.user, request=request, target=obj,
                message=f"Cafe '{obj.name}' updated.",
            )

    # --- display helpers ------------------------------------------------------
    def _cafe_url(self, obj):
        if obj.custom_domain:
            return f"https://{obj.custom_domain}/"
        if settings.DEBUG:
            return f"http://{obj.subdomain}.localhost:8000/"
        return f"https://{obj.subdomain}.{obj.base_domain}/"

    def open_link(self, obj):
        url = self._cafe_url(obj)
        return format_html('<a href="{}" target="_blank">Open ↗</a>', url)
    open_link.short_description = "Dashboard"

    def primary_url_display(self, obj):
        url = self._cafe_url(obj)
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)
    primary_url_display.short_description = "Primary URL"

    @admin.action(description="Activate selected cafes")
    def activate_cafes(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} cafe(s).")

    @admin.action(description="Deactivate selected cafes")
    def deactivate_cafes(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} cafe(s).")


@admin.register(ReservedSubdomain)
class ReservedSubdomainAdmin(admin.ModelAdmin):
    list_display = ("name", "note")
    search_fields = ("name",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "cafe", "actor", "action", "target_type", "target_repr")
    list_filter = ("action", "cafe", "created_at")
    search_fields = ("target_repr", "message", "actor__username")
    readonly_fields = (
        "cafe", "actor", "action", "target_type", "target_repr",
        "message", "metadata", "ip_address", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.site_header = "Kuba Platform Admin"
admin.site.site_title = "Kuba Admin"
admin.site.index_title = "Platform Management"
