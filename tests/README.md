# CPU regression tests

From the project root with `nap_env` activated:

```bash
python -m unittest discover -s tests -t . -v
```

The suite uses standard-library `unittest`, so it adds no package to the research environment. Tests create synthetic inputs in temporary directories and use the real loader, converter, scaler and model. No original datasets, trained weights or GPU are required. Archive tests need the `zstd` executable and are skipped when it is unavailable.

Coverage includes classification coordinates, BLOSUM substitutions, stratified row splits, separate/concatenated loader equivalence, TRAIN-only weighted normalization, a CPU optimizer step, repeated group IDs, invalid metadata/dimensions, output checksums, interrupted conversion and writer exclusion.

Archive tests inject failures during compression, after archive publication and before original removal. They also check source modification, corrupt archives, insufficient space, repeated execution, symlink rejection and checksum verification despite an `ARCHIVED.json` marker. These are controlled software-failure tests, not power-loss or filesystem-durability tests.

## Known verification gaps

Two tests are deliberately marked `expectedFailure` until the corresponding behavior is changed:

- A completed dataset can take the fast return path without rehashing corrupted features when archival is disabled.
- Completed-output verification checks metadata shape but does not detect changed label values with unchanged shape.

A run reporting `OK (expected failures=2)` confirms these limitations remain reproducible; it does not mean all intended integrity guarantees hold. The tests must be updated alongside a verified fix. Production behavior is unchanged by this test suite.
