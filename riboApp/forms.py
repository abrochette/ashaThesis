from django import forms

from riboApp.models import UploadedParquet, UploadedMrnaParquet


class CreateNewList(forms.Form):
    experimentName = forms.CharField(label="Experiment name", max_length=200, required=False)
    adapter = forms.CharField(
        label="Input adapter sequence to be trimmed",
        max_length=500,
        required=True,
        help_text="Adapter sequence found in your sequencing data (e.g., AGATCGGAAGAGC)"
    )
    mouseGenome = forms.BooleanField(label="GRCm39", required=False)
    humanGenome = forms.BooleanField(label="GRCh38", required=False)
    useBarcode = forms.BooleanField(
        label="Use UMI for demultiplexing",
        required=False,
        help_text="Check this if your samples contain UMIs (Unique Molecular Identifiers) that need to be removed during preprocessing"
    )
    includeRnaSeq = forms.BooleanField(
        label="Include mRNA-seq data processing",
        required=False,
        initial=True,
        help_text="Check this if you have mRNA-seq data to process alongside ribosome profiling data"
    )
    sampleFile = forms.FileField(
        label="Upload text file containing ribosome profiling sample data paths",
        required=True,
        help_text="Text file with ribosome profiling sample names and file paths (one per line: sample_name /path/to/file.fastq.gz)"
    )
    mrnaSeqFile = forms.FileField(
        label="Upload text file containing mRNA-seq sample data paths",
        required=False,
        help_text="Text file with mRNA-seq sample names and file paths. Only required if 'Include mRNA-seq data processing' is checked."
    )


class ParquetUploadForm(forms.ModelForm):
    class Meta:
        model = UploadedParquet
        fields = ["file"]

class MrnaParquetUploadForm(forms.ModelForm):
    class Meta:
        model = UploadedMrnaParquet
        fields = ["file"]

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class BulkParquetUploadForm(forms.Form):
    files = MultipleFileField(
        label="Select Multiple Riboseq Parquet Files",
        help_text="Hold Ctrl/Cmd to select multiple files, or drag and drop a folder"
    )

class BulkMrnaParquetUploadForm(forms.Form):
    files = MultipleFileField(
        label="Select Multiple mRNA Parquet Files",
        help_text="Hold Ctrl/Cmd to select multiple files, or drag and drop a folder"
    )

class PsiteOffsetUploadForm(forms.Form):
    offset_csv = forms.FileField(
        label="Upload P-site Offset CSV",
        required=False,
        help_text="CSV file with columns: Experiment, Read Length, P-site Offset"
    )


