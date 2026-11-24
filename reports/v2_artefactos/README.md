# Informes y manifiestos de los artefactos v2 retirados

197 ficheros, 1,1 MB. Es **lo único que queda** de los 158 GB de artefactos de datos de la línea NAP-CNB v2, borrados el 24 de noviembre de 2026.

## Por qué

D1 quedó certificado y el proyecto pasó de auditar a corregir. Los artefactos eran datos reconstruibles ejecutando el pipeline; sus informes, en cambio, documentan **qué se midió, con qué configuración y con qué resultado**, y eso no se reconstruye.

## Qué se retiró

| Directorio original | Tamaño | Qué era |
|---|---:|---|
| `nap_cnb_v2_prott5` | 56 G | 146 shards de embeddings ProtT5, 14.530.324 vectores |
| `nap_cnb_v2_d1_materialized` | 99 G | D1 materializado en bloques NPY + Parquet |
| `nap_cnb_v2_phase1` | 1,5 G | Ventanas originales por familia y estructura base |
| `nap_cnb_v2_dataset_views` | 852 M | Vista global D1 y manifiestos de partición |
| `nap_cnb_v2_secondarybert` | 273 M | Índice SQLite de SecondaryBERT |
| `nap_cnb_v2_blosum_preparation` | 561 M | Inventario y recuperación del histórico BLOSUM |
| `nap_cnb_v2_blosum_materialized` | 481 M | Piloto H2-L de variantes |
| `nap_cnb_v2_d1_experimental` | 289 M | Catálogo SQLite de D1 y estado de experimentos |
| `nap_cnb_v2_d1_original_manifest` | 189 M | Manifiesto certificado de D1 |
| `nap_cnb_v2_phase1_structure` | 26 M | Detalle de huecos estructurales |

## Cómo leerlo

Los nombres conservan la ruta original con `__` en lugar de `/`:

```
nap_cnb_v2_prott5_final_report.md        ← results/nap_cnb_v2_prott5/final_report.md
nap_cnb_v2_dataset_views_d1_manifest.json ← results/nap_cnb_v2_dataset_views/d1_manifest.json
```

**Los manifiestos conservan sus SHA-256**, que es lo que exige §19 del documento maestro: una medición sin su huella de procedencia no es verificable después.

## Lo que NO se retiró

Los resultados de modelo siguen en `results/`: E1, E2, la ablación por modalidad, la partición por componentes de proteína y las ejecuciones históricas de LR y MLP. Sus números están en [`results/RESULTADOS.md`](../../results/RESULTADOS.md).

## Si hay que reconstruirlos

El pipeline sigue completo en `data_pipeline/`. El orden es: `rebuild_iedb/` → `final_selection.py` → `prott5_v2.py` y `secondarybert_v2.py` → `dataset_views.py` → `split_nap_cnb_v2.py`. Los parámetros exactos están en [`docs/PIPELINE.md`](../../docs/PIPELINE.md).

**Coste conocido:** regenerar ProtT5 son ~7 h de una RTX 3090 a 572 secuencias/s.
