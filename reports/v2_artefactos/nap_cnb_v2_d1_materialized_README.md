# D1 original materializado

`manifest.json` identifica la revisión D1, los recuentos certificados y los bloques completos. En `blocks/` cada JSON publica el par de archivos del bloque y sus SHA-256:

- `NNNN.npy` es una matriz de acceso directo, en orden C y float32 little-endian. Las primeras 1.024 columnas son ProtT5 y las últimas 768 son SecondaryBERT.
- `NNNN.parquet` conserva `observation_id`, `group_id`, `global_label` y `split`. Su fila de índice cero corresponde a la primera fila de la matriz. `group_id` es la primaria exacta según D1.
- Los bloques mantienen el orden de los grupos de filas de D1. Para trabajar con una partición, seleccionar las posiciones del Parquet antes de indexar su matriz NPY.

Abrir las matrices con `np.load(path, mmap_mode="r", allow_pickle=False)` y leer lotes usando los offsets de fila. Las características se guardan sin normalizar.

Para reanudar desde la raíz del repositorio, con el Python de `nap_env`:

```sh
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ionice -c 3 nice -n 19 python -B -u results/nap_cnb_v2_d1_materialized/materialize.py
```

Se reutilizan los bloques de la revisión cuyo recibo, tamaño y SHA-256 coinciden. El manifiesto final se publica tras comprobar cobertura y recuentos por partición. El proceso usa en solo lectura las copias locales de embeddings que se verificaron al preparar E1. Los vectores en SQLite y las claves SecondaryBERT se cotejan con el catálogo certificado.
