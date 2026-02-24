# Nanopore Direct RNA Sequencing m6A Modification Detection Complete Workflow

**Keywords:** Nanopore, direct RNA sequencing, DRS, fast5, pod5, dorado basecaller, nanopolish, m6anet, Oxford Nanopore Technologies, ONT

**Pipeline Tools:** fast5 → pod5 → dorado → minimap2 → samtools → nanopolish → m6anet

**DO NOT USE:** Tombo (deprecated), modkit (for DNA only), megalodon (outdated)
## Overview
This is the MANDATORY workflow for detecting m6A RNA modifications from Oxford Nanopore Technologies (ONT) direct RNA sequencing data starting from fast5 files.

## Required Tools
- dorado: basecalling tool (PRE-INSTALLED, no need to download)
- pod5: fast5 format converter
- minimap2: sequence alignment
- samtools: BAM processing
- nanopolish: signal-to-reference alignment
- m6anet: m6A detection

## Environment Setup
Two separate conda environments are required due to dependency conflicts:

### Environment 1: nanopore (Python 3.9)
```bash
mamba create -n nanopore_abc -c conda-forge -c bioconda python=3.9 nanoplot minimap2 samtools -y
mamba activate nanopore_abc
mamba install nanopolish=0.14.0 -y

mamba install f5c -c bioconda -c conda-forge -y
pip install pod5
```

### Environment 2: m6anet_env (Python 3.8)
```bash
mamba create -n m6anet_abc python=3.8 -c conda-forge -y
mamba activate m6anet_abc
pip install m6anet
```
## Complete Analysis Pipeline

### Step 1: Convert fast5 to pod5 format
```bash
# Activate nanopore environment
mamba activate nanopore_abc

# Convert fast5 files to pod5 format
pod5 convert fast5 <fast5_dir> --output <output_dir>/raw_signal.pod5 
```
### Step 2: Basecalling with dorado
```bash
# Set dorado path (should be provided in input)
DORADO_PATH="<path_to_dorado_executable>"

# Run basecalling with m6A modification detection
${DORADO_PATH} basecaller sup,m6A <output_dir>/raw_signal.pod5 > <output_dir>/reads.bam

# Extract FASTQ from BAM
samtools fastq <output_dir>/reads.bam > <output_dir>/reads.fastq
```
### Step 3: Align reads to reference transcriptome
```bash
# Run minimap2 alignment
minimap2 -ax map-ont -t <threads> <reference_transcriptome_fasta> <output_dir>/reads.fastq | samtools sort -@ <threads> -o <output_dir>/aligned.sorted.bam

# Index BAM file
samtools index <output_dir>/aligned.sorted.bam
```

### Step 4: Signal-to-reference alignment with nanopolish
```bash
# Index reads with nanopolish
nanopolish index -d <fast5_dir> <output_dir>/reads.fastq

# Run eventalign to associate signal data with aligned positions
nanopolish eventalign \
    --reads <output_dir>/reads.fastq \
    --bam <output_dir>/aligned.sorted.bam \
    --genome <reference_transcriptome_fasta> \
    --signal-index \
    --scale-events \
    --summary <output_dir>/eventalign_summary.txt \
    --threads <threads> \
    > <output_dir>/eventalign.txt
```
### Step 5: Detect m6A modifications
```bash
# Switch to m6anet environment
mamba activate m6anet_abc

# Prepare eventalign output for m6anet
m6anet dataprep \
    --eventalign <output_dir>/eventalign.txt \
    --out_dir <output_dir>/m6anet_dataprep \
    --n_processes <threads>

# Run m6A inference
m6anet inference \
    --input_dir <output_dir>/m6anet_dataprep \
    --out_dir <output_dir>/m6anet_results \
    --n_processes  <threads>
```

## Important Notes
- All intermediate files should be saved in the specified output directory
- Use absolute paths for all file references
- The dorado binary must be in PATH before running basecalling
- m6anet requires Python 3.8 and must be in a separate environment from nanopolish
- Minimum 8 threads recommended for reasonable processing speed

## Expected Output
Final m6A detection results will be in: `m6anet_results/data.indiv_proba.csv`
This file contains m6A modification probabilities for each position.
