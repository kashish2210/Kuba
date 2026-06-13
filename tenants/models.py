from django.conf import settings
from django.db import models
from django.utils import timezone

from .utils import generate_subdomain, normalize_subdomain


class Cafe(models.Model):
    """A tenant. One cafe = one POS workspace served on its own subdomain."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    subdomain = models.CharField(
        max_length=63,
        unique=True,
        blank=True,
        help_text="The <this>.kuba.com host. Leave blank to auto-generate.",
    )
    custom_domain = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Optional full custom host, e.g. mcd.kuba.com. Superuser only.",
    )
    logo_svg = models.TextField(
        blank=True,
        help_text="Inline SVG markup for the cafe logo (editable).",
    )
    logo_image = models.ImageField(upload_to="cafe_logos/", null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_cafes",
        help_text="The cafe administrator account.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        if self.subdomain:
            self.subdomain = normalize_subdomain(self.subdomain)
        else:
            self.subdomain = generate_subdomain(self.name)
        if not self.slug:
            base = slugify(self.name) or self.subdomain
            slug = base
            counter = 1
            while Cafe.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                counter += 1
                slug = f"{base}-{counter}"
            self.slug = slug
        if self.custom_domain:
            self.custom_domain = self.custom_domain.strip().lower()
        super().save(*args, **kwargs)

    @property
    def base_domain(self):
        return getattr(settings, "KUBA_BASE_DOMAIN", "kuba.com")

    def primary_host(self):
        """The canonical host for this cafe (custom domain wins over subdomain)."""
        if self.custom_domain:
            return self.custom_domain
        return f"{self.subdomain}.{self.base_domain}"

    def dashboard_url(self, request=None):
        """Absolute URL to this cafe's dashboard, on its own host."""
        scheme = "https"
        port = ""
        if request is not None:
            scheme = "https" if request.is_secure() else "http"
            host = request.get_host()
            if ":" in host:
                port = ":" + host.split(":", 1)[1]
        host = self.custom_domain or f"{self.subdomain}.{self.base_domain}"
        # Locally the base domain is "localhost"; keep the dev port.
        if not self.custom_domain and request is not None:
            req_host = request.get_host().split(":", 1)[0]
            if req_host.endswith("localhost") or req_host in {"127.0.0.1"}:
                host = f"{self.subdomain}.localhost"
        return f"{scheme}://{host}{port}/"


class ReservedSubdomain(models.Model):
    """Subdomains that cannot be claimed by a cafe (admin, www, api, ...)."""

    name = models.CharField(max_length=63, unique=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Reserved subdomain"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = normalize_subdomain(self.name)
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """An append-only record of notable actions, per cafe or platform-wide."""

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        LOGIN = "login", "Login"
        SIGNUP = "signup", "Signup"
        OTHER = "other", "Other"

    cafe = models.ForeignKey(
        Cafe,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="Null for platform-level actions.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices, default=Action.OTHER)
    target_type = models.CharField(max_length=100, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = self.actor.get_username() if self.actor else "system"
        return f"{who} {self.action} {self.target_repr}".strip()
