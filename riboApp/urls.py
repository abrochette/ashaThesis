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
    path("clear_parquet_files/", views.clear_parquet_files, name="clear_parquet_files"),
    path("geneCounts/", views.geneCounts, name="geneCounts"),
    path("log2GeneCounts/", views.log2_geneCounts, name="log2GeneCounts"),
    path("plot_gene_counts/", views.plot_gene_counts, name="plot_gene_counts"),
    path("save_selected_genes/", views.save_selected_genes, name="save_selected_genes"),
    path("binCounts/", views.bin_counts_view, name="binCounts"),
    path("readLengthDistribution/", views.read_length_distribution_view, name="readLengthDistribution"),
    path("psiteOffset/", views.psite_offset_view, name="psiteOffset"),
    path("pca/", views.pca_gene_counts, name="pca_plot"),
    path("coverageGraphs/", views.process_ribo_files, name="coverageGraphs"),
    # mRNA analysis URLs
    path("combined_geneCounts/", views.combined_geneCounts, name="combined_geneCounts"),
    path("combined_pca/", views.combined_pca_gene_counts, name="combined_pca_plot"),
    path("delta_analysis/", views.delta_analysis, name="delta_analysis"),
    # P-site metagene analysis
    path("psite_metagene/", views.psite_metagene_plots, name="psite_metagene"),
    # CSV download endpoints
    path("download_csv/<str:analysis_type>/", views.download_csv, name="download_csv"),
    # Performance optimization endpoints
    path("preprocess_all_files/", views.preprocess_all_files_view, name="preprocess_all_files"),
    path("update_psite_caches/", views.update_psite_caches_view, name="update_psite_caches"),
    path("clear_all_cache/", views.clear_all_cache_view, name="clear_all_cache"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
