# Auditoría comparativa de la descarga y normalización de IEDB

## Resultado de la comparación A/B

Se procesaron **1.985.260 registros en 22 exportaciones de 11 familias**. La reproducción A coincide exactamente con las claves completas de los **948.344 eventos** de los CSV fusionados históricos. La variante B conserva los mismos ensayos en **1.016.016 grupos**, incluidos los pendientes. Los 67.672 grupos extra reflejan el cambio de agrupación e identidad, además de los eventos sin coordenadas.

| Familia | Registros MHC | Registros T-cell | Eventos A | Grupos B | Añadidos | Pares A→B modificados | Retirados del conjunto simple |
|---|---:|---:|---:|---:|---:|---:|---:|
| HLA-A | 522.162 | 10.197 | 195.414 | 213.392 | 979 | 27.286 | 10.343 |
| HLA-B | 593.273 | 1.045 | 292.749 | 309.754 | 241 | 32.853 | 16.125 |
| HLA-C | 136.838 | 313 | 70.315 | 74.786 | 19 | 8.253 | 3.813 |
| HLA-DP | 161.793 | 345 | 83.149 | 88.294 | 19 | 6.460 | 1.355 |
| HLA-DQ | 47.617 | 777 | 32.443 | 33.744 | 33 | 2.159 | 896 |
| HLA-DR | 346.917 | 6.297 | 187.806 | 203.954 | 272 | 21.996 | 6.202 |
| H2-D | 45.517 | 519 | 22.514 | 23.391 | 20 | 2.537 | 1.694 |
| H2-K | 87.256 | 1.050 | 46.755 | 50.129 | 63 | 6.291 | 2.993 |
| H2-L | 44 | 114 | 20 | 23 | 2 | 1 | 0 |
| H2-IA | 20.679 | 2.101 | 16.958 | 18.288 | 127 | 2.656 | 1.485 |
| H2-IE | 233 | 173 | 221 | 261 | 16 | 25 | 1 |

- **Coordenadas ausentes.** A descartó **2.038 registros**, agrupados en **1.791 eventos** pendientes en B. Ninguno se convirtió automáticamente en evidencia positiva.
- **Deduplicación.** A colapsó **1.034.878 registros** adicionales. Los brutos permitieron reconstruir **1.983.222 vínculos ensayo–evento**, y **327.644 eventos** tenían varios ensayos. El fusionado no guardaba los IRIs de ensayo de ninguna fila, incluida la representativa.
- **Extracción.** La regex encontró un bloque en **147.987 registros** que B deja pendientes por no ser péptidos simples con el alfabeto estándar de 20 aminoácidos. Para las secuencias que sí cumplen el criterio simple, A y B coincidieron. El contraste auxiliar con la caché previa de IEDB cubrió **8.038 pares modificados** y en todos se conservaba el esqueleto lineal. El error demostrado en esos casos es perder la distinción química o de anotación. Los 147.987 registros requieren revisión, y la muestra de la caché no permite estimar cuántas secuencias lineales son incorrectas.
- **Cambios y exclusiones.** Hay **110.517 pares de claves A→B** modificados. De **95.832 grupos A** con algún registro dudoso, **50.925** conservan otro registro simple. Los **44.907** restantes quedan fuera del conjunto apto para normalización automática y permanecen en la procedencia. Los IRIs source y parent se conservan sin reescribirlos.
- **Referencias y modalidades.** B conserva **326 referencias source** y **40 parent** adicionales, contadas por familia. Las **22.931 filas T-cell** carecen de IRI de epítopo en los campos comprobados y preservan el IRI del ensayo. El IRI ontológico OBI del tipo de ensayo es un campo distinto.

La tabla comparativa incluye recuentos de secuencias distintas, ensayos, referencias y descartes por familia. Los 780.024 péptidos A y 742.030 péptidos simples B son sumas por familia. B deja en revisión los nombres no simples. Tabla comparativa (`comparison_by_family.csv`, artefacto retirado) · Desglose MHC y T-cell (`by_family_assay_type.csv`, artefacto retirado) · Cualitativos (`qualitative.csv`, artefacto retirado)

## Filtros y paginación

Se sustituyó **un filtro por vez** sobre el mismo archivo: cualitativo, nombre del hospedador, organismo fuente, clase o familia MHC. Hubo **cero recuperaciones y cero exclusiones dentro del archivo**. Los cualitativos archivados fueron Positive (1.971.739), Positive-Low (5.702), Positive-Intermediate (2.521) y Positive-High (5.298). El filtro de nombre conserva taxones de cepas y subtaxones. Los 108.759 IRIs de hospedador y 5.626 de organismo fuente que difieren del taxón base requieren comprobar ascendencia antes de sustituir el nombre por igualdad de taxón.

