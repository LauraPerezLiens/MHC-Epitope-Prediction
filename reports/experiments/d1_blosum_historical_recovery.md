# NAP-CNB · Recuperación del inventario histórico BLOSUM62

**Fecha** 23 de noviembre de 2026 (UTC).

Se leyeron los once CSV del archivo histórico y se contaron **1.449.852.950 registros**, de los cuales **1.394.089.375** tienen `blosum_seq` distinto de `original_seq`. Otros **55.763.575** contienen la misma secuencia en ambas columnas. Estos son recuentos de filas, con posible repetición de secuencias. [Inventario estructurado](../../results/nap_cnb_v2_blosum_preparation/recovery/inventory.json)

## Registros y representaciones por familia

En las columnas de embeddings se indica **bloques documentados / bloques con SHA-256 expandido pendiente**. SecondaryBERT se cuenta por grupo. Los bloques concatenados pertenecen a una vista mixta.

| Familia | Filas CSV | Fila original | Fila aumentada | ProtT5 | SecondaryBERT | Concatenado |
|---|---:|---:|---:|---:|---:|---|
| HLA-A | 265.581.108 | 10.214.658 | 255.366.450 | 2.656 / 2.653 | 100 / 97 | Mixto |
| HLA-B | 276.639.038 | 10.639.963 | 265.999.075 | 2.767 / 2.765 | 104 / 102 | Mixto |
| HLA-C | 202.499.934 | 7.788.459 | 194.711.475 | 2.025 / 2.023 | 77 / 75 | Mixto |
| HLA-DP | 130.710.450 | 5.027.325 | 125.683.125 | 1.308 / 1.306 | 50 / 48 | Mixto |
| HLA-DQ | 62.125.466 | 2.389.441 | 59.736.025 | 622 / 620 | 24 / 22 | Mixto |
| HLA-DR | 197.293.902 | 7.588.227 | 189.705.675 | 1.973 / 1.971 | 75 / 73 | Mixto |
| H2-D | 110.365.892 | 4.244.842 | 106.121.050 | 1.104 / 1.102 | 42 / 40 | Mixto |
| H2-K | 156.593.450 | 6.022.825 | 150.570.625 | 1.566 / 1.564 | 59 / 57 | Mixto |
| H2-L | 115.648 | 4.448 | 111.200 | 2 / 1 | 1 / 0 | Mixto |
| H2-IA | 46.559.006 | 1.790.731 | 44.768.275 | 466 / 464 | 18 / 16 | Mixto |
| H2-IE | 1.369.056 | 52.656 | 1.316.400 | 14 / 12 | 1 / 0 | Mixto |

Las filas del CSV coinciden por familia con las cifras declaradas de ProtT5 y suman 1.449.852.950 en cada vista. La coincidencia acredita cardinalidad agregada. Sigue sin acreditarse la correspondencia por registro entre los CSV y los embeddings.

## Miembros del TAR y esquema

- **HLA-A** · `data_intermediate/human/mhc-I/HLA-A/classification_human_mhc-I_HLA-A_blosum.csv`
- **HLA-B** · `data_intermediate/human/mhc-I/HLA-B/classification_human_mhc-I_HLA-B_blosum.csv`
- **HLA-C** · `data_intermediate/human/mhc-I/HLA-C/classification_human_mhc-I_HLA-C_blosum.csv`
- **HLA-DP** · `data_intermediate/human/mhc-II/HLA-DP/classification_human_mhc-II_HLA-DP_blosum.csv`
- **HLA-DQ** · `data_intermediate/human/mhc-II/HLA-DQ/classification_human_mhc-II_HLA-DQ_blosum.csv`
- **HLA-DR** · `data_intermediate/human/mhc-II/HLA-DR/classification_human_mhc-II_HLA-DR_blosum.csv`
- **H2-D** · `data_intermediate/mouse/mhc-I/H2-D/classification_mouse_mhc-I_H2-D_blosum.csv`
- **H2-K** · `data_intermediate/mouse/mhc-I/H2-K/classification_mouse_mhc-I_H2-K_blosum.csv`
- **H2-L** · `data_intermediate/mouse/mhc-I/H2-L/classification_mouse_mhc-I_H2-L_blosum.csv`
- **H2-IA** · `data_intermediate/mouse/mhc-II/H2-IA/classification_mouse_mhc-II_H2-IA_blosum.csv`
- **H2-IE** · `data_intermediate/mouse/mhc-II/H2-IE/classification_mouse_mhc-II_H2-IE_blosum.csv`

