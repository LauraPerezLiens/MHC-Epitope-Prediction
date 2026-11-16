# NAP-CNB | Protein-Based Epitope Prediction with Deep Learning

**A computational bioinformatics project for developing machine learning approaches to MHC epitope prediction, integrating protein sequence information, secondary structure representations, and large-scale data processing.**

This repository contains the data processing, feature generation, and neural network training workflows developed as part of ongoing doctoral research in computational immunology.

The project focuses on building and evaluating computational approaches for identifying potential immune targets, with applications in cancer immunotherapy research.

**Core technologies:** Python · PyTorch · Protein Language Models · Bioinformatics · Machine Learning · GPU Computing

---

## Project Overview

Predicting immunologically relevant epitopes is an important challenge in computational immunology.

This project investigates how complementary representations of protein primary and secondary structure can be integrated into neural network models for epitope classification.

The workflow covers several stages:

1. Acquisition and processing of immunological datasets.
2. Protein sequence retrieval and epitope classification.
3. Sequence-based data augmentation.
4. Protein secondary structure prediction.
5. Generation of primary and secondary structure embeddings.
6. Large-scale dataset preparation and feature normalization.
7. Neural network training and evaluation.

The repository includes both experimental research code and documentation describing the methodology and development process.

## Computational Workflow

```text
              Immunological data (IEDB)
                         |
                         v
            Protein sequence retrieval
                         |
                         v
           Epitope classification
                         |
                         v
              25-aa sequence windows
                         |
              +----------+----------+
              |                     |
              v                     v
       BLOSUM62-based         Secondary structure
       augmentation              prediction
              |                     |
              v                     v
            ProtT5             SecondaryBERT
              |                     |
              v                     v
       1024-dimensional       768-dimensional
          embeddings             embeddings
              |                     |
              +----------+----------+
                         |
                         v
               Feature preparation
                         |
                         v
             Dataset shuffling and
             TRAIN/VALIDATION/TEST
                    splitting
                         |
                         v
              Feature normalization
                         |
                         v
              Neural network training
                         |
                         v
                  Evaluation
```

The repository also includes a feature-concatenation workflow. The current MLP loader processes the primary and secondary representations separately; direct training from the concatenated files requires an additional adaptation.

## Main Components

### 1. Data Acquisition and Classification

Immunological data are collected from the Immune Epitope Database (IEDB).

The processing pipeline retrieves parent protein sequences, validates sequence information, and generates labeled protein windows for downstream classification.

### 2. Data Augmentation

Protein sequence windows are augmented using amino acid substitutions guided by the BLOSUM62 substitution matrix.

This stage expands the training dataset and supports experiments with sequence variation.

The augmented sequences inherit their original labels, which is a modeling assumption rather than independent experimental validation.

### 3. Protein Representation Learning

Two complementary protein representations are investigated.

**Primary structure — ProtT5**

Protein sequences are transformed into numerical embeddings using a pretrained protein language model.

- Model: ProtT5
- Embedding dimension: 1,024
- Input: amino acid sequences

**Secondary structure — SecondaryBERT**

A separate transformer-based model is trained to learn representations of protein secondary structure.

- Input: secondary structure states
- Embedding dimension: 768
- Training approach: masked language modeling

The secondary structure workflow includes protein structure prediction, dataset construction, model training, and embedding validation.

### 4. Large-Scale Data Processing

The project includes custom Python workflows for processing large biological datasets.

Implemented operations include:

- Chunk-based dataset processing.
- Dataset shuffling.
- TRAIN/VALIDATION/TEST partitioning.
- Metadata generation and validation.
- Feature concatenation.
- Memory-conscious feature normalization.

These components support experiments with datasets that are too large to process entirely in memory.

### 5. Neural Network Development

The classification workflow uses multilayer perceptron (MLP) architectures implemented with PyTorch.

The repository includes:

- Custom dataset loading.
- Feature standardization.
- Layer normalization.
- GPU-based model training.
- Incremental training experiments.
- Model evaluation and experiment tracking.

The research is ongoing, and reported experimental results should be interpreted in the context of their respective dataset partitions and evaluation protocols.

## Repository Structure

| Directory | Description |
|---|---|
| `data_pipeline/` | Data acquisition, classification, augmentation, structure prediction, and embedding generation |
| `neural_network/MLP/` | Dataset loading, normalization, MLP training, and evaluation |
| `docs/` | Experimental history and research documentation |
| `env/` | Software environment specification |
| `data/` | Documentation of locally stored datasets |
| `reports/` | Data processing and validation reports |
| `logs/` | Documentation of operational logs |

Large datasets, model weights, checkpoints, and training outputs are excluded from version control.

## Installation

The repository provides a Conda environment specification.

```bash
conda env create -f env/nap_env.yml
conda activate nap_env
```

Some workflows require external datasets, pretrained models, substantial computational resources, and local path configuration.

Cloning the repository does not provide the complete research environment or all data required to reproduce the experiments.

## Documentation

Detailed information is available in the corresponding modules:

- [Data processing pipeline](data_pipeline/README.md)
- [Data processing steps](data_pipeline/scripts/README.md)
- [Neural network implementation](neural_network/MLP/README.md)
- [Experimental history](docs/RESUMEN_EXPERIMENTOS.md)
- [Data and model inventory](data_pipeline/docs/data_and_models.md)

## Research Status

**Status: Active research and development**

The repository documents an evolving research workflow.

Current development includes large-scale data preparation, protein representation learning, and neural network experiments.

Future work includes further model evaluation, methodological validation, and comparisons with established epitope prediction approaches.

## Evaluation Considerations

The experimental workflow has used random row-level dataset partitioning.

Consequently, related sequence windows, augmented variants, or proteins may appear across different partitions.

Results obtained using this strategy should not be interpreted as evidence of generalization to entirely unseen proteins.

Additional evaluation strategies are needed to assess generalization under more restrictive biological separation criteria.

## Research Context

Developed as part of doctoral research in computational biology and cancer immunotherapy at the Spanish National Centre for Biotechnology (CNB-CSIC).

The repository documents research code and computational workflows under active development. It is not presented as a clinically validated prediction tool.
