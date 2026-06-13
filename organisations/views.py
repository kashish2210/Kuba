from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import OrganisationForm
from .models import Organisation


@staff_member_required
def super_admin_organisations(request):
    if request.method == 'POST':
        form = OrganisationForm(request.POST)
        if form.is_valid():
            organisation = form.save()
            messages.success(request, f'{organisation.name} was created successfully.')
            return redirect('super_admin_organisations')
    else:
        form = OrganisationForm()

    organisations = Organisation.objects.select_related('admin_user')
    return render(
        request,
        'organisations/super_admin_organisations.html',
        {'form': form, 'organisations': organisations},
    )


@login_required
def organisation_admin_dashboard(request):
    organisation = getattr(request.user, 'organisation', None)
    return render(
        request,
        'organisations/organisation_admin_dashboard.html',
        {'organisation': organisation},
    )
