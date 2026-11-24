# Dataset experimental D1

`manifest.json` publica la revisión y los bloques admitidos. Los Parquet de `originals/` contienen las observaciones originales. `embeddings/` contiene identificadores, claves exactas, perfiles de modelo y direcciones certificadas. Los vectores se consultan en los almacenes de D1.

Para una lectura operativa, partir del manifiesto y usar `validate.read_verified_block` para verificar el recibo de cada bloque. La consulta de un vector debe usar el ID completo del perfil y la clave exacta. La referencia ProtT5 usa la lista de shards del manifiesto y el offset. SecondaryBERT usa la clave C/H/E del índice certificado. Las dos referencias se resuelven con el lector D1 existente, `data_pipeline.nap_cnb_v2_batches.OriginalBatches`.

`schema.json` documenta identidades, filiación y estados del registro. El ámbito publicado contiene originales y referencias acreditadas. Las altas futuras requieren evidencia de identidad y correspondencia para su perfil antes de admitir una referencia. El estado `calculated` por sí solo carece de esa garantía.

Desde la raíz del repositorio, con el Python de `nap_env`:

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
ionice -c 3 nice -n 19 python -B results/nap_cnb_v2_d1_experimental/build.py
python -B results/nap_cnb_v2_d1_experimental/test_dataset.py -v
ionice -c 3 nice -n 19 python -B results/nap_cnb_v2_d1_experimental/validate.py
```

El constructor publica cada bloque con un recibo SHA-256 y escribe el manifiesto final tras validar cobertura, unicidad y grupos. Una reejecución conserva los bloques de la misma revisión cuyo recibo y contenido coinciden. Las pruebas ejercitan la recuperación de un bloque incompleto o corrupto en un directorio temporal.

`calculation_log.sqlite` registra estados y procedencia de cálculos mediante el esquema `calculation_log.sql`. Se inicializó vacío. Una entrada del registro de cálculos requiere una acreditación independiente antes de incorporarse a una revisión publicada.

### Filiación con datos sintéticos

`synthetic_lineage.py` admite registros de prueba con identificadores opacos `synthetic:`. La base temporal guarda solo registros derivados. Los originales y las referencias de prueba se proporcionan como fixtures, y su revisión queda fijada al abrir la base. Cada alta conserva grupo y partición del padre, y marca la etiqueta como `inherited_only`. Cada modalidad registra disponibilidad verificada, pendiente o ausente. Las referencias verificadas exigen identidad exacta, perfil, huella de configuración y dirección acreditada en el fixture. La repetición de un alta idéntica devuelve el mismo ID y un conflicto revierte el lote.

Para ejecutar las pruebas sintéticas, usar el Python de `nap_env` desde la raíz:

```sh
python -B -m unittest discover -s results/nap_cnb_v2_d1_experimental -p 'test_*.py' -v
```

Este banco de pruebas opera con bases temporales. El manifiesto publicado conserva su alcance de originales D1.

### Estados de representación y evaluación offline

En el banco de pruebas, `SyntheticLineage.update_embedding` registra un evento independiente por modalidad. El mismo `operation_id` permite repetir la operación si sus parámetros coinciden. `history(record_id)` devuelve los cambios con sus motivos y referencias acreditadas. Una invalidación exige un motivo explícito y conserva la referencia previa en el historial.

`evaluate_predictions.py` compara archivos de predicciones ya producidos. Cada Parquet debe incluir `observation_id` o la pareja `sequence` y `secondary_structure`, además de `label_global` y `logit`. El JSON de procedencia requiere `selection_split: "VALIDATION"`, `test_used_for_model_selection: false`, `checkpoint_sha256`, `config_sha256` y `prediction_split` con el nombre de la partición de cada archivo. Los hashes del checkpoint y de la configuración deben coincidir en ambas fases.

Con el Python de `nap_env`, desde la raíz:

```sh
python -B results/nap_cnb_v2_d1_experimental/evaluate_predictions.py select E3 validation.parquet validation_provenance.json selection.json
python -B results/nap_cnb_v2_d1_experimental/evaluate_predictions.py evaluate E3 test.parquet test_provenance.json comparison.json --selection selection.json
```

Para E4, sustituir el identificador del experimento. El evaluador fija el umbral con VALIDATION, exige cobertura exacta de TEST original para ambos archivos comparados y rechaza duplicados. El uso de TEST en ejecuciones externas se controla mediante la declaración del productor y la vinculación de ambos archivos al checkpoint y la configuración declarados. `experiment_status.json` registra el estado actual.

Si se proporcionan los archivos del checkpoint y de configuración, añadir `--checkpoint RUTA --config RUTA` en ambas fases. El evaluador verifica sus hashes sin cargar el modelo. Si solo se entregan hashes declarados, el recibo identifica ese alcance. Si el Parquet incluye ambas formas de identidad o la columna `split`, deben coincidir con la identidad y la partición declaradas.
