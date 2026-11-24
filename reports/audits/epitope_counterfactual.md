# Impacto contrafactual de las coordenadas fuente aplicadas al FASTA parent

## Qué hacía el clasificador

La descarga seleccionaba ensayos positivos de péptidos lineales del organismo, clase y familia indicados. La fusión conservaba ambos extremos de IEDB y los identificadores fuente y parent. El clasificador agrupaba por parent y aplicaba directamente al FASTA parent un corte 1-based inclusivo sobre esas coordenadas. Exigía coincidencia exacta de residuos y contención completa del epítopo en una ventana de 25 aa. No bastaban una coincidencia en otra posición, una similitud de secuencia o una puntuación de posición. La puntuación solo se calculaba después de confirmar la contención.

Si una proteína tenía algún evento que superaba el filtro, se generaban todas sus ventanas consecutivas de 25 aa. Por posición, se escribía una fila por epítopo positivo contenido o una sola fila de etiqueta 0 si no había ninguno. Si la proteína quedaba sin eventos retenidos, no se generaba ninguna ventana para esa familia. El fallo puede afectar tanto a las etiquetas y la multiplicidad de filas como a la cobertura de proteínas.

[Clasificador original](../../data_pipeline/scripts/data_classification/epitope_classification.py#L336) · [Filtros de descarga](../../data_pipeline/scripts/data_download/build_iedb_dataset.py#L246) · [Descripción de los campos de IEDB](https://query-api.iedb.org/docs/swagger/iedb_api.json)

## Recuperación de eventos

Se enlazaron los **102.654 eventos** del grupo auditado con las exportaciones de ensayos originales. Los 903 lotes de IEDB devolvieron 90.240 registros distintos, sin lotes fallidos. Se recuperaron **92.623 eventos (90.23 %)** y **10.031** quedaron sin resolver.

| Resultado por evento | Eventos |
|---|---:|
| IEDB en una accesión alternativa con FASTA idéntico al archivado | 61 |
| IEDB en la versión exacta del parent | 68.468 |
| Fuente versionada de NCBI y proyección por alineamiento | 22.501 |
| Secuencia fuente versionada no verificada | 9.036 |
| Proyección ambigua, discontinua o con residuos distintos | 75 |
| Alineamiento fuera del límite o demasiados óptimos | 728 |
| Fuente con versión exacta de UniProt y proyección por alineamiento | 1.593 |
| El intervalo original no reproduce el péptido en su fuente | 192 |

Solo se aceptó evidencia directa para la misma versión del FASTA o con secuencia completa idéntica comprobada. Para proyección se exigió coincidencia exacta en la fuente versionada, un alineamiento global de proteínas completas y un único intervalo sin huecos que conservara los residuos en todos los óptimos enumerados. Se excluyeron matrices de más de 15 millones de celdas y casos con más de 64 alineamientos óptimos. Los eventos con una coincidencia de péptido aislada quedaron sin resolver. El grupo de 5.149 sin péptido en el parent pertenece a la categoría separada de la auditoría anterior y no participa en estas recuperaciones.

Se reintentaron los lotes de NCBI fallidos y se consultó UniProt para 1.110 accesiones fuente con versión explícita. UniProt devolvió 979 versiones exactas y permitió verificar 1.598 proyecciones antes de aplicar la prioridad de anotación directa. La cobertura es la alcanzada con las versiones y los servicios consultados. No equivale a una estimación de cuántos eventos serían recuperables con todas las versiones históricas.

Estado y coordenadas de cada evento (`event_resolution.csv`, artefacto retirado)

## Filas positivas existentes

Las **9.855.547** filas positivas conservan el epítopo seleccionado en un intervalo retenido por el clasificador y verificable contra el FASTA archivado. El control no detectó una fila positiva sin su anotación seleccionada ni una fila que necesitase apoyarse solo en otro epítopo retenido. Los 102.654 eventos investigados no generaron sus propias filas positivas. Recuperarlos sí añade evidencia a ventanas que ya eran positivas.

- 1.404.140 filas positivas coinciden con la posición de un evento recuperado, en 637.145 ventanas distintas por familia, proteína e inicio.
- 971.534 de esas filas conservan un epítopo seleccionado diferente de al menos uno de los recuperados.
- Cero falsos positivos demostrados por este grupo de eventos excluidos. El control del FASTA y de la regla local no audita independientemente la procedencia fuente de todos los eventos ya retenidos.

## Negativos originales y ventanas que faltaban

**207.302 filas originalmente etiquetadas 0** contienen un epítopo con coordenadas recuperadas y verificadas. Afectan a **196.837 secuencias distintas**. Etiqueta 0 significa que el clasificador no asignó una anotación positiva familiar a esa observación.

| Familia | Filas verificadas | Secuencias distintas | Proteínas |
|---|---:|---:|---:|
| HLA-A | 55.802 | 55.778 | 2.767 |
| HLA-B | 107.905 | 107.751 | 4.119 |
| HLA-C | 14.314 | 14.310 | 775 |
| HLA-DP | 479 | 479 | 34 |
| HLA-DQ | 3.825 | 3.825 | 233 |
| HLA-DR | 15.594 | 15.547 | 1.004 |
| H2-D | 2.274 | 2.274 | 136 |
| H2-K | 5.047 | 5.037 | 282 |
| H2-L | 0 | 0 | 0 |
| H2-IA | 2.025 | 2.025 | 218 |
| H2-IE | 37 | 37 | 2 |

Además, **2.350 pares familia–proteína** no tenían ninguna ventana generada. Ninguno tenía un epítopo que supere el filtro original. Con los eventos recuperados se podrían generar **1.635.285 posiciones de ventana**, de las cuales **52.617** contienen al menos un evento verificado. El recuento es por posición de ventana. Varias anotaciones pueden producir varias filas en una misma posición.

Filas negativas con evidencia verificada (`negative_candidates.csv`, artefacto retirado) · Distribución por proteína (`negative_by_protein.csv`, artefacto retirado) · Pares familia–proteína ausentes (`omitted_proteins.csv`, artefacto retirado)

## Cambios hipotéticos de la etiqueta global

| Escenario en las 15.135.904 secuencias existentes | Secuencias |
|---|---:|
| 0 → 1 al corregir filas existentes | 106.243 |
| 0 → 1 adicionales si se incorporan las ventanas omitidas | 18.736 |
| **0 → 1 total con las dos vías** | **124.979** |
| 1 → 0 atribuibles al grupo auditado | 0 |
| Etiqueta sin cambiar con la evidencia verificada | 15.010.925 |
| Subconjunto sin cambios, aún ambiguo y actualmente global 0 | 49.956 |

El cálculo preserva toda evidencia positiva ya retenida en cualquiera de las once familias. El subconjunto ambiguo contiene secuencias existentes sin evidencia global positiva verificada cuya ventana es compatible con al menos un locus aún sin resolver. Esa compatibilidad sirve para acotar el impacto pendiente. Fuera del corpus actual aparecerían además **15.187** secuencias positivas distintas si se materializaran las ventanas omitidas.

Escenarios por secuencia (`global_scenarios.csv`, artefacto retirado) · Resumen estructurado (`impact.json`, artefacto retirado)

## Recomendación

Reconstruir la evidencia y las etiquetas a partir de los ensayos originales de IEDB con un paso explícito de remapeo de referencias. Conservar por separado evidencia directa, proyecciones verificadas y eventos pendientes. Regenerar las ventanas de las proteínas que no llegaron al dataset y conservar los positivos independientes al agregar por secuencia. La auditoría actual acota el impacto del grupo investigado. Quedan por revisar la procedencia completa de positivos ya retenidos y las demás categorías de eventos excluidos antes de usar una reconstrucción como referencia definitiva.

No se modificaron los datos originales, las etiquetas, los embeddings, los splits, el scaler ni los procesos de entrenamiento.
