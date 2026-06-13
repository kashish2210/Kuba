from django.contrib import admin

from .models import Organisation


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_email', 'admin_user', 'city', 'is_active', 'created_at')
    list_filter = ('is_active', 'city', 'created_at')
    search_fields = ('name', 'contact_email', 'contact_name', 'admin_user__email')
    prepopulated_fields = {'slug': ('name',)}
