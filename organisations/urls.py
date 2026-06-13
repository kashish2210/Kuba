from django.urls import path

from . import views

urlpatterns = [
    path('super-admin/organisations/', views.super_admin_organisations, name='super_admin_organisations'),
    path('organisation-admin/', views.organisation_admin_dashboard, name='organisation_admin_dashboard'),
]
