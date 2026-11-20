"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from apps.accounts.views import admin_login
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin 로그인 시도를 센다. admin/ 보다 앞에 있어야 가로챈다.
    path("admin/login/", admin_login),
    path("admin/", admin.site.urls),
    path("api/vocab/", include("apps.vocab.urls")),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/learning/", include("apps.learning.urls")),
]
