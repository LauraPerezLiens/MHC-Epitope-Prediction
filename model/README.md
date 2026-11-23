# Model artifacts

Only this README is versioned. Weights, tokenizers, model configurations and local validation outputs are excluded from Git and are not provided by cloning the repository.

| Directory | Contents | Used by |
|---|---|---|
| `unet_c_ensemble/` | ProteinUnet TensorFlow SavedModel: `saved_model.pb` and `variables/` | [Secondary structure prediction](../data_pipeline/scripts/secondary_structure_prediction/README.md) |
| `secondary_bert/` | BERT MLM weights, configuration, tokenizer and local validation metrics | [Structural embeddings](../data_pipeline/scripts/embeddings/README.md) |

ProteinUnet prediction uses `proteinunet_env`; SecondaryBERT uses `nap_env`. See [environment setup](../env/README.md).

Scripts default to these directories relative to the project location. Keep SecondaryBERT weights, configuration and tokenizer together. The historical ProtT5 generator loads its checkpoint through Hugging Face. The v2 generator loads a local checkpoint specified by `--checkpoint` and checks the files against `--hashes`. These hashes establish checkpoint file identity. Historical vector–sequence correspondence requires separate evidence.

See the [model inventory](../data_pipeline/docs/data_and_models.md) for architecture details and recorded validation results.
