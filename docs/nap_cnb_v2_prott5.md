# ProtT5 para NAP-CNB v2

El módulo [prott5_v2.py](../data_pipeline/scripts/embeddings/primary_structure/prott5_v2.py) genera un embedding por primaria original exacta. Lee la selección y el inventario reutilizado, y escribe únicamente en el almacén indicado. La receta histórica se conserva junto al nuevo módulo para poder reproducir las auditorías.

## Inventario y claves

- El [inventario previo](../results/nap_cnb_v2_embedding_audit/missing_prott5_sequences.parquet) abarca las 14.530.324 secuencias de v2. El nombre del fichero refleja que en la auditoría todas quedaron pendientes de reutilización certificada. El generador usa sus columnas de secuencia y frecuencia.
- El identificador es la primaria cruda exacta. La longitud y el SHA-256 se calculan directamente cuando se consulta la clave. El ordinal físico del Parquet se vincula a su SHA-256 y solo sirve para localizar el vector en esta versión de almacenamiento.
- Una hipotética colisión SHA-256 se resuelve comparando las claves crudas y deteniendo la publicación hasta verificar el inventario. La escritura y las uniones se definen por las secuencias exactas.
- Join posterior con ventanas por primaria exacta. Con SecondaryBERT se une la cadena C/H/E exacta de cada ventana y su configuración validada. La misma primaria puede compartir ProtT5 y tener distintos SecondaryBERT. Las etiquetas siguen viniendo de los Parquet de v2.

## Configuración

Modelo `Rostlab/prot_t5_xl_half_uniref50-enc`, revisión `94a6abc029ae13029317b140b7424e012bf8dfbf`. La copia local persistente está en `model/prott5/94a6abc029ae13029317b140b7424e012bf8dfbf/`. Los pesos y archivos de tokenización se cotejan contra la auditoría 3A al cargar. [Huellas verificadas](../results/nap_cnb_v2_prott5_audit_3a/checkpoint_hashes.json)

Las primarias mantienen sus 25 caracteres originales. En la entrada del modelo, U, B y Z se convierten explícitamente a X, y X permanece X. Los demás caracteres fuera del alfabeto admitido se rechazan. Se separan residuos por espacios. SentencePiece legado genera 25 tokens de residuo y EOS, todos activos. En este conjunto de longitud fija se usan 26 posiciones activas por fila y no hace falta padding. El último estado oculto del encoder se promedia en float32 con EOS incluido. Se usa FP16 para el cálculo del encoder y float32 para los vectores. El modelo está en modo evaluación.

Se fija atención eager, algoritmos deterministas, TF32 deshabilitado y reducción FP16 de precisión reducida deshabilitada. La semilla del piloto es 20261119. El manifiesto incluye versiones, hashes, configuración, código, tamaño de lote y ordinals del piloto. La recomendación medida es **batch 256**.

## Preparar la sesión en Pascal

Desde la raíz del proyecto, con el entorno Conda `nap_env` activado:

```bash
PY=python
M=data_pipeline.scripts.embeddings.primary_structure.prott5_v2
CKPT=model/prott5/94a6abc029ae13029317b140b7424e012bf8dfbf
P=results/nap_cnb_v2_prott5
export PYTHONPATH="$PWD/.venv/prott5-v2-deps:."
nvidia-smi
export CUDA_VISIBLE_DEVICES=2
```

En el piloto se usó la GPU física 2. Antes de una nueva ejecución, comprobar que la elegida está libre y exponer solo esa GPU. El entorno base medido contiene PyTorch 2.14.0 y CUDA 13.0. La capa de dependencias del piloto se copió byte a byte a `.venv/prott5-v2-deps`. Si faltara esa copia, recrear la capa aislada con los mismos paquetes y comprobar las versiones contra el manifiesto:

```bash
"$PY" -m pip install --no-deps --target "$PWD/.venv/prott5-v2-deps" \
  'transformers==4.57.6' 'huggingface-hub==0.36.0' \
  'tokenizers==0.22.2' 'sentencepiece==0.2.3'
```

## Consultar, ejecutar y verificar

