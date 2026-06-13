from allauth.account.forms import SignupForm
from django import forms
from django.contrib.auth import get_user_model

from .models import Organisation


class OrganisationForm(forms.ModelForm):
    admin_email = forms.EmailField(help_text='Used to create or connect the organisation admin account.')
    admin_name = forms.CharField(max_length=140, required=False)
    temporary_password = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text='Optional. If filled, a new admin account is created with this password.',
    )

    class Meta:
        model = Organisation
        fields = ['name', 'contact_name', 'contact_email', 'phone', 'city', 'is_active']

    def save(self, commit=True):
        organisation = super().save(commit=False)
        User = get_user_model()
        admin_email = self.cleaned_data['admin_email']
        admin_name = self.cleaned_data.get('admin_name', '')
        password = self.cleaned_data.get('temporary_password', '')

        user, created = User.objects.get_or_create(
            email=admin_email,
            defaults={
                'username': admin_email,
                'first_name': admin_name,
                'is_staff': True,
            },
        )
        if admin_name and not user.first_name:
            user.first_name = admin_name
        if created and password:
            user.set_password(password)
        elif created:
            user.set_unusable_password()
        user.is_staff = True
        user.save()

        organisation.admin_user = user
        if commit:
            organisation.save()
        return organisation


class OrganisationSignupForm(SignupForm):
    admin_name = forms.CharField(max_length=140, label='Your name')
    organisation_name = forms.CharField(max_length=180, label='Cafe / organisation name')
    phone = forms.CharField(max_length=30, required=False, label='Phone')
    city = forms.CharField(max_length=90, required=False, label='City')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['admin_name']
        user.is_staff = True
        user.save()
        Organisation.objects.create(
            name=self.cleaned_data['organisation_name'],
            admin_user=user,
            contact_name=self.cleaned_data['admin_name'],
            contact_email=user.email,
            phone=self.cleaned_data.get('phone', ''),
            city=self.cleaned_data.get('city', ''),
        )
        return user