Los once CSV comparten el esquema `protein_group_id`, `group_id`, `original_seq`, `blosum_seq`, `contains_epitope`, `selected_epitope`, `epitope_pos_score`. `group_id` identifica localmente el grupo de la fila original. `protein_group_id` identifica el grupo de procedencia de proteína dentro de la fuente histórica. La combinación con el miembro del TAR o su ID de fuente delimita el ámbito de los identificadores. Los campos de etiqueta y puntuación son históricos. El archivo de clasificación por familia aporta el contexto de procedencia. La revisión contó **0** filas con alguna secuencia vacía y **0** con algún identificador local vacío. El recuento de variantes distintas y la revisión exacta de la ejecución de aumento quedan indeterminados. [Procedencia histórica](d1_blosum_artifact_provenance.md)

Se procesaron los miembros seleccionados con GNU tar y Zstandard en streaming, con prioridad baja de CPU y E/S. Se cotejaron **110.052.645.616 bytes** de miembros CSV con los tamaños de sus entradas TAR. Se recorrió el contenedor comprimido de **5.078.332.109 bytes** en 2 min 41 s y se conservaron solo los agregados. El SHA-256 del TAR procede de la revisión anterior. Los miembros carecen de huellas independientes localizadas.

## Disponibilidad y pendientes

- **Secuencia aumentada documentada.** La secuencia original y la columna BLOSUM62 están presentes y son distintas según la regla de recuento. Los datos pueden volver a consultarse por nombre interno del TAR.
- **ProtT5 documentado.** Los 14.503 bloques familiares de 1.024 float32 tienen rutas, índices de origen y recibos. La revisión de hashes conserva 14.481 comprobaciones de contenido expandido pendientes en este conjunto.
- **SecondaryBERT documentado.** Los 551 bloques canónicos de 768 float32 registran 55.763.575 entradas de grupo declaradas. Quedan 530 hashes de contenido expandido pendientes. Los manifiestos y recibos identifican las copias comprimidas.
- **Concatenado documentado.** Los 14.499 NPY de 1.792 float32 están disponibles como vista mixta. Quedan 14.493 huellas pendientes. Su reparto por familia y su correspondencia por variante siguen sin acreditarse.
- **Componente físicamente ausente.** Faltan las rutas planas de los once índices maestros familiares y de las 1.128 dependencias comunes de la concatenación. Se conservan las copias comprimidas y sus recibos. El árbol concatenado carece de copias locales de los índices mixtos de dirección y split. Estos se conservan comprimidos en el reordenado. Quedan pendientes los hashes de contenido expandido de diez índices maestros familiares.
- **Correspondencia no acreditada.** La cantidad de registros con una representación ausente es indeterminada. La evidencia identifica los componentes a nivel de archivo. La disponibilidad por registro depende de una correspondencia individual que estos recuentos y metadatos dejan abierta. [Manifiesto de integridad](d1_blosum_integrity_manifest.jsonl) · [Catálogo de rutas](d1_blosum_data_organization.md)

## Conclusión

Los once CSV, los dos almacenes históricos por modalidad, el concatenado mixto y sus catálogos se pueden consultar y reutilizar como artefactos históricos sin nuevos cálculos. Queda acreditada la presencia de las filas BLOSUM62 en los CSV y la disponibilidad de las representaciones a nivel de archivo. La disponibilidad por variante, la integridad completa de los bloques pendientes y la correspondencia con D1 permanecen sin acreditar.
