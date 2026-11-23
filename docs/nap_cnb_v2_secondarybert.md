# SecondaryBERT para NAP-CNB v2

**Fase 3C cerrada el 20 de noviembre de 2026.** El índice verificado cubre las 1.847.436 claves C/H/E y las 49.123.503 ventanas originales. Contiene 1.819.032 referencias históricas, 1.000 vectores del piloto y 27.404 vectores de la ejecución completa.

La fase 3C usa las claves C/H/E exactas de 25 posiciones de los dos inventarios de la auditoría. Las frecuencias por clave permiten medir cobertura sobre las ventanas originales. Cada clave del índice tiene un SHA-256 y conserva la cadena como clave primaria. El índice apunta al archivo canónico y a la fila del vector histórico, o a un vector nuevo almacenado en la misma base SQLite.

El módulo `data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2` reutiliza la validación del tokenizador, la carga del modelo y la inferencia de `generate_secondary_bert_embeddings.py`. El checkpoint local `model/secondary_bert` es un `BertForMaskedLM` de 12 capas, 12 cabezas y dimensión oculta 768. Se usa el encoder `model.bert` y se promedian las posiciones biológicas de su última capa oculta. Cada cadena produce 27 tokens, con CLS=2, C=5, H=6, E=7 y SEP=3. La inferencia CUDA usa autocast FP16 y la salida se escribe en float32. Las claves del inventario se validan de forma estricta antes de inferir.

## Ejecución en Pascal

Desde la raíz del proyecto, con el entorno `nap_env` activo, `zstd` en el PATH y CUDA. Selecciona una RTX 3090 libre y exporta su UUID en `CUDA_VISIBLE_DEVICES` antes de ejecutar el piloto o la generación. El lote se fija en 256. Los manifiestos históricos documentan lotes de 4.096.

```bash
python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 index
python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 pilot
```

El índice se construye una vez a partir de los archivos inventariados y del campo `clean_ss` de los metadatos canónicos. Comprueba los IDs y posiciones frente al índice histórico, busca cualquier aparición de claves pendientes y exige una dirección para cada clave auditada como reutilizable. El piloto comprueba 24 claves por fuente canónica con lote 256. Los criterios son diferencia absoluta máxima ≤ 0,01, RMSE máximo por vector ≤ 0,002 y coseno mínimo ≥ 0,99999. La muestra de 1.000 claves pendientes se estratifica por composición y transiciones con semilla fija. Se repite la inferencia y se releen los vectores almacenados.

Este fue el comando utilizado para completar la fase:

```bash
python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 generate
```

La generación comprueba la evidencia del piloto y la coincidencia de checkpoint, tokenizer, código y entorno. Escribe cada lote en una transacción SQLite. Al reanudar, verifica dimensión, finitud y el SHA-256 de clave y bytes de cada vector confirmado, y continúa con las claves restantes. Un piloto válido aporta sus 1.000 vectores a la generación. La validación de cierre cruza por clave exacta las referencias canónicas y los vectores nuevos, y suma las frecuencias de las claves con cobertura.

## Recuperación para entrenamiento

Usa las claves primaria y secundaria de la selección definitiva. Recupera ProtT5 por la primaria exacta a través de su inventario y almacén verificado. Recupera SecondaryBERT por la cadena C/H/E exacta con `read_secondary_embeddings(db, keys)` de `data_pipeline.nap_cnb_v2_batches` sobre `results/nap_cnb_v2_secondarybert/index.sqlite`. La función devuelve los vectores en el orden de las claves solicitadas y agrupa las lecturas históricas por archivo. Conserva etiqueta, familia MHC e identificadores de procedencia en las filas originales. Los dos vectores permiten componer 1.792 dimensiones durante la carga.

La lectura, descompresión y verificación de los bloques históricos tuvo una mediana de 4,73 s por bloque en la muestra. Durante la preparación del entrenamiento se evaluarán la agrupación por archivo, la caché de bloques, la lectura por lotes y, si hace falta, la consolidación. Un almacén compacto para las 1.819.032 claves históricas supondría 5.588.066.304 bytes de vectores float32, más el índice. Esa opción simplificaría el acceso aleatorio y reduciría la dependencia de la estructura archivada, a cambio de crear y mantener una copia derivada. El índice por referencia conserva las rutas auditadas y comprueba los recibos SHA-256 al recuperar archivos. Si se trasladan las fuentes, hay que reconstruir las referencias para la nueva ubicación.

Los resultados medidos se recogen en [el informe de fase 3C](../results/nap_cnb_v2_secondarybert/secondarybert_report.md).
