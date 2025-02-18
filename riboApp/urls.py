from django.urls import path
from . import views
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
import riboApp.geneCounts


urlpatterns = [
    path('admin/', admin.site.urls),
    path('home/', views.home, name = "home"),
    path("preprocess/", views.preProcess, name="preprocess"),
    path("analyze/", views.analyze, name="analyze"),
    path("locatepsites/", views.locatePsites, name="locatepsites"),
    path('download/<str:file_name>/', views.download_file, name='download_file'),
    path("upload/", views.upload_parquet, name="upload_parquet"),
    path("geneCounts/", views.geneCounts, name="geneCounts"),
    path("plot_gene_counts/", views.plot_gene_counts, name="plot_gene_counts"),
    path("save_selected_genes/", views.save_selected_genes, name="save_selected_genes"),
    path("binCounts/", views.bin_counts_view, name="binCounts"),
    path("pca/", views.pca_gene_counts, name="pca_plot"),
    path("coverageGraphs/", views.process_ribo_files, name="coverageGraphs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
