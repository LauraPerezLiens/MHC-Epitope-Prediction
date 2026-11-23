# Auditorías de las fuentes originales

Ejecutar desde la raíz del repositorio con `nap_env`. Ambas herramientas leen el dataset global validado y escriben en un directorio de resultados nuevo. Las etiquetas, embeddings, splits, scaler y entrenamiento se mantienen intactos. Las auditorías se pueden repetir con un destino nuevo. Una ejecución interrumpida requiere reiniciar, porque los resultados parciales carecen de un marcador de auditoría completada.

## Epítopos potencialmente omitidos

Extraer los eventos positivos y las dos tablas de FASTA de los archivos locales a una carpeta separada. Si ya existe una carpeta de evidencia completa, se puede reutilizar y omitir la extracción. Una extracción interrumpida puede dejar archivos parciales.

```bash
stage="$PWD/results/source_audits_inputs_20261118"
mkdir "$stage"
tar --keep-old-files -I zstd -xf data/used_data/data_raw.tar.zst -C "$stage" \
  --wildcards 'data_raw/*/merged_unique_events.csv'
tar --keep-old-files -I zstd -xf data/used_data/data_intermediate.tar.zst -C "$stage" \
  --occurrence data_intermediate/human_parent_protein_fasta.csv \
  data_intermediate/mouse_parent_protein_fasta.csv
```

```bash
python -m data_pipeline.scripts.source_audits.omitted_epitopes \
  --raw "$stage/data_raw" --fasta "$stage/data_intermediate" \
  --rows-per-family 10000 --output results/omitted_epitopes_sample_nueva

python -m data_pipeline.scripts.source_audits.omitted_epitopes \
  --raw "$stage/data_raw" --fasta "$stage/data_intermediate" \
  --full --output results/omitted_epitopes_full_nueva
```

La prueba usa eventos de las once familias y compara ventanas originales con el FASTA archivado. La identidad exige la URL completa y, cuando está disponible, la secuencia archivada exacta. Las URLs de diferentes isoformas se conservan por separado. Un mismo identificador con FASTA divergentes conserva identidades distintas y las versiones conflictivas dentro de un mismo origen se marcan como ambiguas. Sin FASTA se permite únicamente coincidencia de secuencia dentro de la misma URL y origen, con alcance explícito de candidatura.

Un acierto `coordinate_verified` exige coordenadas fuente enteras, que el epítopo y la ventana coincidan con FASTA en sus posiciones y que el epítopo esté totalmente dentro de la ventana. `sequence_only` recoge coincidencias exactas en la misma proteína con evidencia de locus insuficiente. Las posiciones de FASTA y de la ventana son 1-based inclusivas. `hits.csv` enumera coincidencias, que pueden repetirse por fila si hay varios epítopos u offsets. `summary.json` y `report.md` incluyen recuentos únicos, distribución por familia y ejemplos. Los recuentos de problemas en la evidencia son por evento fuente.

El recorrido completo de 55.763.575 ventanas tomó 4 min 33 s, con 922 MiB de RSS pico y aproximadamente 149 MiB de salida.

## Redundancia exacta de embeddings

```bash
python -m data_pipeline.scripts.source_audits.exact_embeddings \
  --groups-per-family 1000 --shuffle-chunks 12 \
  --output results/exact_embeddings_sample_nueva

python -m data_pipeline.scripts.source_audits.exact_embeddings \
  --full --output results/exact_embeddings_full_nueva
```

El índice barajado se lee directamente de su CSV archivado. El script localiza el registro original como el primero del bloque de 26 de cada observación, contrasta la dirección con la etiqueta familiar, el grupo y la proteína en el almacén ProtT5 y verifica grupo y proteína en el almacén SecondaryBERT. El índice de barajado contiene la dirección exacta de origen y permite comprobar ambos vectores contra la tabla concatenada. La comprobación distingue modalidades, aunque una diferencia por sí sola no identifica en qué etapa intermedia se produjo. El filtro de originales depende del orden de la implementación BLOSUM62 y del manifiesto existente.

La auditoría procesa bloques, mantiene vectores en un archivo mapeado a disco e indexa candidatos SHA-256 en SQLite. Para asignar una clase de equivalencia verifica los valores de cada candidato con su representante. Un duplicado exige la misma secuencia exacta, las dos clases de valor verificadas y la misma etiqueta global. El grupo solo se usa para localizar la observación de origen. Los ceros con signo son numéricamente iguales y los valores no finitos detienen la auditoría. El informe distingue secuencias cuyas observaciones son todas iguales de aquellas con algún par repetido y varias representaciones.

`proposed_provenance.parquet` vincula cada `(source_dataset_id, source_row_index)` con una observación representativa. Conserva secuencia, etiqueta global, grupo, proteína local y dirección ProtT5. `sources.json` resuelve los archivos de cada familia. Para una futura limpieza conviene conservar la tabla de procedencia y revisar los conflictos y el protocolo de splits antes de materializar representantes.

La muestra tomó aproximadamente 1 min 43 s y 1,9 GiB de RSS pico para 11 bloques de origen y 12 chunks de índice barajado. A escala completa se deben descomprimir aproximadamente 14.499 bloques originales, recorrer 1.450 millones de direcciones barajadas y cotejar 55,8 millones de originales. Una extrapolación simple de la muestra sitúa solo la lectura inicial en el orden de decenas de horas. La auditoría completa puede tardar varios días según el rendimiento secuencial y aleatorio del disco. No se ha medido a escala completa.

El archivo temporal de vectores requiere unos **372 GiB**. Reservar **500 GiB de disco libre** para vectores, índices y ordenaciones, y al menos **8 GiB de RAM disponible** para bloques y cachés, con margen para la caché del sistema. El acceso a vectores puede beneficiarse de un SSD. Pasar `--scratch /ruta/a/directorio/ssd` para ubicar los temporales en otro volumen existente. SQLite puede usar además el área temporal del sistema para ordenar. Configurar `SQLITE_TMPDIR` hacia el mismo volumen si su capacidad lo requiere.

## Pruebas

```bash
python -m unittest tests.test_source_audits -v
```
