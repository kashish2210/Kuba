from django.db import migrations

RESERVED = [
    ("admin", "Django platform admin host"),
    ("www", ""),
    ("api", ""),
    ("app", ""),
    ("static", ""),
    ("media", ""),
    ("mail", ""),
    ("smtp", ""),
    ("kuba", "Brand"),
    ("support", ""),
    ("help", ""),
    ("billing", ""),
    ("blog", ""),
    ("docs", ""),
    ("status", ""),
    ("dashboard", ""),
    ("account", ""),
    ("accounts", ""),
    ("login", ""),
    ("signup", ""),
    ("register", ""),
]


def seed(apps, schema_editor):
    ReservedSubdomain = apps.get_model("tenants", "ReservedSubdomain")
    for name, note in RESERVED:
        ReservedSubdomain.objects.get_or_create(name=name, defaults={"note": note})


def unseed(apps, schema_editor):
    ReservedSubdomain = apps.get_model("tenants", "ReservedSubdomain")
    ReservedSubdomain.objects.filter(name__in=[n for n, _ in RESERVED]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
