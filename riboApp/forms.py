from django import forms

class CreateNewList(forms.Form):
    experimentName = forms.CharField(label="Experiment name", max_length=200, required=False)
    adapter = forms.CharField(label="Input adapter sequence to be trimmed", max_length=500, required=True)
    mouseGenome = forms.BooleanField(label="GRCm39", required=False)
    humanGenome = forms.BooleanField(label="GRCh38", required=False)
    sampleFile = forms.FileField(label="Upload text file containing sample data paths", required=True)
