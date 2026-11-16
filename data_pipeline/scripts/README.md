# Data processing steps

Run documented commands from the `lperez_nn/` root. Use `nap_env` except for ProteinUnet prediction, which uses `proteinunet_env`; see [environment setup](../../env/README.md).

| Step | Module | Purpose |
|---|---|---|
| 1 | [data_download](data_download/README.md) | Download and deduplicate IEDB events. |
| 2 | [data_classification](data_classification/README.md) | Retrieve proteins and label windows. |
| 3 | [data_augmentation](data_augmentation/README.md) | Generate BLOSUM62 variants. |
| 4 | [secondary_structure_prediction](secondary_structure_prediction/README.md) | Predict and map secondary structure. |
| 5 | [secondaryBERT](secondaryBERT/README.md) | Prepare structural training data and train the representation model. |
| 6 | [embeddings](embeddings/README.md) | Generate ProtT5 and SecondaryBERT representations. |
| 7 | [data_shuffling](data_shuffling/README.md) | Globally shuffle rows and recover interrupted runs. |
| 8 | [data_splitting](data_splitting/README.md) | Assign splits, prepare metadata and validate. |
| 9 | [embedding_concatenation](embedding_concatenation/README.md) | Combine both representations. |
| 10 | [data_archiving](data_archiving/README.md) | Compress consumed sources with full verification; overlaps conversion where safe. |

Steps 3 and 4 are complementary branches. SecondaryBERT has its own pretraining workflow. The classifier scaler and launchers are in `../../neural_network/MLP/`. The MLP loader reads concatenated chunks directly; original sources can be archived after verified conversion.

Shuffling, splits, metadata and scaling are already complete for the current dataset. Do not repeat them on data used by an active process.
