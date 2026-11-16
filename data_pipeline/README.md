# Data pipeline

Prepare IEDB epitope datasets and protein representations for the [MLP classifier](../neural_network/MLP/README.md).

```text
IEDB positive MHC / T-cell assays (human and mouse)
  → parent-protein retrieval and validation
  → labeled 25-aa windows
      ├── BLOSUM62 variants → ProtT5 (1,024 features)
      └── ProteinUnet predictions → SecondaryBERT (768 features per group)
  → global row shuffle → splits and metadata
  → feature concatenation → MLP normalization, training and evaluation
```

SecondaryBERT is pretrained separately:

```text
UniRef50 → MMseqs2 clustering at 30% identity → FASTA chunks
  → ProteinUnet → C/H/E Parquet splits → BERT masked-language modeling
```

“UniRef30” names the local clustered representative set, not an official UniRef release.

## Modules

| Directory | Purpose |
|---|---|
| [data_download](scripts/data_download/README.md) | Download and deduplicate positive IEDB events |
| [data_classification](scripts/data_classification/README.md) | Retrieve parent proteins and label windows |
| [data_augmentation](scripts/data_augmentation/README.md) | Generate single-substitution BLOSUM62 variants |
| [secondary_structure_prediction](scripts/secondary_structure_prediction/README.md) | Predict protein structure and map it to windows |
| [secondaryBERT](scripts/secondaryBERT/README.md) | Build structural datasets, pretrain and validate BERT |
| [embeddings](scripts/embeddings/README.md) | Generate and check ProtT5 and SecondaryBERT features |
| [data_shuffling](scripts/data_shuffling/README.md) | Shuffle rows and recover interrupted runs |
| [data_splitting](scripts/data_splitting/README.md) | Assign splits and validate compact metadata |
| [embedding_concatenation](scripts/embedding_concatenation/README.md) | Combine both representations |
| [data_archiving](scripts/data_archiving/README.md) | Compress and verify consumed sources |

See [processing steps](scripts/README.md) for execution order and the [data and model inventory](docs/data_and_models.md) for artifact formats and recorded validation results.

## Running the pipeline

Commands are run from the `lperez_nn/` project root unless stated otherwise. The [environment specification](../env/nap_env.yml) records the current `nap_env`. Run the two ProteinUnet prediction scripts with the separate [proteinunet_env](../env/proteinunet_env.yml), which pins TensorFlow/Keras compatible with the saved model. See [environment setup](../env/README.md).

Datasets and weights are excluded from Git. Archived inputs must be restored before rerunning earlier stages; see [local data](../data/README.md). Default data and model paths are resolved from each script’s location, so they do not depend on a username or the working directory. Existing CLI path options override those defaults.

## Dataset interpretation

- Positive windows fully contain a recorded positive epitope. Other windows are labeled negative, but are not experimentally verified negatives.
- BLOSUM variants inherit the original label and structural features; mutant structures are not predicted independently.
- IDs are local to each species/class/family dataset. Join branches by dataset and identifiers, not row order. A window containing several epitopes can produce several labeled examples.
- The current MLP split is by row and allows shared groups and proteins across splits. It does not measure generalization to unseen proteins.
