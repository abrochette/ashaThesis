from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, Http404
from .models import ProcessingInput
from .forms import CreateNewList
import mimetypes
import os

def preProcess(response):
    if response.method == "POST":
        form = CreateNewList(response.POST, response.FILES)
        if form.is_valid():
            experimentName = form.cleaned_data["experimentName"]
            adapter = form.cleaned_data["adapter"]
            sampleFile = form.cleaned_data["sampleFile"]
            humanGenome = form.cleaned_data["humanGenome"]
            mouseGenome = form.cleaned_data["mouseGenome"]

            # Read the contents of the uploaded sample file
            sample_file_content = sampleFile.read().decode('utf-8')

            # Process the sample file content: assuming "name (space) sample filepath" per line
            sample_data = []
            for line in sample_file_content.splitlines():
                if line.strip():  # Ignore empty lines
                    parts = line.split(' ', 1)  # Split at the first space
                    if len(parts) == 2:
                        sample_data.append((parts[0], parts[1]))  # (name, filepath)

            # Determine the genome based on the user selection
            genome = ""
            if mouseGenome:
                genome = "/blue/kotaro.fujii/a.rochette/GRCm39.genome.fa"
            elif humanGenome:
                genome = "/blue/kotaro.fujii/a.rochette/GRCh38.genome.fa"

            # Construct the shell script dynamically based on user input and sample file content
            script_content = f"""#!/bin/bash
#SBATCH --job-name=nextflow_processing    # Job name
#SBATCH --output=/blue/kotaro.fujii/a.rochette/nextflow_processed_riboseq/logs/output_%A_%a.out        # Standard output (%A=job ID, %a=array index)
#SBATCH --error=/blue/kotaro.fujii/a.rochette/nextflow_processed_riboseq/logs/error_%A_%a.err          # Standard error (%A=job ID, %a=array index)
#SBATCH --time=24:00:00                   # Time limit hrs:min:sec (adjust based on expected runtime)
#SBATCH --cpus-per-task=1                # Number of CPU cores per task (adjust if needed)
#SBATCH --mem-per-cpu=30gb               # Job memory request (adjust if needed)
#SBATCH --mail-type=END,FAIL             # Mail events (NONE, BEGIN, END, FAIL, ALL)
#SBATCH --mail-user=a.rochette@ufl.edu   # Where to send mail
#SBATCH --ntasks=1                       # Run on a single CPU
#SBATCH --qos=kotaro.fujii-b

module purge
module load java
module load nextflow/24.04.2
module load singularity/3.10.4
module load conda


# Define directories and input files
OUTPUT_DIR="/blue/kotaro.fujii/a.rochette/nextflow_processed_riboseq"
SAMPLESHEET="$OUTPUT_DIR/samplesheet.csv"  # The generated CSV file path
FASTA="{genome}"                 # Path to the selected genome file
GTF="/blue/kotaro.fujii/a.rochette/gencode.vM34.chr_patch_hapl_scaff.annotation.gtf"
CONTAMINANTS_FASTA="/blue/kotaro.fujii/a.rochette/rdna_mouse-48s.fasta"
LOG_DIR="${{OUTPUT_DIR}}/logs"
mkdir -p "$LOG_DIR"

# Install RiboFlow dependencies
git clone https://github.com/ribosomeprofiling/riboflow.git
conda env create -f riboflow/environment.yaml

# Activate the ribo environment
conda activate ribo

# Get RiboFlow repository
mkdir rf_test_run && cd rf_test_run
git clone https://github.com/ribosomeprofiling/riboflow.git
cd riboflow

# Write user data into project.yaml file in riboflow directory


# Finally run RiboFlow
nextflow RiboFlow.groovy -params-file project.yaml
"""

            # Add user-specific experiment information
            script_content += f"# Further commands to process {experimentName} can go here...\n"

            # Return the generated script as a downloadable file
            response = HttpResponse(script_content, content_type='application/x-sh')
            response['Content-Disposition'] = f'attachment; filename="{experimentName}_script.sh"'
            return response
    else:
        form = CreateNewList()

    all_inputs = ProcessingInput.objects.all()

    return render(response, "riboApp/preprocess.html", {"form": form, "all_inputs": all_inputs})


# def preProcess(response):
#     if response.method == "POST":
#         form = CreateNewList(response.POST, response.FILES)
#         if form.is_valid():
#             experimentName = form.cleaned_data["experimentName"]
#             adapter = form.cleaned_data["adapter"]
#             sampleFile = form.cleaned_data["sampleFile"]
#             humanGenome = form.cleaned_data["humanGenome"]
#             mouseGenome = form.cleaned_data["mouseGenome"]
#
#             ProcessingInput.objects.create(
#                 experimentName=experimentName,
#                 adapter=adapter,
#                 sampleFile=sampleFile,
#                 humanGenome=humanGenome,
#                 mouseGenome=mouseGenome
#             )
#
#             return HttpResponseRedirect('/preprocess/')
#     else:
#         form = CreateNewList()
#
#     all_inputs = ProcessingInput.objects.all()
#
#     return render(response, "riboApp/preprocess.html", {"form": form, "all_inputs": all_inputs})

def download_file(response, file_name):
    file_path = os.path.join('media/uploads', file_name)

    if not os.path.exists(file_path):
        raise Http404("File not found")

    mime_type, _ = mimetypes.guess_type(file_path)
    with open(file_path, 'rb') as f:
        response = HttpResponse(f, content_type=mime_type or 'application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename={file_name}'
        return response

def home(response):
    return render(response, 'riboApp/home.html')

def analyze(response):
    return render(response, 'riboApp/analyze.html')

def locatePsites(response):
    return render(response, 'riboApp/psites.html')
