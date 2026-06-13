# Kuba — Multi-Tenant Cafe POS Platform (Foundation)

## Context

Kuba is meant to be a SaaS platform: `kuba.com` hosts many cafes, each on its own
subdomain (`<id>.kuba.com`, or a superuser-assigned custom one like `mcd.kuba.com`).
Today Kuba is a **single-tenant** app — `cafe_pos` has full POS models but they're not
scoped to any cafe, the Django admin is uncustomized, and the `dashboard` app is an empty
shell. (Migrations `0001`/`0002` exist but are **unapplied** — no `cafe_pos` tables exist
yet, so models can be reshaped cleanly.)

This pass builds the **tenant control layer** the user asked for:
1. A `Cafe` (tenant) model + subdomain resolution so the same code serves every cafe.
2. A polished **superuser Django admin** (jazzmin, like the `ane` project) to create cafes —
   name, logo SVG, admin username/email/password, subdomain (auto-random if blank), custom
   domains — with **live subdomain availability checking + reservation**.
3. A **self-service signup** that creates a cafe + its admin in one step.
4. A **per-cafe admin panel** (the existing custom-UI `dashboard` app) where a cafe admin sets
   up **floors & numbered tables** (the Table View grid in the screenshot), **products**,
   **employees**, **customizes the cafe**, and views **audit logs**.

Live POS terminal / KDS / payments / reports are deferred (already specced in `req.md`).

Multi-tenancy approach: **row-level** (shared DB, a `cafe` FK on every tenant-scoped model) —
the right fit for the current SQLite + existing-models setup. No Postgres/schema split.

---

## 1. New `tenants` app — the platform core

Create `Kuba/tenants/` with:

### `models.py`
- **`Cafe`** (the tenant): `name`, `slug`, `subdomain` (unique, lowercased, validated, auto-
  generated when blank), `custom_domain` (unique, null/blank — superuser-only, e.g.
  `mcd.kuba.com`), `logo_svg` (TextField — editable inline SVG, mirrors `ane`'s
  `Category.icon_svg`), optional `logo_image` (ImageField), `owner` (FK→User, the cafe admin),
  `is_active`, `created_at`.
  - `save()` auto-generates `subdomain` from `slugify(name)` with a numeric/random suffix on
    collision; rejects reserved names.
  - `primary_host()` / `dashboard_url(request)` helpers build the cafe's absolute URL on its
    host (used for post-signup redirect and admin links).
- **`ReservedSubdomain`**: `name` (unique). Data-migration-seeded with `admin, www, api, app,
  static, media, mail, kuba, support, billing, …`. `admin` is also hard-reserved in code for
  the Django admin host.
- **`AuditLog`**: `cafe` (FK, null=platform-level), `actor` (FK→User, null), `action`
  (`create/update/delete/login/signup`), `target_type`, `target_repr`, `message`,
  `metadata` (JSONField), `ip_address`, `created_at`.

### `utils.py`
- `normalize_subdomain(value)`, `validate_subdomain(value)` (charset + length + reserved check),
  `is_subdomain_available(value, exclude_pk=None)` → `(bool, reason)`,
  `generate_subdomain(name)`.
- `log_action(action, *, cafe, actor, request=None, target=None, message='', **meta)` — single
  helper used by admin, dashboard views, signup.

