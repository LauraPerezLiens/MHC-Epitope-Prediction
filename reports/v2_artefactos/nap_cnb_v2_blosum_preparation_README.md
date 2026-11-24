# Preparación de metadatos BLOSUM62

`inspect_data.py` lee la matriz BLOSUM62 de Biopython y recorre por bloques la columna `sequence` del Parquet original. Verifica el SHA-256 del Parquet contra su manifiesto antes de contar símbolos. `statistics.json` conserva el alfabeto, la diagonal, las distribuciones completas y el censo de D1. Los recuentos de residuos corresponden a observaciones, por lo que una primaria con varias representaciones contribuye una vez por fila.

## Esquema SQLite

| Tabla | Contenido |
|---|---|
| `source_manifest` | Ruta y SHA-256 del Parquet de observaciones originales. |
| `original_observation` | Proyección de claves binarias de 50 bytes, identificadas conjuntamente con el SHA-256 de su origen. |
| `experiment` | Identificador, revisión de origen, método, versión y SHA-256 de la matriz, parámetros JSON, semilla y procedencia. |
| `related_record` | Identificador propio, referencia a experimento y observación en una misma revisión, y estado de validación. |
| `artifact_reference` | Rol, URI y SHA-256 de cada artefacto asociado a un registro. |

El Parquet es la fuente de verdad de los identificadores. SQLite aplica las claves foráneas dentro de la base mediante la proyección `original_observation`. La prueba carga en memoria un identificador real del Parquet y verifica el rechazo de una clave inexistente y de una referencia que mezcla revisiones. Para cada conexión SQLite se debe activar `PRAGMA foreign_keys = ON` antes de iniciar una transacción. El DDL base se amplía con `catalog_schema.sql`. La proyección persistente se guarda en `d1_original_catalog.sqlite`. Las tablas de experimentos, registros relacionados y artefactos se entregan vacías.

## Reproducción

Con el entorno `nap_env` y desde la raíz del repositorio:

```bash
out=results/nap_cnb_v2_blosum_preparation
python "$out/inspect_data.py" > "$out/statistics.json"
python "$out/test_preparation.py"
```

Los resultados están en `tests.log`. El [informe de preparación](../../reports/experiments/d1_blosum_preparation.md) resume la interpretación y el alcance.

## Catálogo persistente de originales

`build_catalog.py` lee el Parquet por bloques de hasta 100.000 filas y ordena un
índice compacto de 51 bytes por observación. Carga SQLite por lotes en un
directorio temporal dentro del directorio de salida. Tras comprobar la base
contra todas las filas originales y ejecutar los PRAGMA de integridad, publica
el archivo mediante un enlace que falla si el destino ya existe. Una ejecución
con el catálogo presente verifica en modo lectura su contenido y procedencia.

La columna virtual `original_sequence_id` extrae los primeros 25 bytes del
identificador de observación. El catálogo almacena la partición como campo
obligatorio y conserva la clave compuesta del esquema base.
`catalog_metadata` registra la huella SHA-256 del JSON del manifiesto como
identificador de revisión, la huella del Parquet, la fecha UTC y los recuentos.

Para construir o volver a verificar con el entorno `nap_env`:

```bash
python results/nap_cnb_v2_blosum_preparation/build_catalog.py
python results/nap_cnb_v2_blosum_preparation/test_preparation.py
```
