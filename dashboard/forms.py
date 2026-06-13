from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from cafe_pos.models import (
    CafeTable,
    ChatAssistantSettings,
    Coupon,
    Floor,
    Customer,
    LoyaltySettings,
    PaymentMethod,
    PaymentSettings,
    Product,
    ProductCategory,
    Profile,
    Promotion,
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
            "is_featured", "tags", "cross_sells"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "cross_sells": forms.SelectMultiple(attrs={"size": 6}),
        }

    def __init__(self, *args, cafe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cafe is not None:
            self.fields["category"].queryset = ProductCategory.objects.filter(cafe=cafe)
            self.fields["cross_sells"].queryset = Product.objects.filter(cafe=cafe, is_active=True).exclude(pk=self.instance.pk if self.instance else None)


class CouponForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ["name", "code", "discount_type", "discount_value", "is_active"]

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


class PromotionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Promotion
        fields = ["name", "apply_to", "product", "min_quantity", "min_order_amount", "discount_type", "discount_value", "is_active"]
        widgets = {
            "min_order_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "min_quantity": forms.NumberInput(attrs={"min": "1"}),
        }

    def __init__(self, *args, cafe=None, **kwargs):
        self._cafe = cafe
        super().__init__(*args, **kwargs)
        if cafe is not None:
            self.fields["product"].queryset = Product.objects.filter(cafe=cafe, is_active=True)
        self.fields["product"].required = False
        self.fields["min_quantity"].required = False
        self.fields["min_order_amount"].required = False

    def clean(self):
        cd = super().clean()
        apply_to = cd.get("apply_to")
        if apply_to == Promotion.ApplyTo.PRODUCT:
            if not cd.get("product"):
                self.add_error("product", "Required for product-based promotions.")
            if not cd.get("min_quantity"):
                self.add_error("min_quantity", "Required for product-based promotions.")
            cd["min_order_amount"] = None
        elif apply_to == Promotion.ApplyTo.ORDER:
            if not cd.get("min_order_amount"):
                self.add_error("min_order_amount", "Required for order-based promotions.")
            cd["product"] = None
            cd["min_quantity"] = None
        return cd


class LoyaltySettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LoyaltySettings
        fields = [
            "level_1_orders",
            "level_2_orders",
            "level_3_orders",
            "level_4_orders",
            "level_5_orders",
            "points_per_order",
        ]
        widgets = {
            "level_1_orders": forms.NumberInput(attrs={"min": "1"}),
            "level_2_orders": forms.NumberInput(attrs={"min": "1"}),
            "level_3_orders": forms.NumberInput(attrs={"min": "1"}),
            "level_4_orders": forms.NumberInput(attrs={"min": "1"}),
            "level_5_orders": forms.NumberInput(attrs={"min": "1"}),
            "points_per_order": forms.NumberInput(attrs={"min": "0"}),
        }
        labels = {
            "level_1_orders": "Level 1 orders",
            "level_2_orders": "Level 2 orders",
            "level_3_orders": "Level 3 orders",
            "level_4_orders": "Level 4 orders",
            "level_5_orders": "Level 5 orders",
            "points_per_order": "Points per paid order",
        }

    def clean(self):
        cd = super().clean()
        values = [cd.get(f"level_{i}_orders") for i in range(1, 6)]
        if all(v is not None for v in values) and values != sorted(values):
            raise forms.ValidationError("Loyalty order thresholds must go from lowest to highest.")
        return cd


class CustomerLoyaltyForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["manual_loyalty_level", "is_banned", "ban_reason"]
        widgets = {
            "manual_loyalty_level": forms.NumberInput(attrs={"min": "1", "max": "5"}),
            "ban_reason": forms.TextInput(attrs={"placeholder": "Optional reason shown to staff"}),
        }
        labels = {
            "manual_loyalty_level": "Manual level override",
            "is_banned": "Ban customer",
            "ban_reason": "Ban reason",
        }

    def clean_ban_reason(self):
        if not self.cleaned_data.get("is_banned"):
            return ""
        return self.cleaned_data.get("ban_reason", "").strip()


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


class ChatAssistantSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ChatAssistantSettings
        fields = [
            "is_enabled", "bot_name", "welcome_message",
            "gemini_api_key", "gemini_model",
            "groq_api_key", "groq_model",
            "custom_instructions", "terms_and_conditions",
        ]
        widgets = {
            "gemini_api_key": forms.PasswordInput(render_value=True),
            "groq_api_key": forms.PasswordInput(render_value=True),
            "welcome_message": forms.Textarea(attrs={"rows": 2}),
            "custom_instructions": forms.Textarea(attrs={"rows": 4}),
            "terms_and_conditions": forms.Textarea(attrs={"rows": 6}),
        }
        help_texts = {
            "bot_name": "Displayed to customers in the chat and in emails.",
            "custom_instructions": "Extra guidance for the AI, e.g. 'Always mention our specials.'",
            "terms_and_conditions": "If filled, customers must accept these before chatting. Leave blank to skip.",
            "gemini_api_key": "Google AI Studio key. Used first; leave blank to skip Gemini.",
            "groq_api_key": "Groq key. Used as fallback if Gemini is unavailable.",
        }
