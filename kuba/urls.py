"""
URL configuration for kuba project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from cafe_pos import chat_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('tenants.urls')),
    path('pos/', include('pos.urls')),
    path('', include('dashboard.urls')),
    # Public chat session (no login required, token-gated)
    path('session/<uuid:token>/', chat_views.chat_session, name='chat-session'),
    path('session/<uuid:token>/chat/', chat_views.chat_message, name='chat-message'),
    path('session/<uuid:token>/accept-terms/', chat_views.accept_terms, name='chat-accept-terms'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif not getattr(settings, 'USE_CLOUDINARY', False):
    # Production without Cloudinary: serve user-uploaded media through Django.
    # Cloudinary (when configured) serves media from its own CDN, so this
    # fallback is only needed for local-disk media. Functional but not ideal
    # for high traffic — prefer Cloudinary or a CDN at scale.
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