El código histórico sumaba 1.000 al offset hasta encontrar una página vacía. Detectaba fallos HTTP y no registraba recuentos esperados, orden estable, rangos ni solapamientos. Los CSV archivados no traen los encabezados ni totales históricos. Una fusión reproducida fielmente demuestra consistencia local y no certifica cuántos registros nunca se descargaron.

La consulta vigente del **18 de noviembre de 2026** quedó registrada con hora UTC. Los recuentos MHC amplios y el del ensayo HLA-A 699 agotaron su tiempo. Un recuento amplio de HLA-A T-cell devolvió 10.484 con ambos filtros cualitativos frente a 10.197 archivados. Esa diferencia entre fechas puede reflejar revisiones de IEDB y no se atribuye al descargador. La prueba acotada de la API ordenada por ID recuperó **9 epítopos en 3 páginas**, con rangos consecutivos, sin duplicados y con el mismo total exacto antes y después. Esa prueba valida el cliente experimental para la consulta probada.

Filtros por familia y modalidad (`filters.csv`, artefacto retirado) · Prueba vigente con fecha y parámetros (`live_counts.json`, artefacto retirado) · [API de IEDB](https://query-api.iedb.org/docs/swagger/) · [Paginación PostgREST](https://postgrest.org/en/stable/references/api/pagination_count.html)

## Sensibilidad de las ventanas

De los eventos añadidos sin coordenadas, **1.054** tienen una secuencia simple y ambas referencias. **1.043** también tienen FASTA parent local y **25 de las 40** referencias parent nuevas tienen FASTA archivado. El cribado no produjo una coincidencia única de hasta 25 residuos para estos eventos. Quedan **cero positivos nuevos confirmados** y el número de incorporaciones depende de verificar las referencias y recuperar los intervalos.

De los grupos que quedan pendientes sin otro registro simple, **41.427** pasaban el cotejo local del clasificador. Sus intervalos abarcan **491.850 posiciones positivas históricas**. **192.024** conservan otro evento bajo el criterio anterior. Las otras **299.826** perderían ese respaldo local si se retiraran los pendientes sin resolverlos. En **2.171 pares familia–parent** desaparecería el último evento admisible bajo la regla histórica. Son posiciones por familia, proteína e inicio y constituyen un escenario condicional. No demuestran falsos positivos ni cambios de etiqueta global y no se suman a la auditoría anterior del remapeo source→parent.

Escenario por familia (`window_sensitivity.json`, artefacto retirado)

## Ejemplos reales

- **Vínculo colapsado.** H2-IA MHC, filas 11 y 12, ensayos 200008 y 200009, para EEQTQQIRLQAEIFQAR.
- **Añadido pendiente.** H2-IA MHC, fila 340, ensayo 1678222. KLHRVAPKIKAKMMESGT conserva ambas referencias y carece de intervalo.
- **Modificado y en revisión.** H2-IA MHC, fila 286, ensayo 1646002. De GPPGPSGPAGERGEQG + HYLGLUCGAL(P3), A retiene GPPGPSGPAGERGEQG. B conserva el nombre y la modificación por separado.
- **Alfabeto ambiguo.** H2-IA MHC, fila 15776, ensayo 18495215. El nombre comienza por X y se conserva pendiente. El cambio no es un recorte de la regex.
- **Filtros.** No hay ejemplos de cambios de selección en el archivo histórico, porque ninguna sustitución individual cambió su selección.

Índices de fila base cero, sin cabecera. Añadidos (`added_events.csv.gz`, artefacto retirado) · Eliminados de la vía simple (`removed_events.csv.gz`, artefacto retirado) · Modificados (`modified_events.csv.gz`, artefacto retirado) · Descartes y motivos (`discarded_records.csv.gz`, artefacto retirado) · Procedencia completa (`event_assay_provenance.csv.gz`, artefacto retirado)

## Propuesta para los scripts principales

1. Guardar la respuesta bruta, parámetros, fecha y versión si el servicio ofrece un snapshot. Usar orden o cursor con clave única, cotejar total y rango por página, buscar solapamientos y publicar un marcador de finalización.
2. Separar entidades químicas, eventos y ensayos. Retener los IRIs fuente y parent exactos, el resultado cualitativo y la relación muchos-a-muchos entre evento y ensayo. Conservar coordenadas ausentes como pendientes.
3. Validar el péptido completo mediante campos estructurados de IEDB y conservar las modificaciones. No trasladar evidencia de un péptido modificado al péptido simple sin validarla.
4. Adoptar un conjunto explícito de positivos, revisar los alelos y alias con procedencia y verificar la ascendencia taxonómica. Comparar en una misma versión antes de cambiar la consulta principal.
5. Remapear source→parent después de resolver la estructura y la evidencia. Reconstruir ventanas solo tras validar las referencias.

Los scripts originales y los datos originales se conservaron. Para esta auditoría no se ejecutó una reconstrucción completa ni se trabajó con embeddings, splits, scaler o entrenamiento.
