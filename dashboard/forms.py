from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from cafe_pos.models import CafeTable, Floor, Product, ProductCategory, Profile
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
            "name", "category", "image", "price", "unit_of_measure",
            "tax_percentage", "description", "show_in_kds", "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, cafe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cafe is not None:
            self.fields["category"].queryset = ProductCategory.objects.filter(cafe=cafe)


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
        fields = ["name", "logo_svg", "logo_image"]
        widgets = {
            "logo_svg": forms.Textarea(attrs={"rows": 8, "style": "font-family:monospace"}),
        }
