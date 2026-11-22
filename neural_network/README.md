# Neural networks

`MLP/` contains the classifier using ProtT5 and SecondaryBERT embeddings. Pretrained embedding-model weights are in `../model/`; embedding-generation tools are in `../data_pipeline/`.

See [MLP instructions](MLP/README.md) for training, scaling and outputs.

[Logistic regression](logistic_regression/README.md) provides a linear classifier using the same 50/50 sampling, optimizer, scheduler and evaluation engine as MLP, on one GPU or CPU.
