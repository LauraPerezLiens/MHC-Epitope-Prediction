# CPU regression tests

From the project root with `nap_env` activated:

```bash
python -m unittest discover -s tests -t . -v
```

The suite uses standard-library `unittest`, so it adds no package to the research environment. Tests create synthetic inputs in temporary directories and use the real loader, converter, scaler and model. No original datasets, trained weights or GPU are required. Archive tests need the `zstd` executable and are skipped when it is unavailable.

Coverage includes classification coordinates, BLOSUM substitutions, stratified row splits, separate/concatenated loader equivalence, TRAIN-only weighted normalization, a CPU optimizer step, repeated group IDs, invalid metadata/dimensions, output checksums, interrupted conversion and writer exclusion.

Archive tests inject failures during compression, after archive publication and before original removal. They also check source modification, corrupt archives, insufficient space, repeated execution, symlink rejection and checksum verification despite an `ARCHIVED.json` marker. These are controlled software-failure tests, not power-loss or filesystem-durability tests.

## Completed-output integrity

Normal completed-output checks hash metadata and inspect feature counts, sizes, shapes and dtypes. New conversion records retain feature modification times: changed timestamps trigger feature rehashing; unchanged large payloads are not read. Quick checks cannot detect same-size feature corruption with a preserved timestamp. Historical records without timestamps receive structural feature checks only.

`--verify-only --output PATH` reads all feature and metadata content and verifies SHA-256 without writing or archiving. Legacy metadata records require independent original files or archived checksum records; missing evidence is an error. Tests cover both modes, the explicit CLI, preservation of file content, exclusion of active writers, refusal before payload reads when `.writer.lock` is missing, and a writer recreating that lock.

## Preparation and checkpoint recovery

Launcher tests run only against temporary synthetic trees. They check missing/invalid splits, missing metadata even when a scaler exists, fitting only a missing synthetic scaler, preserving an existing scaler and validating concatenated data without fitting it again.

Preparation-cost regressions ensure that existing-scaler checks skip full CSV parsing, explicit requests and missing scalers require it, and every metadata value is still checked. Missing files or invalid CSV headers remain errors.

The CPU model test performs two optimizer steps across an actual temporary checkpoint. It restores model, optimizer, scheduler and CPU RNG state and compares the resumed step with an uninterrupted step. It does not use production checkpoints or change checkpoint-selection policy.

## Reconstruction and structural recovery

Reconstruction tests compare each synthetic window with its expected coordinates, sequence and label. Structural recovery tests inject a failure before the final directory rename and verify that a fresh invocation can publish after staging is cleaned up. The sparse-window fixture checks each row against its reference and verifies the expected count. The gap inventory records counts by protein, so substituting a different valid position in the source can preserve every check.

## CI and local reproduction

The [CPU workflow](../.github/workflows/cpu-checks.yml) installs a small independent environment and runs syntax checks, focused Ruff correctness rules, the unit suite and the synthetic example. See [environment setup](../env/README.md#cpu-tests-and-ci) for the exact local commands. GitHub-hosted execution is only confirmed after the workflow has actually run there.
