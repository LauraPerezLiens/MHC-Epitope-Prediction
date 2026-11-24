# Origen y fiabilidad de las coordenadas de epítopos

## Conclusión

El dataset fusionado conserva **coordenadas de la proteína fuente de IEDB**, pero el clasificador las coteja sin remapeo con el **FASTA de la proteína parent**. Esa combinación explica el mecanismo de exclusión observado. Los 102.654 eventos incompatibles enlazan a una URL de fuente distinta de la URL parent. Las dos URLs pueden representar versiones o alias de una misma proteína, y también secuencias de isoformas, precursores, cadenas maduras o constructos distintos. El examen individual demuestra varias de esas causas y deja pendiente cuantificar cada una en todo el corpus.

Hay una vía para recuperar coordenadas verificables sin deducirlas solo del texto del epítopo. IEDB registra posiciones en accesiones alternativas bajo `curated_source_antigens`. Si esa accesión identifica la versión exacta del FASTA archivado, se pueden validar sus posiciones directamente. Cuando el registro solo identifica otra secuencia, un alineamiento entre secuencias completas puede proyectar un intervalo fuente que ya ha sido verificado. No se aplicó ningún cambio al dataset. [Esquema oficial de la IQ-API](https://query-api.iedb.org/docs/swagger/iedb_api.json) · [Distinción entre fuente curada y parent](https://discuss.iedb.org/t/immune-epitope-database-query-api-iq-api/154)

## Campos, procedencia e indexación

| Archivo o etapa | Campos | Significado |
|---|---|---|
| `mhc_export_full.csv` y `tcell_export_full.csv` | `epitope__starting_position`, `epitope__ending_position` | Intervalo del péptido lineal en la proteína fuente de referencia de IEDB. |
| Exportaciones completas | `epitope__source_molecule_iri`, `epitope__molecule_parent_iri` | Identificador de la secuencia fuente y referencia parent, respectivamente. El texto, los comentarios, el ensayo y la publicación están disponibles en columnas adicionales. |
| `merged_unique_events.csv` | Los dos campos de coordenadas anteriores, `epitope__name_canonical`, `source_id`, `parent_id`, `protein_id` | Se copian las coordenadas de la API. `source_id` conserva la fuente, `parent_id` conserva el parent y `protein_id` es una copia local del parent. La fusión canoniza el nombre del péptido, elimina filas sin extremos y deduplica por péptido, ambos extremos y ambas referencias. |
| `*_parent_protein_fasta.csv` | `protein_url`, `db`, `id_full`, `id_base`, `resolved_id`, `fasta` | Se descarga por `parent_id`. El descargador prueba el ID completo y puede recurrir al base. El encabezado puede conservar la versión de secuencia UniProt como `SV`. |
| CSV de ventanas originales | `window_start`, `selected_epitope`, `epitope_pos_score`, `protein_url`, `protein_group_id`, `group_id` | `window_start` y la puntuación son cálculos locales. Los límites fuente del epítopo no se guardan con la ventana. Los IDs de grupo son locales al CSV. |

El clasificador usa **1-based e inclusivo** en ambos extremos. Su comprobación Python es `protein_seq[start - 1:end]` y la longitud esperada es `end - start + 1`. El inicio de ventana se guarda como `i + 1`. El esquema oficial identifica la referencia fuente. La convención numérica se comprobó en los datos archivados y en las accesiones fuente de los ejemplos.

En **936.940 eventos fusionados** con FASTA parent archivado, extremos enteros y péptido de 1–25 residuos, el corte 1-based inclusivo coincidió en **829.137**. La alternativa 0-based con extremo inclusivo coincidió en **4.525**, con 42 coincidencias compartidas. En el grupo de 102.654, la alternativa coincide en 4.483. Eso no justifica cambiar la convención ni aplicar un desplazamiento general. El ejemplo Q92538 demuestra que un desplazamiento aparente de +1 también puede deberse a una versión distinta.

- [Descarga y fusión](../../data_pipeline/scripts/data_download/build_iedb_dataset.py#L208)
- [Descarga de FASTA y fallback](../../data_pipeline/scripts/data_classification/fetch_parent_proteins_fastas.py#L284)
- [Cotejo y construcción de ventanas](../../data_pipeline/scripts/data_classification/epitope_classification.py#L336)

## Qué explican los 102.654 eventos

- **100.550** tienen un intervalo parent en rango y de longitud correcta cuyos residuos discrepan. **2.104** tienen un intervalo fuera de rango o inválido para el parent.
- Las **102.654** URLs fuente difieren del parent tras equiparar HTTP y HTTPS. **94.670** también difieren en el token de acceso tras ignorar el sufijo numérico de versión y, si procede, el de isoforma. **6.581** tienen el mismo token al ignorar solo la versión y **1.403** comparten base al ignorar también el sufijo de isoforma. Son comparaciones de identificadores, no pruebas de identidad de secuencia.
- **80.425** URLs fuente llevan un sufijo de versión con punto y **696** URLs parent llevan un sufijo de isoforma con guion. En estos eventos, **ningún** FASTA archivado registra `id_full` diferente de `resolved_id`. El fallback es un riesgo del diseño, pero no se observó como causa en este grupo. Solo tres URLs fuente estaban también en el archivo FASTA local por coincidencia exacta de URL dentro del mismo organismo, y una validó el intervalo fuente directamente.
- Los puntos con un intervalo recuperado presentan desplazamientos positivos y negativos. Las posiciones coincidentes con +1 merecen verificación por accesión y versión. No se puede asignar a todos los eventos una causa biológica o de curación a partir del intervalo por sí solo.

El fallo de procesamiento demostrado es comparar coordenadas de una referencia con otra sin traducirlas. Esto deja los epítopos incompatibles fuera de la construcción de ventanas positivas. Las coordenadas pueden ser correctas en su propia secuencia fuente. IEDB también documenta que, históricamente, puede conservar numeraciones de autor que discrepan de una base de referencia. En los ejemplos verificados, el cambio de referencia explica los casos sin necesidad de postular un error de numeración de IEDB. [Manual de curación de IEDB](https://curationwiki.iedb.org/wiki/index.php/Curation_Manual)

## Ejemplos rastreados

Los índices de registro son **base cero y excluyen la cabecera**. Para HLA-A, los archivos se encuentran bajo `data_raw/human/mhc-I/HLA-A/` en `data/used_data/data_raw.tar.zst`. Se localizó cada exportación por familia, péptido canónico, coordenadas y las dos URLs. El detalle de los 12 ejemplos incluye índices, IRI de ensayo, IRI de epítopo cuando existe, PMID, encabezado FASTA y correspondencia de accesiones.

| Evento fusionado y registro bruto | Intervalo que se verifica en la fuente | Evidencia sobre el FASTA parent archivado |
|---|---|---|
| HLA-A 21, MHC 22, IEDB 16587 | `AAA73576.1`, 2333–2343 | `P49327.3`, 2335–2345, registrado por IEDB y validado en FASTA. Las referencias tienen 2.509 y 2.511 residuos. |
| HLA-A 23, T-cell 515, ensayo 1809091, IEDB 37182 | `P13284.2`, 27–35 | `P13284.3`, 16–24, registrado por IEDB y validado. Los FASTA tienen 261 y 250 residuos. Es un cambio de versión de secuencia. |
| HLA-A 34, MHC 38, IEDB 74794 | `Q92841.1`, 146–154 | `Q92841.2`, 225–233, registrado por IEDB y validado. La secuencia fuente es exactamente el sufijo parent tras 79 residuos. UniProt anota isoformas sin ese tramo N-terminal. |
| HLA-A 170, MHC 224, IEDB 75980 | `P01591.3`, 110–118 | `P01591.4`, 132–140. La fuente de 137 residuos es exactamente la cadena 23–159 del precursor archivado. UniProt anota péptido señal 1–22. |
| HLA-A 421, MHC 862, IEDB 42961 | Cadena PDB `2B5T_I`, 281–298 | `P01008.1`, 313–330, registrado por IEDB y validado. El desplazamiento es compatible con la cadena procesada tras la señal 1–32 y el alineamiento verifica el tramo. La cadena PDB completa difiere del sufijo parent. |
| HLA-A 684, MHC 1772, IEDB 10091 | `P01860.1`, 242–250 | 329–337 en `P01860.2`, registrado por IEDB. El FASTA público de esa versión es idéntico al FASTA archivado de la isoforma `P01860-1`. |
| HLA-A 1417, MHC 3107, IEDB 156660 | `Q92538.2`, 1053–1062 | `Q92538.3`, 1054–1063. Ambos intervalos están curados y ambos pasan con sus secuencias respectivas en 1-based inclusivo. El +1 no es un error de indexación. |
| HLA-A 8601, MHC 12605, IEDB 424582 | `AAH01973.1`, 44–52 | La secuencia aparece en 282–290 y 609–617 del FASTA `Q4VC44.2`. IEDB registra explícitamente 282–290 y el alineamiento de la secuencia fuente apoya ese intervalo. |
| HLA-A 81, MHC 100, IEDB 4966 | `Q13848`, 17–25 | El FASTA fuente de la fusión BCR/ABL contiene el péptido en ese intervalo. El parent ABL1 archivado `P00519` no lo contiene. La API vigente lista otro parent para ese epítopo. No procede trasladar este evento al FASTA archivado. |

Para HLA-B 147375, MHC 219295 e IEDB 509391, el archivo FASTA local también contiene la URL exacta de la fuente `A0A0U1RQK7`. El intervalo fuente **654–662** y el parent `O43432.2` **465–473** coinciden exactamente con sus secuencias. IEDB registra ambos. Es un ejemplo que se puede comprobar con el archivo local y la anotación alternativa sin buscar primero el péptido en el target.

- Rastreo de registros brutos y fusionados (`trace.json`, artefacto retirado)
- Validación de referencia, hashes de FASTA y alineamientos (`reference_validation.json`, artefacto retirado)
- Anotaciones de IEDB consultadas para los ejemplos (`iedb_curated_examples.json`, artefacto retirado) · Registro GILT 37182 (`iedb_curated_gilt.json`, artefacto retirado)
- [Características de JCHAIN](https://rest.uniprot.org/uniprotkb/P01591.json) · [Características de DDX17](https://rest.uniprot.org/uniprotkb/Q92841.json) · [Características de antitrombina](https://rest.uniprot.org/uniprotkb/P01008.json)

## Criterio de uso para una futura corrección

1. Recuperar la referencia del ensayo positivo y su epítopo desde la exportación completa, conservando la accesión y versión fuente. El CSV fusionado permite reconstruir el vínculo, pero elimina los IDs de ensayo y publicación.
2. Priorizar un intervalo explícito de IEDB en la **misma versión o secuencia comprobada del FASTA parent** y confirmar residuos, límites, proteína y contención. Para un IRI sin versión, exigir evidencia de identidad de la secuencia.
3. Si falta un intervalo directo, validar primero el intervalo original en la versión fuente. Proyectarlo después con un alineamiento de proteínas completas y aceptar como candidato fuerte solo un mapeo inequívoco sin huecos a través del péptido y con coincidencia exacta en el parent. Registrar la accesión, versión y hash de ambas secuencias, el intervalo original y el método de remapeo.
4. Mantener por separado los loci inferidos solo por coincidencia única, las secuencias repetidas sin mapeo inequívoco, los cambios de parent y las fuentes que no pueden resolverse. Una ocurrencia única en el FASTA no demuestra por sí sola que el ensayo se refiera a ese parent.
5. Someter a auditoría el cruce completo antes de usar los resultados para cambiar etiquetas. Se comprobó la viabilidad en ejemplos seleccionados. La cobertura de `curated_source_antigens` y de las proyecciones verificadas en todo el grupo sigue sin medirse.

La regla conserva la evidencia positiva y exige una correspondencia documentada entre la referencia del ensayo y la ventana. No se corrigió ninguna etiqueta ni coordenada de origen.
