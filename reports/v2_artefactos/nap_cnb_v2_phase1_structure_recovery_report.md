# NAP-CNB v2 · recuperación de estructura secundaria

La recuperación validada cubre las **468.559 ventanas** que quedaron sin verificar por la referencia archivada. La salida complementaria existente se aplica por `window_id`.

| Métrica | Antes | Después |
|---|---:|---:|
| Ventanas binarias | 49.205.104 | 49.205.104 |
| Ventanas con C/H/E verificada | 48.654.944 | 49.123.503 |
| Ventanas sin C/H/E | 550.160 | 81.601 |
| Cobertura estructural | 98,882 % | 99,834 % |

## Proteínas investigadas y pendientes

Se investigaron **828 proteínas únicas** por accession, versión y SHA-256 de la secuencia completa, correspondientes a **827 secuencias completas distintas** y **1.107 pares familia–proteína**. Se recuperaron **669 proteínas** y **668 predicciones completas distintas**. Las coincidencias recuperadas utilizaron la misma URL y la misma secuencia completa. La búsqueda por hash incluyó predicciones bajo otros identificadores.

| Estado de los casos pendientes | Proteínas | Ventanas |
|---|---:|---:|
| Predicción completa sin localizar en las fuentes históricas consultadas | 159 | 81.601 |
| Predicción localizada con secuencia, longitud, versión o isoforma incompatible | 0 | 0 |
| Predicciones válidas ambiguas | 0 | 0 |
| Necesidad de una predicción nueva confirmada documentalmente | 0 | 0 |

Los 159 casos corresponden a 159 secuencias completas distintas. Su predicción podría existir fuera de los archivos localizados. El inventario indica para cada caso el accession, la versión cuando se conoce, el hash y el número de ventanas por familia. [Inventario de proteínas](../nap_cnb_v2_structure_recovery/proteins.tsv)

## Fuentes y procedencia

La fase 1 exigía una referencia del FASTA archivado con versión o cadena fijada. Para los casos recuperados, la fila original de ProteinUnet contiene tanto la secuencia completa de v2 como el C/H/E de la misma longitud. Se conservó la versión donde el FASTA archivado acreditó la misma URL y secuencia completa. [Procedencia por archivo y fila](../nap_cnb_v2_structure_recovery/prediction_sources.tsv)

Se reutilizaron los dos CSV de ProteinUnet extraídos de `data/used_data/data_intermediate.tar.zst`, los FASTA archivados de humano y ratón, el inventario de huecos y las referencias completas y coordenadas de las familias de fase 1. [Predicciones humanas](../nap_cnb_v2_phase1_structure/secondary_struct_human.csv) · [Predicciones murinas](../nap_cnb_v2_phase1_structure/secondary_struct_mouse.csv) · [Inventario original](structure_gaps.tsv) · [Referencias de fase 1](references/)

## Integración y controles de integridad

- El Parquet complementario se une por `window_id`. La clave existente incluye familia, URL de proteína e inicio 1-based. El final inclusivo es el inicio más 24. Cada fila incluye el hash de proteína, el método de verificación y un identificador de predicción que se resuelve en el TSV de procedencia.
- La validación incremental comprobó coincidencia exacta de secuencia completa, longitud global, recortes sobre el mismo intervalo, cadenas de 25 caracteres C/H/E, unicidad de los identificadores y trazabilidad de todas las filas. Pasaron las 13 pruebas de reconstrucción, estructura y recuperación incremental.
- Las 468.559 filas del Parquet coinciden con el aumento de cobertura. Los tamaños y marcas de modificación de los archivos base coinciden con los registrados tras la recuperación. El índice solo añade información estructural a claves de ventanas antes pendientes. Las etiquetas, las secuencias primarias y las estructuras ya verificadas se leen de la fase 1.
- El C/H/E del índice usa diccionarios Parquet y compresión Zstandard. Los identificadores y la tabla de procedencia evitan depender del orden físico de los archivos.

## Archivos y tamaño

El conjunto incremental reutilizado ocupa **4.199.405 bytes**.

| Archivo | Bytes |
|---|---:|
| [window_structures.parquet](../nap_cnb_v2_structure_recovery/window_structures.parquet) | 3.781.064 |
| [proteins.tsv](../nap_cnb_v2_structure_recovery/proteins.tsv) | 171.574 |
| [prediction_sources.tsv](../nap_cnb_v2_structure_recovery/prediction_sources.tsv) | 238.133 |
| [metrics.json](../nap_cnb_v2_structure_recovery/metrics.json) | 5.208 |
| [Informe de ejecución previo](../nap_cnb_v2_structure_recovery/report.md) | 3.426 |

En esta revisión se añadió únicamente este informe a la salida de fase 1.
