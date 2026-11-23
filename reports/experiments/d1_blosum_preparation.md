# NAP-CNB · Preparación estadística y de metadatos BLOSUM62

Se comprobó la matriz que referencia el repositorio, se censó el alfabeto de las 15.100.592 observaciones originales de D1 y se probó el esquema de metadatos. La preparación se limitó a la matriz, los datos originales y pruebas SQLite en memoria.

## Matriz y compatibilidad con D1

El repositorio carga `BLOSUM62` desde `Bio.Align.substitution_matrices` en `data_pipeline/scripts/data_augmentation/generate_blosum62_variants.py`. Se leyó la misma matriz directamente desde Biopython 1.86. El archivo de datos tiene SHA-256 `85510d3846ee6d5f4778e425cf8daf6e0dbb889b306f2d13434e1254780efb40`.

La matriz es simétrica, de **24 × 24**, con puntuaciones enteras de −4 a 11. El alfabeto es `ARNDCQEGHILKMFPSTWYVBZX*`. Incluye los 20 aminoácidos canónicos, los códigos ambiguos B y Z, el símbolo desconocido X y el símbolo de parada `*`. La diagonal canónica va de 4 a 11. Las entradas diagonales B, Z, X y `*` valen 4, 4, −1 y 1 respectivamente. La diagonal completa está en el registro estadístico.

Biopython ofrece puntuaciones explícitas para X. La consulta con un símbolo ajeno a la matriz produce un error de índice. El helper histórico del repositorio devuelve −4 si falla la consulta. En el manifiesto de D1 se contaron **377.514.800 posiciones** de 25 caracteres por fila. Todas pertenecen al alfabeto canónico, así que el tratamiento de símbolos adicionales no afecta la compatibilidad de estos originales.

## Distribución de puntuaciones

Los **190 pares canónicos distintos y sin orientación** excluyen la diagonal y cuentan una sola vez cada par simétrico.

| Puntuación | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Pares | 8 | 44 | 47 | 45 | 25 | 12 | 7 | 2 |

Hay 21 pares positivos (11,05 %), 25 con cero (13,16 %) y 144 negativos (75,79 %). BLOSUM62 resume frecuencias de sustitución en alineamientos mediante log-odds. Una puntuación positiva indica que el par se observa más a menudo de lo esperado según el modelo de fondo y suele corresponder a una sustitución conservadora. Una negativa indica menor frecuencia relativa y puede reflejar diferencias fisicoquímicas. Cero indica una frecuencia aproximadamente acorde con el fondo a la resolución de la matriz. Estas puntuaciones son propiedades de la matriz y carecen de información sobre la posición concreta o el contexto experimental de D1.

## Esquema y pruebas

El esquema SQLite asocia cada observación mediante su identificador binario y el SHA-256 del Parquet original. Una clave foránea compuesta mantiene la misma revisión de D1 en el experimento y en la observación. El esquema conserva método, versión y huella de matriz, parámetros, semilla, procedencia, referencias a artefactos y estado de validación.

**8 pruebas aprobadas**. Cubren carga, dimensiones, simetría, integridad y diagonal, símbolos desconocidos, compatibilidad con D1 y restricciones SQLite. Se probó una referencia a una observación real del Parquet, el rechazo de huérfanos y revisiones mezcladas, y las restricciones de unicidad, estado y metadatos. La sección siguiente documenta la carga persistente de identificadores originales. La incorporación de registros o artefactos futuros queda pendiente.

- [Esquema SQLite](../../results/nap_cnb_v2_blosum_preparation/schema.sql)
- [Estadísticas completas](../../results/nap_cnb_v2_blosum_preparation/statistics.json)
- [Pruebas](../../results/nap_cnb_v2_blosum_preparation/test_preparation.py) y [registro](../../results/nap_cnb_v2_blosum_preparation/tests.log)
- [Documentación y reproducción](../../results/nap_cnb_v2_blosum_preparation/README.md)

## Catálogo persistente de originales

La base [d1_original_catalog.sqlite](../../results/nap_cnb_v2_blosum_preparation/d1_original_catalog.sqlite) se creó el **23 de noviembre de 2026 a las 10:22:31 UTC** con el esquema base más [catalog_schema.sql](../../results/nap_cnb_v2_blosum_preparation/catalog_schema.sql), versión SQLite **2**. La clave principal conserva el par `(manifest_sha256, observation_id)`. El campo obligatorio `split` conserva la asignación certificada. La columna virtual `original_sequence_id` se obtiene del prefijo de 25 bytes del identificador y evita almacenar una segunda copia de la primaria. La base carece de columnas de embeddings.

| Partición | Observaciones |
|---|---:|
| TRAIN | 12.083.630 |
| VALIDATION | 1.507.558 |
| TEST | 1.509.404 |
| **Total** | **15.100.592** |

**Secuencias primarias únicas** · 14.530.324.

| Artefacto | SHA-256 |
|---|---|
| SQLite publicada | `fca9435fcf6268a404e46e2f4611bd40483d96439ba3ab3b5ce65530eaacfc17` |
| Parquet original | `5c90cddeab32d538e7b6d8ad1b73f7c2fd417f6e0c119660ac23f82b825e6c5f` |
| JSON del manifiesto, identificador de revisión | `2063fa8656d87fa10adcd0f8c5292574ee889950f582246094e2965ca7cf82cf` |

Se verificaron los identificadores no nulos, su unicidad, su correspondencia con la primaria y la consistencia de partición para las representaciones de una misma primaria. Se cotejaron las **15.100.592** filas de SQLite con sus identificadores y particiones en el Parquet. `PRAGMA integrity_check` devolvió `ok` y `PRAGMA foreign_key_check` devolvió cero infracciones. La clave foránea compuesta exige la misma revisión del Parquet en el experimento y la observación.

La carga por bloques de hasta 100.000 filas usó un índice de ordenación compacto, tomó **2 min 12 s**, alcanzó un pico RSS de **1,08 GiB** y produjo una base de **2,1 GiB**. Se publicó tras verificar la base temporal y volver a comprobar las huellas de ambos archivos fuente. Las huellas de E1 y E2, incluido el scaler, coincidieron con las publicadas.

La suite ampliada completó **12 pruebas**. Incluye inserción válida, clave duplicada, referencia inexistente, mezcla de revisiones, integridad referencial, interrupción durante la inserción y reejecución. En la prueba de interrupción, la transacción temporal quedó sin publicar y un intento posterior completó la carga. Una prueba adicional comprobó que una base incompatible preexistente conserva su huella. La carga completa terminó sin errores.

- [Constructor](../../results/nap_cnb_v2_blosum_preparation/build_catalog.py) y [registro de carga](../../results/nap_cnb_v2_blosum_preparation/catalog_build.log).
- [Registro de pruebas ampliadas](../../results/nap_cnb_v2_blosum_preparation/catalog_tests.log).

La reejecución completa verificó la base existente en modo lectura y obtuvo la misma huella SHA-256, metadatos y 15.100.592 filas. El resultado está en el [registro de reejecución](../../results/nap_cnb_v2_blosum_preparation/catalog_reexecution.log). Las huellas del código y de los esquemas están en [catalog_code.sha256](../../results/nap_cnb_v2_blosum_preparation/catalog_code.sha256).