```bash
# Verifica todas las claves, longitudes, frecuencias y hashes, sin cargar el modelo.
"$PY" -m "$M" inventory

# Benchmark acotado de lotes 32/128/256 y control de precisión.
"$PY" -m "$M" benchmark --checkpoint "$CKPT"

# Piloto reproducible. --max-batches 3 permite comprobar una parada controlada.
"$PY" -m "$M" pilot --checkpoint "$CKPT" --output "$P/pilot" --batch-size 256
"$PY" -m "$M" progress --output "$P/pilot"
"$PY" -m "$M" verify --output "$P/pilot"
"$PY" -m "$M" repeat --checkpoint "$CKPT" --output "$P/pilot"

# Consulta por ID exacto. Devuelve SHA-256, ordinal, shard y fila de la ruta completa.
"$PY" -m "$M" locate --sequence MMKFKPNQTRTYDREGFKKRAACLC
```

### Comando completo y reanudación

```bash
"$PY" -m "$M" full --checkpoint "$CKPT" \
  --output "$P/final" --batch-size 256
```

Reanudar con el mismo comando. `progress` usa una conexión SQLite de solo lectura y muestra los lotes confirmados. `verify` comprueba las formas, finitud, claves y digests de cada lote confirmado con el escritor detenido. Un cambio de configuración o de código durante una reanudación requiere un almacén nuevo o una migración explícita.

## Almacenamiento y reanudación

Los shards NPY de 100.000 filas son mmap de float32 little-endian. La selección completa tendría **146 shards** y el último sería parcial por tamaño. Cada lote se valida, se sincroniza el archivo y se confirma en una transacción SQLite con un SHA-256 que vincula las claves ordenadas y los bytes de los vectores. Los lectores deben consultar `progress.sqlite` para decidir si una fila está confirmada. Al terminar el almacén, todos los rangos están confirmados y pueden leerse por shard y fila.

La comprobación en cada reanudación conserva los lotes válidos y detiene el proceso ante bytes alterados, sin sobrescribir lotes confirmados. Un corte entre inferencia y confirmación puede repetir **hasta un lote no confirmado**. Se necesita un solo escritor por almacén. Para un lector por lotes, cargar una vez el catálogo Arrow, resolver las claves exactas con `index_in` y agrupar las lecturas mmap por shard. No se materializa una dirección por ventana.

Una futura ejecución paralela puede repartir intervalos disjuntos de shards y registrar productos independientes con el mismo manifiesto. La recolección comprobaría rangos, hashes y configuración. Esa opción requiere un benchmark de E/S y coordinación de rangos. La CLI actual está preparada para **una GPU**.

## SecondaryBERT

La auditoría inicial verificó 1.819.032 estructuras únicas y 49.083.724 ventanas. Quedaron entonces 28.404 claves pendientes. La [fase 3C cerrada](nap_cnb_v2_secondarybert.md) documenta su cobertura posterior. La relación con ProtT5 y las etiquetas se resuelve por cada modalidad antes de considerar concatenación. [Auditoría de embeddings](../results/nap_cnb_v2_embedding_audit/embedding_audit_report.md)

[Informe del piloto](../results/nap_cnb_v2_prott5/pilot_report.md) · [Inventario y propuesta de organización](nap_cnb_v2_organizacion.md)


## Registro del lanzamiento autorizado

La ejecución completa se inició el **19 de noviembre de 2026 a las 13:41 CET**, en la sesión persistente `nap-prott5-v2`. El primer PID del generador fue `3984594`. El almacén en `results/nap_cnb_v2_prott5/final/` conserva la configuración del piloto, con el inventario completo. La sesión añade al log progreso confirmado, recursos y ETA. Tras la generación, verifica el almacén al reabrirlo, comprueba el inventario y publica el informe final con el estado real.

```bash
tmux attach -t nap-prott5-v2
tail -f results/nap_cnb_v2_prott5/full_run.log
python \
  -m data_pipeline.scripts.embeddings.primary_structure.prott5_v2 progress \
  --output results/nap_cnb_v2_prott5/final
```

Para una incidencia, consultar primero el log y verificar los lotes confirmados con el escritor detenido. El panel tmux se conserva al salir. Si está detenido y la incidencia es recuperable, se puede relanzar el comando original del panel con `tmux respawn-pane -t nap-prott5-v2:0.0`. El generador verifica y conserva los lotes válidos del almacén existente. Una inconsistencia de hashes, configuración o datos requiere investigación antes de reanudar.
