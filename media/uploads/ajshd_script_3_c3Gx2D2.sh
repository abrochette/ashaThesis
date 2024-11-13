#!/bin/bash
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
FASTA="/blue/kotaro.fujii/a.rochette/GRCm39.genome.fa"                 # Path to the selected genome file
GTF="/blue/kotaro.fujii/a.rochette/gencode.vM34.chr_patch_hapl_scaff.annotation.gtf"
CONTAMINANTS_FASTA="/blue/kotaro.fujii/a.rochette/rdna_mouse-48s.fasta"
LOG_DIR="${OUTPUT_DIR}/logs"
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
# Further commands to process ajshd can go here...