### `middleware.py`
- **`TenantMiddleware`** — resolves `request.get_host()` (port-stripped):
  - base domain from `settings.KUBA_BASE_DOMAIN` (default `kuba.com`) **and** `localhost`.
  - host == `admin.<base>` / `admin.localhost` → `request.is_admin_host = True`, `request.cafe = None`.
  - empty / bare base / `www` → root/public context (`request.cafe = None`).
  - else look up active `Cafe` by `subdomain` (or `custom_domain`) → `request.cafe`; unknown → render a "cafe not found" 404.
  - plain `localhost`/`127.0.0.1` with no subdomain → root context (so superuser admin/login works locally, per the user's "locally allow via normal admin" note).
- **`AdminAccessMiddleware`** (adapted from `ane/annexivafood/middleware.py`) — requests to
  `/admin/` require `request.user.is_superuser`; in production also require the admin host
  (`admin.<base>`), bypassed when `DEBUG`.

### `forms.py`
- **`CafeCreationForm`** (Django-admin add form): `name`, `subdomain` (blank=auto),
  `custom_domain`, `logo_svg`, plus `admin_username`, `admin_email`, `admin_password`. `clean_subdomain` uses `is_subdomain_available`.
- **`CafeSignupForm(allauth SignupForm)`**: adds `cafe_name` + optional `desired_subdomain`
  (with availability validation); `save(request)` creates User → Cafe(owner) → Profile(role=admin) → audit log.

### `adapters.py`
- `KubaAccountAdapter(DefaultAccountAdapter)` — `get_login_redirect_url` / `get_signup_redirect_url`
  send a freshly-signed-up/cafe user to **their** cafe dashboard on its subdomain host.

### `admin.py` (jazzmin-themed superuser UI)
- **`CafeAdmin`**: uses `CafeCreationForm` on add; `save_model` creates the linked User
  (`set_password`), `Profile(role=admin, cafe=…)`, sets `owner`, writes an audit log. `list_display`
  = name/subdomain/custom_domain/owner/is_active/created_at + clickable primary URL.
  Actions: activate/deactivate. `get_urls()` adds a JSON endpoint
  `check-subdomain/?value=…` → `{available, reason}`; `Media` loads
  `tenants/js/subdomain_check.js` which shows a live ✓/✗ next to the subdomain field
  (the "search DB / reserve" behaviour — reservation is the unique constraint enforced on save).
- **`ReservedSubdomainAdmin`** (CRUD), **`AuditLogAdmin`** (read-only, filterable).
- Optionally register key `cafe_pos` models read-only with a `cafe` list_filter for platform oversight.

### `views.py`
- Public `subdomain_available` JSON endpoint (for the signup page).
- Minimal root-host landing (or redirect to login/signup).

### `static/tenants/js/subdomain_check.js`, `context_processors.py`
- `tenant` context processor → `{cafe, base_domain, admin_host}` for building links/branding in templates.

---

## 2. Tenant-scope the `cafe_pos` models

In `Kuba/cafe_pos/models.py`, add `cafe = ForeignKey('tenants.Cafe', on_delete=CASCADE, related_name=…)`
to the per-cafe models: `Profile, ProductCategory, Product, Floor, CafeTable, PaymentMethod,
Coupon, Promotion, Customer, POSSession, Order`. Make uniqueness **per-cafe**:
- `ProductCategory` name, `Coupon` code, `Customer` email, `PaymentMethod` type,
  `Order` order_number → `UniqueConstraint(fields=['cafe', <f>])`.
- `POSSession` open-session uniqueness → per cafe (`condition=Q(status='open')`, `fields=['cafe']`).
- `CafeTable` stays unique per `(floor, table_number)` (floor already implies cafe).

Migrations: since `0001`/`0002` are unapplied and there are no `cafe_pos` tables, **regenerate**
— delete current `0001`+`0002`, `makemigrations cafe_pos` fresh, and rewrite the seed as a data
migration that first creates a **demo `Cafe` + its admin user**, then attaches all demo
categories/products/floors/tables/etc. to that cafe.

---

## 3. Per-cafe admin panel (the `dashboard` app, custom UI)

Reuse the existing shell (`templates/base.html` + `header.html`/`topbar.html`/`footer.html`).

- `dashboard/mixins.py` — **`CafeAdminRequiredMixin`**: requires login + `request.cafe` set +
  the user is that cafe's owner/admin (`Profile.cafe == request.cafe`, role admin), else 403.
  All views scope querysets to `request.cafe`.
- `dashboard/forms.py` — Floor, Table, Product, Category, Employee, CafeCustomize forms.
- `dashboard/views.py` + `dashboard/urls.py` (named to match `header.html` ids):
  - **`index`** — cafe-aware stats.
  - **`floors`** — the **Table View** screen from the screenshot: floor tabs + a numbered grid
    of table cards, with add/edit/delete for floors and tables (server-rendered + light JS).
  - **`products`** / `product_form` / **`categories`** — per-cafe CRUD.
  - **`users`** — list/add cafe employees (creates User + `Profile(cafe, role)`), archive, set password.
  - **`customize`** — edit cafe `name` + `logo_svg` (live preview); `subdomain` shown read-only
    (only the superuser changes it in Django admin).
  - **`audit_log`** — AuditLog list for this cafe.
  - `pos-session` / `kds` / `reports` links rendered as "coming soon" placeholders.
- New templates under `templates/dashboard/`: `floors.html, products.html, product_form.html,
  categories.html, users.html, customize.html, audit_log.html`; update `header.html` links to the
  real `dashboard:*` URLs.

---

## 4. Wiring — `kuba/settings.py`, `kuba/urls.py`, signup template, requirements

- `settings.py`: add `jazzmin` (top of `INSTALLED_APPS`, before `django.contrib.admin`) +
  `JAZZMIN_SETTINGS`; add `tenants` app; add `TenantMiddleware` + `AdminAccessMiddleware`;
  `KUBA_BASE_DOMAIN`, `KUBA_ADMIN_SUBDOMAIN='admin'`; `ALLOWED_HOSTS = ['.kuba.com','.localhost','localhost','127.0.0.1']`;
  `ACCOUNT_FORMS = {'signup': 'tenants.forms.CafeSignupForm'}`, `ACCOUNT_ADAPTER='tenants.adapters.KubaAccountAdapter'`;
  add the `tenants.context_processors.tenant` processor. (Each host keeps its own session — no
  cross-subdomain cookie sharing needed.)
- `kuba/urls.py`: include `tenants` public urls (subdomain-availability, landing); admin stays at `/admin/`.
- `templates/account/signup.html`: add **Cafe name** + **desired subdomain** fields with the live
  availability check (calls the public endpoint).
- `requirements.txt`: add `django-jazzmin`.

---

## Files

**Create:** `tenants/{__init__,apps,models,utils,middleware,forms,adapters,admin,views,context_processors,urls}.py`,
`tenants/migrations/__init__.py` (+ generated `0001` + reserved-subdomain seed),
`tenants/static/tenants/js/subdomain_check.js`,
`dashboard/{mixins,forms}.py`, and `templates/dashboard/{floors,products,product_form,categories,users,customize,audit_log}.html`.

**Modify:** `cafe_pos/models.py` (+ regenerate `cafe_pos/migrations/0001`,`0002`),
`dashboard/{views,urls}.py`, `templates/header.html`, `templates/account/signup.html`,
`kuba/settings.py`, `kuba/urls.py`, `requirements.txt`.

**Reference patterns:** jazzmin config & custom admin (`ane/product/admin.py`,
`ane/annexivafood/settings.py`), admin-gating middleware (`ane/annexivafood/middleware.py`),
inline SVG text field (`ane/product/models.py::Category.icon_svg`), custom admin `get_urls`/actions
(`ane/login/admin.py`).

---

## Verification (end-to-end)

1. `venv/Scripts/python.exe -m pip install django-jazzmin`; `makemigrations` + `migrate`;
   `createsuperuser`.
2. `python manage.py runserver` and open **`admin.localhost:8000/admin/`** → jazzmin admin.
   - Add a Cafe: fill name + admin creds + subdomain; watch the **live availability** ✓/✗; try a
     reserved name (`admin`,`www`) and a duplicate → both rejected. Leave subdomain blank → auto-generated.
3. Open **`<subdomain>.localhost:8000/`** → log in as that cafe's admin → verify the dashboard:
   create floors + a numbered table grid (matches the screenshot), add a product, add an employee,
   edit the logo SVG (live preview), view audit log entries for the actions just taken.
4. Open **`localhost:8000/accounts/signup/`** → sign up with a cafe name + subdomain → confirm a
   Cafe is created and you're redirected to `<subdomain>.localhost:8000/`.
5. Tenant isolation: data created under cafe A is not visible under cafe B's subdomain.
6. Confirm `localhost:8000/admin/` still works for the superuser locally (DEBUG bypass).