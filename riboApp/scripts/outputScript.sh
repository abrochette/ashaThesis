#!/bin/bash
#SBATCH --job-name=riboflow_processing
#SBATCH --output=output_%A_%a.out   # Add filepath where output files from the job will go
#SBATCH --error=error_%A_%a.err   # Add filepath where error files will go
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=30gb    # Adjust accordingly based on size of sample files- check error file if your process fails, and try adding more memory as first method of troubleshooting
#SBATCH --mail-type=END,FAIL
#SBATCH --ntasks=1

module purge
module load java
module load nextflow/24.04.2
module load singularity/3.10.4
module load conda

# Edit and uncomment the line below to specify where process occurs
# cd your_home_directory

genome="{genome}"
filter="{filter}"
transcriptome="{transcriptome}"
regions="{regions}"
transcriptLengths="{transcriptLengths}"
experimentName="{experimentName}"
filePaths="{filePaths}"


git clone https://github.com/ribosomeprofiling/riboflow.git
conda env create -f riboflow/environment.yaml
conda activate ribo

mkdir rf_test_run && cd rf_test_run
git clone https://github.com/ribosomeprofiling/riboflow.git
cd riboflow


# Create output directory if not exists
mkdir -p "$LOG_DIR"

# Write variables to a YAML file
cat <<EOL > "${OUTPUT_DIR}/project.yaml"
# N E X T F L O W
##########################################################################
#####   SAMPLE RIBOFLOW ARGUMENTS FILE WITH RNASEQ AND METADATA   ########
##########################################################################

# Tested on  version 19.04.1

# Perform fastqc at several stages of the pipeline
do_fastqc: true

# Check existnece of fastq.gz files and bowtie2 reference files
do_check_file_existence : true

# Remove duplicate reads based on their length
# and mapped position
deduplicate: true

# If you have RNA-Seq data additionally,
# that you want to pair with your ribosome profiling data,
# you can set this flag to true
# AND PROVIDE RNA-Seq data
# under the key rnaseq in this file. See below.
# If you don't have RNA-Seq data, set this flag to false
do_rnaseq: true

# If you don't have metadata set do_metadata to false.
# If you have metadata, provide yaml files for the experiments
# under input -> metadata below.
do_metadata: true

# These arguments are used for clipping adapters by cutadapt.
# (see https://cutadapt.readthedocs.io/en/stable/guide.html )
clip_arguments: '-u 1 -a CTGTAGGCACCATCAAT --overlap=4 --trimmed-only --maximum-length=40 --minimum-length=15 --quality-cutoff=28'

# If you don't want to perform and adapter clipping,
# you can comment the above option and use the option below.
#clip_arguments: '--quality-cutoff=0'

# Transcriptome alignments are filtered based on mapping quality.
# This is the threshold that the alignments need to pass for
# downstream quantification
mapping_quality_cutoff: 2

###############################################################################
# Arguments for the aligner for
# corresponding steps
alignment_arguments:
   # bowtie2 arguments for rtRNA filtering step
   filter:        '-L 15 --no-unal --norc'

   # bowtie2 arguments for transcriptome alignment step
   transcriptome: '-L 15 --norc --no-unal'

   # hisat2 arguments
   # use -k 1 so that each aligned read is reported once.
   # otherwise, our read length analysis values might be inflated.
   genome: '--no-unal -k 1'

###############################################################################
# RiboPy parameters for ribo file generation.
ribo:
    ref_name:        "appris-v2"
    metagene_radius: 50
    left_span:       35
    right_span:      10
    read_length:
       min: 28
       max: 32
    coverage: true

###############################################################################
# Output folder settings
# These entries typically don't need modifications.
# Note that everything is placed as a subfolder under the *base* folder
# *base* gives the actual folder location
# The other parameters are folder names that are going to be under the *base*
output:
   individual_lane_directory: 'individual'
   merged_lane_directory: 'merged'
   intermediates:
      # base is the root folder for the intermediate files
      base: 'intermediates'
      clip: 'clip'
      log: 'log'
      transcriptome_alignment: 'transcriptome_alignment'
      filter: 'filter'
      genome_alignment: 'genome_alignment'
      bam_to_bed: 'bam_to_bed'
      quality_filter: 'quality_filter'
      genome_alignment: 'genome_alignment'
      # alignment_ribo folder contains the bed files
      # that are used as input to RiboPy to create ribo files.
      alignment_ribo: 'alignment_ribo'
   output:
      # base is the root folder for the output files
      base: 'output'
      log: 'log'
      fastqc: 'fastqc'
      ribo: 'ribo'

###############################################################################
# In this exapmle we have two experiments with the names
# GSM1606107 and GSM1606108
# These names are first introduced when providing fastq files
# for ribosome profiling data. (input -> fastq -> GSM1606107) and (input -> fastq -> GSM1606108)
#
# If metadata or RNA-Seq data are provided, they must match these names
# See below as an example.


input:
   reference:
   # filter indicates bowtie2 index files
   # * is used as a wild card to match all bowtie2 index files:
   # human_rtRNA.1.bt2, human_rtRNA.2.bt2, ....
      filter: "${filter}"

      # transcriptome indicates bowtie2 index files
      # Generated from isoform sequences.
      transcriptome: "${transcriptome}"

      # Main annotation file.
      # CDS and UTR regions are defined in this file.
      regions: "${regions}"

      # Transcript lengths
      transcript_lengths: "${transcriptLengths}"

      ## Genome Alignment Reference
      # Sequences that are NOT aligneod to the transcriptome
      # are mappoed to the genome
      # This parameter (and the corresponding step) is optional.
      # Comment the line below to skip this step
      #genome: "${genome}"

      # Reads NOT aligned to the genome are mapped to this reference
      # This parameter (and the corresponding step) is optional.
      # Comment the line below to skip this step
      #post_genome: ./rf_sample_data/post_genome/post_genome*

   # This will be prefixed to the file paths below
   # You can leave it as empty "" if you provide complete paths.
   fastq_base: ""
   fastq:
       "${filePaths}"
EOL


nextflow RiboFlow.groovy -params-file project.yaml