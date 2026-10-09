from django.contrib import admin
from django.urls import path
from Main import views  # Import views directly from your Main app

urlpatterns = [
    # Django Admin Panel
    path('admin/', admin.site.urls),
    
    # Endpoints for license plate checking
    path('api/v1/check_exists', views.check_if_exists, name='check_if_exists'),
    path('api/v1/check_has_pass', views.check_if_has_pass, name='check_if_has_pass'),
    path('api/v1/check_pass_valid', views.check_if_pass_is_valid, name='check_pass_valid'),
]
