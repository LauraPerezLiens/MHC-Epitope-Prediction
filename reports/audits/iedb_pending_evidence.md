# Verificación de los 44.907 eventos pendientes de IEDB

## Alcance y cruce

Se recuperaron **56.192 registros de ensayo** para **44.907 grupos familiares**. **2.543** grupos ya aparecían en la auditoría de coordenadas. **2.122** tenían un mapeo verificado en esa auditoría. La unión se hizo por familia, esqueleto anterior, coordenadas y ambas referencias, conservando versiones e isoformas. Se equipararon los esquemas HTTP y HTTPS. Cada grupo se cuenta una sola vez en la tabla final. El cruce histórico por FASTA reproduce 41.427 grupos que pasaban el cotejo local y 491.850 posiciones positivas. Se localizaron anotaciones compatibles atribuidas a esos grupos en 491.850 posiciones de los Parquet originales. El escenario de retirada usa filas realmente observadas.

Todos los vínculos de ensayo (`assay_links.jsonl.gz`, artefacto retirado) · Estado por grupo (`event_resolution.csv`, artefacto retirado) · Cobertura de consultas (`coverage.json`, artefacto retirado)

## Estados finales y solapamientos

| Estado mutuamente excluyente | Grupos |
|---|---:|
| Esqueleto ausente de la referencia parent | 253 |
| Intervalo o proyección sin verificar | 254 |
| Péptido modificado con esqueleto y locus parent verificados | 42.809 |
| Necesita referencia o esqueleto resoluble | 1.591 |

**2.180** grupos tienen una corrección de extremos comprobada y sin conflicto de locus. Esa marca se cruza con la identidad molecular y no forma una categoría excluyente.
De los grupos con evidencia simple o modificada mapeada, **42.385** también reproducen exactamente el intervalo en su referencia source. Cuando falta esa comprobación, solo se acepta el locus parent si existe una anotación explícita para la misma versión o secuencia o un mapeo previo verificado y vinculado a la estructura original. Las columnas de estructuras separan ambos controles.
Se obtuvieron **47.004 de 47.004** IDs solicitados a IEDB y hubo **0** lotes sin respuesta utilizable. Los estados de referencia pendiente reflejan las fuentes y versiones recuperadas en esta ejecución. Un locus verificado para la entidad modificada conserva esa evidencia experimental. Aplicar esa positividad a la ventana sin modificar requeriría evidencia adicional. [Manual de curación de IEDB sobre residuos modificados](https://curationwiki.iedb.org/wiki/index.php/Curation_Manual)

## Distribución por familia

| Familia | Verificados simples o modificados | Coordenadas corregidas | No verificados | Posiciones históricas | Secuencias afectadas |
|---|---:|---:|---:|---:|---:|
| H2-IA | 1.167 | 98 | 318 | 5.789 | 6.473 |
| H2-IE | 1 | 0 | 0 | 11 | 11 |
| H2-D | 1.586 | 38 | 108 | 12.741 | 13.166 |
| H2-K | 2.905 | 60 | 88 | 33.486 | 34.215 |
| HLA-DR | 5.740 | 575 | 462 | 39.708 | 43.135 |
| HLA-DQ | 806 | 46 | 90 | 5.645 | 5.986 |
| HLA-DP | 1.295 | 26 | 60 | 9.239 | 9.457 |
| HLA-B | 15.689 | 650 | 436 | 206.603 | 215.024 |
| HLA-A | 9.945 | 413 | 398 | 131.081 | 135.329 |
| HLA-C | 3.675 | 274 | 138 | 47.547 | 50.696 |
| H2-L | 0 | 0 | 0 | 0 | 0 |

Las posiciones se deduplican dentro de familia, proteína e inicio. Las secuencias se deduplican en el agregado global. Los recuentos de secuencias por familia pueden solaparse.

## Impacto sobre etiquetas globales

Las posiciones históricas cubren **437.427** secuencias distintas. Al incluir loci remapeados, se evaluaron **455.775** secuencias del índice actual. En ambos escenarios se conserva cualquier evidencia histórica independiente fuera de estos 44.907 grupos, en cualquiera de las 11 familias. Para atribuir retiradas se cotejaron filas positivas reales por proteína, inicio y epítopo seleccionado. Los loci con una anotación indistinguible aportada por otro evento se conservaron de forma conservadora. No se volvió a validar toda esa evidencia independiente.

| Escenario hipotético | Global 1 que se conserva | Global 1 → 0 | Global 0 → 1 | Secuencias positivas nuevas fuera del índice |
|---|---:|---:|---:|---:|
| Conservar de forma hipotética el respaldo de los modificados ya mapeados | 445.499 | 2.849 | 7.427 | 1.088 |
| Exigir respaldo simple para el péptido sin modificar | 281.229 | 167.119 | 0 | 0 |

El primer escenario excluye los grupos sin respaldo verificable, corrige los loci y permite que los modificados mapeados sostengan hipotéticamente la etiqueta histórica. El segundo conserva solo respaldo simple de los grupos auditados. El contraste cuantifica la decisión química pendiente. Una etiqueta operativa 0 expresa ausencia de respaldo elegible, no negatividad experimental.
Los ascensos del primer escenario comparten **7.427** secuencias con los ascensos de la auditoría anterior. No deben sumarse como conjuntos disjuntos.

Distribución y cambios globales por familia (`by_family.csv`, artefacto retirado) · Escenarios por secuencia (`global_scenarios.csv`, artefacto retirado)

## Ejemplos trazables

- **Péptido modificado con esqueleto y locus parent verificados.** H2-IA, GPPGPSGPAGERGEQG + HYLGLUCGAL(P3), source 642–657, parent 642–657. Ensayo http://www.iedb.org/assay/1646002, grupo 002256dd3ee2cfde0b60ccaa9322334fb2b47a129bddbfefd120406ca7edc884.
- **Necesita referencia o esqueleto resoluble.** H2-IA, AGGGREREKAERQPGT + OX(R12), source 211–226, sin intervalo parent verificado. Ensayo http://www.iedb.org/assay/2378838, grupo 9c1f0e0a14d9f2d20d59f8e7747662f8e0d6f346ecb107bd1aa3b885cf920511.
- **Intervalo o proyección sin verificar.** H2-IA, AAPEAAAAPEVAAAPATPA + OX(P3, P9), source 157–175, sin intervalo parent verificado. Ensayo http://www.iedb.org/assay/2378802, grupo df06927587918ce3116d5c9364171ddfcd83756922e4685fb54b8842d16d9f81.
- **Esqueleto ausente de la referencia parent.** H2-IA, AAARGAAGTESRANRVR + DEAM(R4), source 7–23, sin intervalo parent verificado. Ensayo http://www.iedb.org/assay/2378791, grupo cac9476096740e70d428cea9dd88b82d1d433c64ce89eab9f447d464745668a6.

## Cambios que requieren los scripts originales

1. **Descarga.** Conservar los resultados cualitativos, IRIs de ensayo y estructura, metadatos de modificación y coordenadas ausentes. Registrar fecha y controles de integridad por página.
2. **Normalización.** Sustituir la extracción por regex por campos estructurados de IEDB. Distinguir la entidad modificada de su esqueleto lineal y conservar la relación muchos-a-muchos con los ensayos.
3. **Clasificación.** Verificar la versión de la referencia y remapear los intervalos fuente al parent antes de crear ventanas. Separar evidencia de entidad modificada, respaldo simple, proyección y casos pendientes. Agregar por secuencia conservando las evidencias independientes.

No se editaron los scripts principales ni sus datos, y no se reconstruyeron datasets completos ni se calcularon embeddings.
