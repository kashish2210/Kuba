from django.urls import path

from . import views

app_name = "tenants"

urlpatterns = [
    path("api/subdomain-available/", views.subdomain_available, name="subdomain-available"),
]
