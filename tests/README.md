# CPU regression tests

From the project root with `nap_env` activated:

```bash
python -m unittest discover -s tests -t . -v
```

The suite uses standard-library `unittest`, so it adds no package to the research environment. Tests create synthetic inputs in temporary directories and use the real loader, converter, scaler and model. No original datasets, trained weights or GPU are required. Archive tests need the `zstd` executable and are skipped when it is unavailable.

Coverage includes classification coordinates, BLOSUM substitutions, stratified row splits, separate/concatenated loader equivalence, TRAIN-only weighted normalization, a CPU optimizer step, repeated group IDs, invalid metadata/dimensions, output checksums, interrupted conversion and writer exclusion.

Archive tests inject failures during compression, after archive publication and before original removal. They also check source modification, corrupt archives, insufficient space, repeated execution, symlink rejection and checksum verification despite an `ARCHIVED.json` marker. These are controlled software-failure tests, not power-loss or filesystem-durability tests.

## Completed-output integrity

Completed outputs are rehashed even when no archival is requested. New per-chunk records include independent SHA-256 hashes for labels, group IDs and split IDs; tests alter each array without changing its shape and require verification to reject it.

Legacy records without metadata hashes are checked against original source metadata or its archived `original_sha256` record. Missing independent evidence is an error. Verification does not modify outputs. These regressions run as ordinary tests without `expectedFailure`.
