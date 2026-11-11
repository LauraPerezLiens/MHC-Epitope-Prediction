# Runtime environment

`nap_env.yml` records the Conda environment used by this project.

```bash
conda env create -f env/nap_env.yml
conda activate nap_env
```

Launchers accept `PYTHON` to select another interpreter. Moving code does not install or change dependencies; running processes retain their original interpreter.
