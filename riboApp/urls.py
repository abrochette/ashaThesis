from django.urls import path
from . import views
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('home/', views.home, name = "home"),
    path("preprocess/", views.preProcess, name="preprocess"),
    path("analyze/", views.analyze, name="analyze"),
    path("locatepsites/", views.locatePsites, name="locatepsites"),
    path('download/<str:file_name>/', views.download_file, name='download_file')
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
