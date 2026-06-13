from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from cafe_pos.models import (
    CafeTable,
    Coupon,
    Floor,
    PaymentMethod,
    PaymentSettings,
    Product,
    ProductCategory,
    Profile,
    ReceiptSettings,
)
from tenants.models import Cafe


class StyledFormMixin:
    """Apply the dashboard's CSS classes to default Django widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            if isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-textarea")
            else:
                widget.attrs.setdefault("class", "form-input")


class FloorForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Floor
        fields = ["name", "sort_order"]


class TableForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CafeTable
        fields = ["floor", "table_number", "seats", "is_active"]

    def __init__(self, *args, cafe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cafe is not None:
            self.fields["floor"].queryset = Floor.objects.filter(cafe=cafe)


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ["name", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}


class ProductForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "category", "price", "unit_of_measure",
            "tax_percentage", "description", "image", "show_in_kds", "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, cafe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cafe is not None:
            self.fields["category"].queryset = ProductCategory.objects.filter(cafe=cafe)


class CouponForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ["code", "discount_type", "discount_value", "is_active"]

    def __init__(self, *args, cafe=None, **kwargs):
        self._cafe = cafe
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if self._cafe is not None:
            qs = Coupon.objects.filter(cafe=self._cafe, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("A coupon with that code already exists.")
        return code


class EmployeeForm(StyledFormMixin, forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    role = forms.ChoiceField(choices=Profile.Role.choices, initial=Profile.Role.CASHIER)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class SetPasswordForm(StyledFormMixin, forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="New password")

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class CafeCustomizeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Cafe
        fields = [
            "name", "logo_svg", "logo_image",
            "theme_primary_color", "theme_primary_hover_color", "theme_accent_color",
            "theme_sidebar_color", "theme_surface_color", "theme_surface_alt_color",
            "theme_text_color", "theme_radius_px", "custom_css",
        ]
        widgets = {
            "logo_svg": forms.Textarea(attrs={"rows": 8, "style": "font-family:monospace"}),
            "theme_primary_color": forms.TextInput(attrs={"type": "color"}),
            "theme_primary_hover_color": forms.TextInput(attrs={"type": "color"}),
            "theme_accent_color": forms.TextInput(attrs={"type": "color"}),
            "theme_sidebar_color": forms.TextInput(attrs={"type": "color"}),
            "theme_surface_color": forms.TextInput(attrs={"type": "color"}),
            "theme_surface_alt_color": forms.TextInput(attrs={"type": "color"}),
            "theme_text_color": forms.TextInput(attrs={"type": "color"}),
            "theme_radius_px": forms.NumberInput(attrs={"min": 4, "max": 28, "step": 1}),
            "custom_css": forms.Textarea(attrs={
                "rows": 12,
                "spellcheck": "false",
                "style": "font-family:ui-monospace,SFMono-Regular,Consolas,monospace",
                "placeholder": ".btn-primary {\n    text-transform: uppercase;\n}",
            }),
        }
        labels = {
            "theme_primary_color": "Primary color",
            "theme_primary_hover_color": "Primary hover color",
            "theme_accent_color": "Accent color",
            "theme_sidebar_color": "Sidebar color",
            "theme_surface_color": "Page background",
            "theme_surface_alt_color": "Alternate surface",
            "theme_text_color": "Text color",
            "theme_radius_px": "Corner radius",
            "custom_css": "CSS override editor",
        }


class PaymentSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PaymentSettings
        fields = [
            "upi_id", "upi_payee_name",
            "razorpay_enabled", "razorpay_key_id", "razorpay_key_secret",
            "stripe_enabled", "stripe_publishable_key", "stripe_secret_key",
        ]
        widgets = {
            "razorpay_key_secret": forms.PasswordInput(render_value=True),
            "stripe_secret_key": forms.PasswordInput(render_value=True),
        }


class ReceiptSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ReceiptSettings
        fields = [
            "use_default", "template_html",
            "smtp_use_default", "smtp_host", "smtp_port", "smtp_user",
            "smtp_password", "smtp_use_tls", "from_email",
        ]
        widgets = {
            "template_html": forms.Textarea(attrs={
                "rows": 18, "id": "receipt-html",
                "style": "font-family:ui-monospace,Consolas,monospace;",
            }),
            "smtp_password": forms.PasswordInput(render_value=True),
        }
