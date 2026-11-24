# NAP-CNB — Documento maestro de contexto científico y técnico

**Fecha de corte:** 24 de noviembre de 2026  
**Ámbito:** investigación doctoral, construcción de datos, aprendizaje automático, inmunoinformática e integración en Scipion-Chem.  
**Naturaleza:** documento vivo de transferencia de conocimiento, no artículo publicado ni auditoría certificada del código.

> ⏳ **Hay una tarea abierta: § 0.6, verificación de datos IEDB.** Si se reanuda la sesión tras un corte, leer esa subsección primero: contiene el estado, lo hecho, lo pendiente y los comandos para continuar.

> Este documento reconstruye el historial comunicado en conversaciones. Distingue resultados históricos, decisiones, propuestas y trabajo pendiente. Las rutas y cifras corresponden a distintas versiones del pipeline y no deben interpretarse como un único snapshot. Las secciones 1 a 21 conservan ese historial tal como se escribió; **la sección 0, añadida el 24 de noviembre de 2026, las corrige donde han quedado obsoletas y tiene prioridad sobre ellas.**

---

## 0. Estado verificado a 24 de noviembre de 2026

Esta sección se apoya en artefactos del repositorio y en los artículos publicados del grupo, no en resúmenes de conversación. Fuente autoritativa del diagnóstico: [`reports/auditoria_consolidada.md`](reports/auditoria_consolidada.md); índice de evidencia en [`docs/INDICE_EVIDENCIA.md`](docs/INDICE_EVIDENCIA.md).

### 0.1. Correcciones a secciones posteriores

| Afirmación en §10–§18 | Estado real |
|---|---|
| ROC-AUC ≈ 0,99999 | Artefacto de partición por fila. **No volver a citarse.** |
| ROC-AUC histórico 0,7955 | Fuga: 99,70 % de los grupos en varias particiones, 87,38 % en las tres. |
| Bloqueo de compatibilidad de embeddings | **Resuelto.** Las auditorías de embeddings salieron limpias (muestras bit-exactas, finitud, cobertura, digests). No procede seguir auditándolos. |
| «Prioridad inmediata: resolver el bloqueo antes de escalar D2» | **Obsoleto.** La recomendación vigente es **no ejecutar D2**. |
| E3/E4 pendientes de ejecución | Sustituidos por E1/E2, ablación por modalidad y partición por componentes, ya ejecutados. |

### 0.2. Resultados honestos actuales (D1, TEST puntuado una vez)

| Modelo | Partición | ROC-AUC | AP | Prevalencia | AP/prev |
|---|---|---:|---:|---:|---:|
| LR | primaria exacta | 0,654641 | 0,375738 | 0,25451 | 1,476 |
| MLP 1.792 (E2) | primaria exacta | 0,680107 | 0,412129 | 0,25451 | 1,619 |
| LR | componentes de proteína | 0,662294 | 0,379399 | 0,24385 | 1,556 |
| MLP | componentes de proteína | 0,674668 | 0,395093 | 0,24385 | 1,620 |

Eliminar **toda** la fuga por proteína cuesta 0,0054 de ROC-AUC. **El nivel 0,66–0,68 es generalización real**, no artefacto. El techo no se explica por fuga, ni por ruido de etiqueta, ni por corrupción: es la formulación de la tarea y la representación.

Ablación por modalidad (mismas particiones): solo ProtT5 **0,682302**; ProtT5+SecondaryBERT 0,680107; solo SecondaryBERT 0,601431. Contar C/H/E en la ventana con regresión logística da 0,592364. **SecondaryBERT aporta +0,0088 sobre tres enteros y aporte negativo sobre ProtT5.**

### 0.3. Línea base publicada del grupo

Estas cifras provienen de los artículos y son el único punto de comparación legítimo.

**PDFs de referencia, todos accesibles en `i2pc.es/coss/Articulos/`** (añadidos el 24 nov 2026 para poder reconsultarlos sin pedirlos de nuevo):

| Trabajo | Enlace | Qué aporta |
|---|---|---|
| Wert-Carvajal et al., Sci Rep 2021 | https://i2pc.es/coss/Articulos/Wert2021.pdf | **La línea base real: AUC 0,865 en held-out, PR-AUC 0,4197, lift 15,9×.** Un modelo por haplotipo, 12-mer, one-hot, biLSTM, BLOSUM62 on-batch + post-proceso en inferencia (+7,6 %). |
| Méndez-Pérez et al., eLife 2024 | https://i2pc.es/coss/Articulos/Mendez2024.pdf | Validación in vivo. **La expresión pesa más que la inmunogenicidad predicha.** No mejora ninguna métrica de modelo. |
| Guillén 2021 (TFG) | https://i2pc.es/coss/Articulos/Guillen2021.pdf | Origen de la ventana de 30 aa, ProteinUnet y los BERT de primaria/secundaria. val accuracy 0,70–0,73. |
| Ballesteros 2022 (TFG) | https://i2pc.es/coss/Articulos/Ballesteros2022.pdf | Pipeline humano/ratón y detección flexible de mutaciones. **Ninguna métrica de modelo.** |
| Sánchez 2024 (TFM) | https://i2pc.es/coss/Articulos/Sanchez2024.pdf | MLP de 1.536 dim. test acc 0,838–0,861, pero con undersampling y **split aleatorio por fila**: no es generalización. |

> Las cifras de §0.3 se obtuvieron leyendo estos PDFs directamente. Si hace falta un detalle que no esté aquí, están en esas URLs; no reconstruirlo de memoria.

**Wert-Carvajal et al., Sci Rep 2021;11:10780 — lo que sí se publicó.**
Unidad: péptido de **12 aa** centrado en la SNV (probaron 8/10/12). Codificación **one-hot**; probaron tres embeddings de baja dimensión y no mejoraron sobre one-hot. Modelo: 3 × biLSTM + 3 densas + 2 dropouts. Negativos: Smith-Waterman del epítopo contra su proteína fuente, el resto de la proteína como negativo. **Un modelo por haplotipo**; reportan que la predicción cruzada H-2Kb↔H-2Kd es subóptima y concluyen que hacen falta redes individuales por haplotipo. Datos H-2Kb: 4.828 entradas IEDB → **251.049 secuencias, 6.714 positivas, 244.225 negativas, prevalencia 2,67 %**. BLOSUM62 **on-batch** durante el entrenamiento con tolerancia ajustada por grid search, nunca materializado a disco; y **post-proceso en inferencia** por voto de mayoría sobre sustituciones de un residuo, **+7,6 % de precisión**. Balanceo on-batch: la prevalencia virtual subió AUC y F1 un 20 %, más que la profundidad de la red. 5-fold CV, 80 modelos.

Métricas: **AUC 0,95 ± 0,04 en CV**; en el **10 % held-out, AUC 0,865, accuracy 0,972, PR-AUC 0,4197 con prevalencia 2,64 %** (lift **15,9×**). Por haplotipo, de 0,7 ± 0,1 (H-2Db) a 0,96 ± 0,06 (H-2Kk).

> **Comparación justa.** No citar 0,95 frente al 0,68 actual: 0,95 es CV, el número comparable es 0,865, y la tarea es otra. En lift de AP: **15,9× (2021) frente a 1,62× (E2)**.

**Méndez-Pérez et al., eLife 2024;13:RP95010 — no mejora ninguna métrica.** Es validación in vivo: 5 péptidos sintéticos, ELISpot, ICS y reto con B16-F10 en C57BL/6J. \*Herc6 (predicho no inmunogénico) no indujo respuesta, confirmando el control negativo. Hallazgo central: **la expresión pesa más que la inmunogenicidad predicha** — \*Adar, top-scored pero el menos expresado, falló por completo; la protección máxima (100 % de ratones con tumor <100 mm³ a día 15) fue con \*Wiz, que **solo apareció tras el post-proceso BLOSUM62**, y con la mezcla \*Pnp+\*Adar+\*Lrrc28. Conclusión de los autores: priorizar TNA con mayor expresión tumoral aunque sean menos inmunogénicos, y usar terapia multiantígeno.

**Linaje TFG/TFM del que desciende el pipeline actual — nunca dio un número bueno y honesto.**

| Trabajo | Aportación | Métrica real |
|---|---|---|
| Guillén 2021 (TFG) | Origen de ventana 30 aa + ProteinUnet + BERT primaria/secundaria | val accuracy **0,70–0,73** |
| Ballesteros 2022 (TFG) | Pipeline humano/ratón, detección flexible de mutaciones | **ninguna métrica de modelo**; valida ejecución, no predicción |
| Sánchez 2024 (TFM) | MLP 1.536-dim, 5 capas, fine-tuning por haplotipo | test acc 0,838/0,831/0,861, pero con **undersampling aleatorio**, **split aleatorio por fila** y train 0,991 vs test 0,838 |

### 0.4. Diagnóstico: cuatro decisiones, por orden de impacto

1. **Familia en vez de alelo, más etiqueta global sobre las 11 familias.** `HLA-A` no es un haplotipo: son cientos de alelos con motivos de unión incompatibles. Wert2021 demuestra experimentalmente que hacen falta redes por haplotipo; el diseño actual hace lo contrario y lo agrava. Es la causa del 93,53 % de positivos que aparecen también como negativos. **Que «el ratón funcione y el humano no» no es dificultad biológica del humano: H-2Kb es un alelo de una cepa consanguínea y aun así se modeló por separado.**
2. **Mean pooling sobre 25 posiciones.** El epítopo ocupa 8–11 de 25 residuos y la media lo diluye. Parejas adyacentes con etiqueta opuesta quedan a distancia mediana 12,71 frente a 58,13 entre proteínas distintas (coseno 0,9455). Wert2021 conservaba la posición con one-hot + LSTM.
3. **Prevalencia 25,45 % frente a 2,67 %.** El criterio de contención en 25 aa más la etiqueta global multiplica los positivos por diez. No es el mismo objetivo.
4. **BLOSUM62 materializado a disco en lugar de on-batch.** El paper nunca escribió variantes aumentadas. Las variantes están a coseno 0,9883 y distancia 6,60 tras el scaler, **más cerca entre sí que la distancia que separa etiquetas opuestas reales (12,71)**: no añaden información sobre el objetivo.

### 0.5. Prioridades vigentes

1. **E0 — reproducir Wert2021 como brazo de control**, antes que cualquier otra cosa: one-hot, 12-mer, biLSTM, solo H-2Kb, negativos de la misma proteína, prevalencia natural, 251 k secuencias. Si se alcanza ~0,86, la diferencia está en la construcción de datos; si no, está en IEDB. Sin este anclaje no puede defenderse ninguna afirmación de mejora.
2. **Post-proceso BLOSUM62 en inferencia** sobre los Parquet de predicciones ya existentes. Es el único uso de BLOSUM62 con evidencia publicada de que funciona.
3. **Alelo en la entrada**, como pseudosecuencia al estilo NetMHCpan.
4. **Pasar de ventana a péptido**: 8–11 aa para MHC-I, representación por residuo, negativos como señuelos del mismo proteoma emparejados por longitud y deduplicados por péptido exacto.
5. **No ejecutar D2.** Cerrar la línea histórica aumentada.
6. **Cerrar la línea de estructura secundaria y publicarla como resultado negativo.** Cuatro evidencias independientes convergen (Guillén 0,70; Sánchez sin aislar el aporte; ablación +0,0088 sobre contar C/H/E y negativo sobre ProtT5). Cierra una línea que el laboratorio ha perseguido durante tres TFG/TFM.
7. **Benchmark contra NetMHCpan y MHCflurry** sobre un test común: es requisito para publicar.
8. **Tratar la línea RNA-seq/Scipion como camino crítico, no accesorio.** Lo que publicó eLife fue validación in vivo, y su hallazgo fue que la expresión manda. Sugiere ranking por expresión × afinidad.

---

## 0.6. TAREA EN CURSO — Verificación de datos IEDB (abierta el 24 nov 2026)

> **Si la sesión se ha cortado (VPN), empieza por aquí.** Esta subsección es el diario de trabajo de la tarea abierta: se actualiza a cada paso. Es autocontenida: no depende de ningún resumen de conversación.
>
> **Última actualización:** 24 nov 2026, 13:05 UTC. Hallazgos A–E cerrados; re-descarga de familias humanas en curso.
>
> Scripts de esta tarea, todos en `data_pipeline/scripts/iedb_verification_20261124/`: `download_v2.py` (re-descarga), `compare_downloads.py` (viejo vs nuevo por `assay_id`), `wert_chain.py` (cadena de filtrado de Wert), `wert_vs_h2k.py` (Wert vs nuestro H2-K), `wert_missing_source.py` (organismo fuente de los ausentes), `missing_mus.py` (ausentes murinos vs histórico), más `alleles.py`, `fill_rates.py`, `pseudo_coverage.py`, `pseudo_by_class.py`, `diagnose_paging.py`, `inspect_raw.py`.

### 0.6.1. Objetivo de la tarea

Certificar la procedencia de los datos IEDB del pipeline, que §3 y §21 dejan sin documentar (release, filtros de ensayo, criterios de evidencia). Tres comparaciones:

1. **`data_raw` histórico** (snapshot del 10 nov 2026, archivado en `data/used_data/data_raw.tar.zst`) — lo que realmente alimentó D1.
2. **`data/data_raw_20261124`** — re-descarga con los *mismos filtros* pero paginación corregida, para separar «IEDB ha cambiado» de «el paginado antiguo perdía o duplicaba filas».
3. **`reference/neoantigenpred_zip/`** — GitLab de Carlos Wert (`neoantigenpred-master.zip`, ya descomprimido), que contiene el dataset y el código reales de Wert2021.

### 0.6.2. Artefactos localizados

| Artefacto | Ruta | Nota |
|---|---|---|
| Script de descarga del pipeline | `data_pipeline/scripts/data_download/build_iedb_dataset.py` | **Ya revisado.** Paginaba por `offset` **sin `order`**, lo que en PostgREST no garantiza orden estable entre páginas → riesgo de filas perdidas y duplicadas. Causa de la re-descarga. |
| **Script de descarga definitivo** | `data_pipeline/scripts/data_download/build_iedb_dataset_v2.py` | **Escrito el 24 nov; sustituye a `build_iedb_dataset.py`.** Ver §0.6.5. |
| Scripts de esta verificación | `data_pipeline/scripts/iedb_verification_20261124/` | Copiados del scratchpad al repo el 24 nov para que no se pierdan. |
| Snapshot histórico extraído | `data/used_data/data_raw.tar.zst` (3,2 GB al extraer) | Se extrajo al scratchpad; **re-extraíble**, no hace falta conservarlo. |
| Re-descarga nueva | `data/data_raw_20261124/` + `manifest.json` | En curso (ver 0.6.4). |
| Dataset real de Wert2021 | `reference/neoantigenpred_zip/neoantigenpred-master/media/downloadable_content/H2Kb_data.csv` (34 MB) | Export crudo de IEDB en formato de dos filas de cabecera. |
| Código de entrenamiento de Wert2021 | `.../media/scripts/LSTMcvonehot.py` | **Es la implementación de referencia para E0.** Junto a `peptides_extraction.py`, `join_peptide_file.py`, `VEPtoAminoacids.py`, `ModelLoadNap.py`, `tokenizer_Kd.pickle`, `job_cv_h2d_final.hdf5` (checkpoint H-2D entrenado). |
| Pseudosecuencias NetMHCpan | `reference/pseudosequences/pseudosequences.netmhcpan.34aa.csv` | Para la prioridad §0.5.3 (alelo en la entrada). |

### 0.6.2 bis. Qué de esto NO está en GitHub

**Decisión del 24 nov 2026: el repositorio de Carlos Wert no se publica en este GitHub.** `/reference/neoantigenpred_zip/` está ignorado **por completo**: es código y datos de terceros, y no nos corresponde republicarlos. Vive **solo en este servidor**, extraído de `neoantigenpred-master.zip` (en la raíz del repo, ignorado por `*.zip`).

Para reconstruirlo en otra máquina hay que conseguir el ZIP por el canal original y extraerlo:

```bash
unzip -o neoantigenpred-master.zip -d reference/neoantigenpred_zip
```

Dos razones adicionales, encontradas al revisarlo, para no subirlo:

- Traía un fichero `q`: un volcado accidental de `git log` con 159 commits y los **correos personales de cuatro personas**.
- `NeoantigensApp/views.py` contiene un correo personal en una línea comentada de un `send_mail` de ejemplo.
- Sus claves (`SECRET_KEY`, reCAPTCHA) salen de `os.getenv` con defaults vacíos: **no hay credenciales**, eso sí estaba limpio.

Sí se versiona `reference/pseudosequences/pseudosequences.netmhcpan.34aa.csv` (590 KB), que no es material de Wert.

Tampoco están en git, por reglas previas: `data/` (salvo READMEs), `logs/`, `model/`, `results/`, `*.npy`, `*.parquet`. Es decir, **`data/data_raw_20261124` y los logs de descarga también viven solo en este servidor.**

### 0.6.2 ter. Estado de git en este servidor

- **El `origin` real es `git@github.com:LauraPerezLiens/MHC-Epitope-Prediction.git`**, no `lperez_nn`. Corrige §9.1, que listaba ambos sin aclarar cuál estaba en uso.
- Rama de trabajo: `ml_model_comparison`. Commit de esta tarea: `f7cd3d7`.
- **Permiso de push concedido a Claude** en `.claude/settings.json`: `Bash(git push:*)` permitido, con `--force`, `--force-with-lease`, `-f`, `--delete` y `--mirror` **denegados** explícitamente. Lo irreversible sigue requiriendo intervención humana.
- **Autenticación:** la clave `~/.ssh/id_ed25519` de este servidor debe estar registrada en GitHub → Settings → SSH and GPG keys. Si el push falla con `Permission denied (publickey)`, es que no lo está, y los commits se quedan en local hasta registrarla.

### 0.6.3. Hallazgos confirmados

**A. El paginado histórico es sospechoso por diseño.** `build_iedb_dataset.py` usa `offset` sin `order`. La re-descarga usa paginación *keyset* sobre `assay_id` (`order=assay_id.asc`, `assay_id=gt.<último>`), que sí es estable. Los filtros se han mantenido **idénticos** para que la única variable sea el paginado.

**A bis. El paginado antiguo NO estaba roto. La sospecha que motivó la re-descarga era infundada.** Comparación por `assay_id` sobre las 7 familias ya re-descargadas (`compare_downloads.py`):

| | Filas |
|---|---:|
| `data_raw` del 10 nov | 1.284.363 |
| **Duplicadas en el viejo** | **0** |
| `data_raw_20261124` | 1.412.016 |
| **Solo en el viejo** | **1** (una fila de H2-IA `tcell`, retirada de IEDB) |
| Solo en el nuevo | 127.654 |
| En común | 1.284.362 |

Y las 127.654 filas nuevas son **crecimiento real de IEDB, no filas que el viejo se saltara** (`newonly_distribution.py`): su `assay_id` es **estrictamente mayor** que el máximo del snapshot viejo en todas las familias (0,0 % intercaladas; única excepción, 10 filas en HLA-A `tcell`, el 3,5 %). Un paginado que pierde páginas deja huecos repartidos por todo el rango de identificadores; aquí no hay ninguno.

**Conclusión: `data_raw` del 10 nov es un snapshot fiel y completo de IEDB a esa fecha, y D1 no necesita reconstruirse por este motivo.** `offset` sin `order` es frágil por diseño y debe corregirse para el futuro, pero de hecho no dañó estos datos. La re-descarga sigue valiendo la pena por otra razón: da datos más frescos y procedencia certificada con manifiesto.

> Nota para interpretar el crecimiento: +9.216 filas en H2-IA (+45 %), +70.780 en HLA-B (+12 %) y +46.851 en HLA-A (+9 %) en dos semanas corresponden a importaciones masivas de IEDB, coherentes con identificadores consecutivos altos.

**B. El `H2Kb_data.csv` que distribuye Wert no es el snapshot del paper.** Cadena de filtrado reproducida (`wert_chain.py`), replicando `peptides_extraction.py`:

| Paso | Filas |
|---|---:|
| 0. Filas de datos en el CSV | 31.788 |
| 1. Tras descartar `Assay.4 == "Negative"` | 28.150 (quita 3.638) |
| 2. Tras `drop_duplicates` por péptido | 9.827 |
| 3. Con accession de proteína madre → van a UniProt | **8.901** |
| Sin accession (`IEDB_rest`, positivos truncados) | 926, de los cuales 171 con longitud ≥ 12 |
| Proteínas únicas a descargar | 4.473 |

El paper declara **4.828 entradas IEDB**; el CSV distribuido da **8.901**. Es decir, el ZIP contiene un snapshot de IEDB **posterior** al que se publicó, aproximadamente del doble de tamaño. **Consecuencia para E0: reproducir Wert2021 con este CSV no da el mismo conjunto que el paper.** Hay que decidir y documentar cuál de los dos se usa como brazo de control, y no afirmar «mismos datos».

Longitudes de los 8.901 epítopos con accession: 8 aa → 3.789; 9 aa → 3.018; 10 aa → 728; 11 aa → 418; 12–15 aa → 507; 6–7 aa → 24. Confirma que la unidad real es el péptido MHC-I corto (8–11 aa domina), no la ventana de 25 aa — coherente con §0.4.2 y §0.5.4.

**C. Nuestro H2-K y el H-2Kb de Wert solo comparten el 56 % de los positivos** (`wert_vs_h2k.py`, por secuencia de péptido, única clave común):

| Magnitud | Valor |
|---|---:|
| Péptidos únicos en el CSV de Wert | 12.394 |
| De ellos, no-`Negative` | 9.827 |
| `Negative` explícitos | 2.567 |
| Péptidos únicos en nuestro H2-K (`mhc_export`) | 38.888 |
| Idem `tcell_export` | 413 |
| **Positivos de Wert que sí tenemos** | **5.499 (56,0 %)** |
| Positivos de Wert ausentes en nuestro H2-K | 4.328 |
| Nuestros péptidos que Wert no tiene | 33.510 |
| `Negative` de Wert presentes en nuestro conjunto | **0** (coherente: filtramos solo `Positive`) |

**D. La causa del 44 % ausente es el filtro de organismo fuente** (`wert_missing_source.py`). `build_iedb_dataset.py` impone `epitope__source_organism = ilike *Mus musculus*`. De las 8.361 filas de ensayo de Wert que nos faltan, **7.695 (92,0 %) tienen un organismo fuente que no es *Mus musculus***: virus de la coriomeningitis linfocítica (1.658), vaccinia (851), *Gallus gallus* (394), *Trypanosoma cruzi* (345), herpesvirus humano 1 (231), influenza A (229), *Coxiella burnetii* (193), *Yersinia pestis* (176), VPH-16 (149), *Bordetella pertussis* (147)…

Esto significa que **nuestro dataset contiene solo epítopos de origen propio (murino), mientras que el modelo H-2Kb de Wert2021 se entrenó sobre todos los epítopos H-2Kb de IEDB, dominados por los derivados de patógeno.** Es una **quinta diferencia de formulación**, al nivel de las cuatro de §0.4, y no estaba documentada: para neoantígenos tumorales el filtro propio es defendible, pero entonces **la comparación con el 0,865 de Wert2021 no es homogénea**, porque su señal mayoritaria es de patógeno. Hay que decidir explícitamente cuál de los dos universos de epítopos define la tarea, y justificarlo.

**E. Las 666 filas murinas restantes no son una pérdida nuestra: son un defecto del preprocesado de Wert.** Están ausentes **de los dos** snapshots —histórico y nuevo— por igual (`missing_mus.py`: 0 % presentes en el histórico), así que no es el paginado. Desglosadas (`why653.py`):

- **659 filas tienen `Assay.4` vacío y `Allele Name` vacío**: no son filas de ensayo de unión a MHC, no tienen resultado cualitativo ni alelo anotado. `peptides_extraction.py` las admite como positivas porque su filtro es `!= "Negative"`, no `== "Positive"`. Nuestro `ilike *Positive*` las excluye, y hace bien. **El conjunto positivo de Wert2021 contiene ~659 péptidos sin medida de ensayo.**
- **Solo 7 filas** son `Positive` + `H2-Kb` legítimas y ausentes de los nuestros: ruido irrelevante (rotación de IEDB).
- Las 372 «sin organismo» son en buena parte **no péptidos** (`2,4,6-trinitrophenyl group`, ácidos sulfónicos…), excluidas correctamente por `epitope__object_type = Linear peptide`.

A nivel de péptido único en H2-K, el snapshot histórico tiene 38.944 y el nuevo 39.009: **solo 65 de diferencia**. El efecto del paginado, si existe, es pequeño en péptidos únicos; queda por medirlo a nivel de `assay_id`, que es donde se vería la duplicación (pendiente nº 2–3).

**F. El colapso familia→alelo, medido.** Censo de alelos sobre la re-descarga (`alleles.py`, 9 familias ya bajadas):

| Familia | Filas | **Alelos distintos** |
|---|---:|---:|
| human/mhc-I/HLA-B | 665.167 | **125** |
| human/mhc-I/HLA-A | 579.497 | **81** |
| human/mhc-I/HLA-C | 140.172 | **33** |
| mouse/mhc-II/H2-IA | 32.008 | 12 |
| mouse/mhc-I/H2-D | 46.111 | 8 |
| mouse/mhc-II/H2-IE | 406 | 8 |
| mouse/mhc-I/H2-K | 88.669 | 7 |
| mouse/mhc-I/H2-L | 158 | 2 |
| **Total** | | **276** |

El pipeline colapsa **276 alelos en 11 etiquetas de familia**. Esto cuantifica §0.4.1, que hasta ahora era un argumento cualitativo.

**G. Dentro de una misma familia, los alelos comparten la mitad de los residuos de unión.** Pseudosecuencias NetMHCpan de 34 aa, identidad posición a posición:

| Par | Iguales | |
|---|---:|---:|
| H2-Kb vs H2-Kd | 17/34 | **50 %** |
| H2-Kb vs H2-Kk | 21/34 | 62 % |
| H2-Kd vs H2-Kk | 19/34 | 56 % |
| H2-Kb vs H2-Db | 20/34 | 59 % |

**H2-Kb y H2-Kd difieren en la mitad de las posiciones del surco de unión, y el pipeline los trata como la misma clase «H2-K».** Nótese que H2-Kb vs H2-Db (familias *distintas*) se parecen **más** (59 %) que H2-Kb vs H2-Kd (50 %) dentro de la *misma* familia: la partición por familia no agrupa por similitud de unión. Es la explicación estructural de por qué Wert2021 encontró subóptima la predicción cruzada Kb↔Kd y concluyó que hacen falta redes por haplotipo.

**H. La prioridad §0.5.3 (alelo en la entrada) es viable con pérdida mínima.** Cobertura de `reference/pseudosequences/pseudosequences.netmhcpan.34aa.csv` sobre la re-descarga: **190 de 276 alelos, que son el 95,70 % de las filas** (1.485.485 de 1.552.188). El 4,30 % sin cubrir son, casi todos, **serotipos de baja resolución, no alelos**: `HLA-A2`, `HLA-A24`, `HLA-B7`, `HLA-B27`… más los de clase II de ratón (`H2-IAb` con 23.624 filas, `H2-IAg7`) que esa tabla de clase I no incluye, y dos mutantes puntuales (`HLA-B*27:05 C67S mutant`). Son filas a descartar o a resolver aparte, no un obstáculo de diseño.

**I. Los filtros IEDB, certificados desde el código** (`build_iedb_dataset.py:253-260`). Esto es lo que §3 y §21 declaraban ausente. Endpoints: `https://query-api.iedb.org/mhc_export` y `/tcell_export`, ambos consultados para cada familia.

| Filtro | Valor | Qué implica |
|---|---|---|
| `epitope__object_type` | `eq.Linear peptide` | Excluye epítopos discontinuos y no péptidos. Correcto. |
| `assay__qualitative_measurement` | `ilike.*Positive*` | **Solo ensayos positivos.** Admite `Positive`, `Positive-High`, `-Intermediate`, `-Low` sin distinguirlos. |
| `mhc_restriction__class` | `eq.I` / `eq.II` | — |
| `host__name` | `ilike.*{especie}*` | Especie del hospedador del ensayo. |
| `mhc_restriction__name` | `ilike.*{familia}*` | **Coincidencia por subcadena**, no por alelo. Es el mecanismo del colapso 276→11 (hallazgo F). |
| `epitope__source_organism` | `ilike.*{especie}*` | **Causa del hallazgo D:** restringe a epítopos de origen propio y excluye los de patógeno. |

**Consecuencia que conviene tener presente: no se descarga ni un solo ensayo negativo de IEDB.** El filtro `ilike.*Positive*` lo impide. Por tanto los «negativos» del dataset **no son negativos experimentales**, sino ventanas sin anotación positiva. Confirma §4.3 desde el código, y refuerza que la tarea es positive-unlabeled. **Wert2021 tampoco tenía negativos experimentales** —eso lo corrige §0.7.6, leído de su código— pero sí construía **señuelos de la misma proteína fuente**, que es un fondo mucho más exigente que una ventana sin anotación cualquiera.

**Lo que NO se filtra**, y debería documentarse como limitación: tipo de ensayo (unión frente a elución frente a célula T, todos mezclados), calidad o nivel de evidencia, y resolución del alelo (entran serotipos como `HLA-A2` junto a alelos de cuatro dígitos; véase hallazgo H).

**Paginación histórica:** `limit` fijo con `offset = página × limit` y **sin `order`** (`build_iedb_dataset.py:149-175`). Frágil por diseño, aunque de hecho no dañó los datos (hallazgo A bis). La re-descarga lo sustituye por keyset sobre `assay_id`.

**Sobre la *release* de IEDB: no se puede certificar, porque IEDB no la publica.** Comprobado el 24 nov recorriendo los 39 endpoints del swagger de `query-api.iedb.org`: no existe ninguno de versión, release ni metadatos (el `"version": "14.3"` del swagger es la versión de **PostgREST**, no de la base). Sustituto adoptado: **huella de contenido por consulta** en el manifiesto — número de filas, `min`/`max assay_id`, `assay_id` distintos, alelos distintos, SHA-256 y tamaño del CSV. Con eso dos descargas son comparables bit a bit aunque IEDB no diga en qué versión está.

**J. El filtro `ilike.*Positive*` nos ha estado privando de negativos experimentales reales, y son muchos.** Medido sobre H2-L con el perfil `full` del script nuevo (sin filtro cualitativo y sin filtro de organismo fuente):

| | `mhc_export` | `tcell_export` |
|---|---:|---:|
| Perfil `legacy` (lo que alimentó D1) | 44 | 114 |
| Perfil `full` | **534** | **1.488** |
| De ellas, `Negative` explícitas | **210 (39,3 %)** | **518 (34,8 %)** |
| `Positive` + variantes High/Low/Intermediate | 324 | 970 |
| Organismos fuente distintos | 69 | 84 |

Es decir: para H2-L había **728 ensayos negativos experimentales en IEDB** que el pipeline nunca vio. §4.3 trataba la tarea como positive-unlabeled por necesidad; **en buena medida no era necesario**. Esto no elimina el carácter PU del problema (las ventanas sin anotación siguen siendo unlabeled), pero permite un conjunto de negativos *medidos* con el que calibrar, y acerca el diseño al de Wert2021 — que **tampoco** tenía negativos experimentales, sino señuelos de la propia proteína fuente (§0.7.6).

> Ojo al interpretar el 12× de H2-L: se debe a los negativos **y** a los epítopos de patógeno a la vez. No es comparable sin desglosar, y H2-L es la familia más pequeña; no extrapolar el factor a HLA-A.

**K. El filtro de organismo fuente también descarta las filas sin organismo anotado.** En H2-L `mhc` perfil `full`, 169 de 534 filas (31,7 %) tienen `epitope__source_organism` vacío. `ilike.*Mus musculus*` las elimina en silencio junto con las de patógeno. Hay que decidir explícitamente qué se hace con las no anotadas.

**L. La etiqueta de alelo es, en su mayoría, inferida — no medida.** Censo de `mhc_restriction__evidence_code`, que `build_iedb_dataset.py` nunca consultó:

| Código de evidencia | H2-K | HLA-A |
|---|---:|---:|
| Elución con anticuerpo específico de MHC | **84.020 (95,9 %)** | 130.665 (23,0 %) |
| Inferido estadísticamente por motivo o alelos presentes | 2.583 | **242.842 (42,7 %)** |
| **Un solo alelo presente** (atribución directa) | **627 (0,7 %)** | 173.688 (30,5 %) |
| Sin código | 363 | 6.239 |

En H2-K, **solo el 0,7 % de las filas tiene el alelo atribuido de forma directa**; el 95,9 % lo tiene atribuido por el anticuerpo usado en la elución (Y-3, SF1-1.1.1…), que no distingue entre alelos de la misma familia. En HLA-A, el 42,7 % es inferencia por motivo — es decir, **la etiqueta de alelo procede de un predictor, no de un experimento**, con el riesgo de circularidad que eso implica para entrenar sobre ella. Es una limitación que debe declararse y, probablemente, un criterio de filtrado o de ponderación.

**M. No hay afinidad cuantitativa aprovechable.** `assay__quantitative_measurement` está relleno en el **0,16 %** de H2-K y el **0,68 %** de HLA-A (3.293 filas en nM sobre 569.013). **Descarta por completo plantear regresión de afinidad** sobre estos datos; la tarea solo puede ser cualitativa.

**N. El tipo de ensayo está dominado por inmunopeptidómica, no por unión.** `assay__method` en H2-K: `cellular MHC/mass spectrometry` 85.432 (97,5 %), `mass spectrometry` 1.539, unión competitiva purificada 59. En HLA-A: espectrometría de masas 562.708 (98,9 %), unión 3.529. Lo que el dataset mide mayoritariamente es **presentación (ligandos eluidos)**, no afinidad de unión ni inmunogenicidad. Para la comparación con NetMHCpan/MHCflurry (§0.5.7) importa: hay que comparar contra sus modelos de **presentación/eluted ligand**, no contra sus predicciones de afinidad.

**O. Riesgo de fuga por publicación, no detectado hasta ahora.** `reference__pmid` tiene solo **89 valores distintos para las 87.593 filas de H2-K** y 583 para las 569.013 de HLA-A. Un único estudio de inmunopeptidómica aporta decenas de miles de filas con el mismo tipo celular, el mismo anticuerpo y el mismo sesgo de preparación. **Particionar por proteína no protege de esto:** un modelo puede aprender la huella técnica de un laboratorio. Hay que medir la fuga por `pmid` y considerar partición por publicación como control adicional, al nivel de la partición por componentes de proteína de §0.2.

**Q. `tcell_export` usa un vocabulario de ensayo y de evidencia COMPLETAMENTE DISTINTO al de `mhc_export`,** y el pipeline los concatenaba sin distinguirlos. En `tcell_export` los métodos son ELISPOT, 51-cromo, ICS, ELISA, multímero/tetrámero, SPR, ensayo in vivo, 3H-timidina… es decir **inmunogenicidad**, no presentación ni unión. Y los códigos de evidencia del alelo son otros: `Cited reference`, `Not determined`, `MHC binding assay` y —lo importante— **`MHC binding prediction`**.

**Hay, por tanto, tres objetivos distintos mezclados en una sola etiqueta binaria:** presentación (elución por espectrometría, mayoría de `mhc_export`), afinidad de unión, e inmunogenicidad (`tcell_export`). No son intercambiables. Esto se suma al hallazgo N y refuerza §0.4: parte del techo 0,66–0,68 puede venir de que la etiqueta agrega fenómenos distintos.

**R. Hay filas cuyo alelo lo asignó un predictor, no un experimento.** `MHC binding prediction` como `mhc_restriction__evidence_code`: 179 filas en el `tcell_export` de H2-L (perfil `full`), 110 tras agregar por péptido-alelo. **Entrenar sobre ellas es circular**: el modelo aprendería la salida de otro modelo. Junto con el 42,7 % de HLA-A inferido por motivo (hallazgo L), define un criterio de filtrado obligatorio antes de publicar cualquier comparación con NetMHCpan: **excluir las filas cuya etiqueta de alelo provenga de una predicción.**

**P. La resolución de alelo en humano es buena; el problema es el colapso, no los datos.** En HLA-A: 554.918 filas (97,5 %) con alelo de cuatro dígitos (`HLA-A*02:01`…), 14.071 (2,5 %) serotipos de baja resolución (`HLA-A24`, `HLA-A2`…) y 3 mutantes. Los serotipos son además mayoritariamente de elución (72,7 %), coherente con el hallazgo L. **Conclusión: trabajar por alelo es viable sin apenas pérdida; el 2,5 % de serotipos se descarta o se trata aparte.** Nótese el desbalance extremo: `HLA-A*02:01` es 219.292 filas, el 38,5 % de HLA-A.

### 0.6.4. Estado de la re-descarga (proceso vivo)

**TERMINADA** el 24 nov a las 14:32 UTC (`download_v2.py`, log en `logs/download_v2_20261124.log`, marca `DONE`). Las 11 familias, **2.177.675 filas** en total, con `manifest.json` completo.

| Familia | `mhc` | `tcell` |
|---|---:|---:|
| mouse/mhc-I/H2-K | 87.593 | 1.076 |
| mouse/mhc-I/H2-D | 45.583 | 528 |
| mouse/mhc-I/H2-L | 44 | 114 |
| mouse/mhc-II/H2-IA | 29.895 | 2.113 |
| mouse/mhc-II/H2-IE | 233 | 173 |
| human/mhc-I/HLA-A | 569.013 | 10.484 |
| human/mhc-I/HLA-B | 664.053 | 1.114 |
| human/mhc-I/HLA-C | 139.852 | 320 |
| human/mhc-II/HLA-DR | 405.608 | 6.375 |
| human/mhc-II/HLA-DQ | 50.191 | 780 |
| human/mhc-II/HLA-DP | 162.186 | 347 |

> **Esta descarga es del perfil `legacy`**: mismos filtros que `build_iedb_dataset.py`, es decir **solo positivos y solo epitopos de la propia especie**. Sirvio para verificar procedencia, que era su proposito. Para trabajar (E0, negativos, alelo en la entrada) hace falta una descarga del perfil `full` con `build_iedb_dataset_v2.py` (véase §0.6.5).

> **Nota sobre H2-L: 44 filas en `mhc_export`** con el perfil `legacy`, frente a **534** con el perfil `full`. §3.1 atribuye 69 M de filas BLOSUM historicas a H2-L: con 44 ensayos, esa cifra solo puede venir de expansion masiva por ventanas mas aumento. Merece comprobacion explicita.

### 0.6.5. El script de descarga definitivo

`data_pipeline/scripts/data_download/build_iedb_dataset_v2.py`, escrito el 24 nov 2026. **Sustituye a `build_iedb_dataset.py`**, que no debe volver a usarse para datos nuevos (se conserva solo para reproducir la procedencia de D1). Probado en vivo sobre `mouse/mhc-I/H2-L` en los dos perfiles.

**Tres cambios de fondo**, cada uno atado a un hallazgo:

1. **Paginación keyset** sobre `assay_id` (`order=assay_id.asc` + `assay_id=gt.N`) en lugar de `offset` sin `order`. El viejo no dañó los datos (hallazgo A bis) pero es frágil por diseño.
2. **Los negativos ya no se excluyen por defecto** (hallazgo J). El valor cualitativo se descarga tal cual y el filtrado se decide en el procesado, no en la descarga.
3. **El filtro de organismo fuente es una elección explícita de perfil** (hallazgos D y K), no una decisión enterrada en el código.

**Dos perfiles, `--profile` obligatorio** —a propósito, para que nadie lance una descarga de varios millones de filas por omisión:

| Perfil | Filtro cualitativo | Filtro de organismo fuente | Para qué |
|---|---|---|---|
| `legacy` | `ilike.*Positive*` | `ilike.*<especie>*` | Reproduce el universo exacto de D1. Verificar procedencia. |
| `full` | **ninguno** | **ninguno** | Superconjunto: negativos experimentales + epítopos de patógeno. Es el universo de Wert2021 y el necesario para E0. |

**Lo que conserva y el viejo tiraba.** La salida es el export completo de IEDB (113 columnas), y el alelo (`mhc_restriction__name`) se guarda **literal**. La familia se usa solo para *enumerar* las consultas, nunca como etiqueta: colapsar 276 alelos en 11 familias es el primer problema de diseño del modelo (hallazgo F). Columnas que ahora sí se explotan: `mhc_restriction__evidence_code` (hallazgo L), `assay__method` (N), `reference__pmid` (O), `epitope__starting_position`/`ending_position` y `epitope__molecule_parent`.

**Procedencia.** Manifiesto con huella de contenido por consulta (filas, `min`/`max assay_id`, `assay_id` distintos, alelos distintos, SHA-256, bytes), parámetros exactos de cada petición, fecha UTC y commit de git. **Reanudable**: las consultas ya presentes en el manifiesto se omiten salvo `--force`, y el manifiesto se reescribe tras cada consulta. Se niega a escribir en un directorio cuyo manifiesto sea de otro perfil, para que no se mezclen universos de datos.

```bash
P=/home/nap/miniconda3/envs/nap_env/bin/python   # requests + pandas
# universo Wert2021 / E0, con negativos:
$P data_pipeline/scripts/data_download/build_iedb_dataset_v2.py \
    --profile full --out data/data_raw_full_YYYYMMDD
# una sola familia:
$P ... --profile full --out DIR --only mouse/mhc-I/H2-K
```

> **Entorno:** `pandas` y `requests` están en `nap_env`, **no** en `base`. Usar `/home/nap/miniconda3/envs/nap_env/bin/python`.

### 0.6.6. Verificación a tres bandas, cerrada sobre las 11 familias

Script: `data_pipeline/scripts/iedb_verification_20261124/verify_download.py`. Consolida y sustituye a `compare_downloads.py`, `newonly_distribution.py` y `wert_vs_h2k.py`. Informe: [`reports/audits/iedb_verificacion_descarga_20261124.md`](reports/audits/iedb_verificacion_descarga_20261124.md), detalle en el `.json` hermano.

Dos comparaciones con **claves distintas, y eso no es un detalle**: nuevo contra viejo por `assay_id` (única forma de separar «IEDB creció» de «el paginado falló»), y nuestro H2-K contra Wert **por secuencia de péptido**, porque su CSV viene de otro export y no tiene `assay_id` utilizable.

**Resultado sobre las 11 familias** (antes solo había 7):

| Magnitud | Valor |
|---|---:|
| Filas en el snapshot del 10 nov | 1.985.260 |
| **Duplicadas en el viejo** | **0** |
| Filas en la re-descarga del 24 nov | 2.177.675 |
| **Solo en el viejo** | **1** |
| Solo en el nuevo | 192.416 |
| **De ellas, intercaladas** (por debajo del máx. `assay_id` viejo) | **33 (0,017 %)** |
| En común | 1.985.259 |

`verify_download.py` añade la columna *intercalado*, que es la prueba diagnóstica: un paginado que pierde páginas deja huecos repartidos por todo el rango de identificadores. Hay 33 sobre 192.416. **Hallazgo A bis queda cerrado y confirmado sobre el conjunto completo: el paginado antiguo no dañó los datos y D1 no se reconstruye por este motivo.** Las 192.383 restantes son crecimiento de IEDB en dos semanas, concentrado en HLA-B (+70.780), HLA-DR (+58.691), HLA-A (+46.851) y H2-IA (+9.216).

Lado Wert, reconfirmado: 12.394 péptidos únicos, 9.827 positivos por su criterio real (`!= "Negative"`), de los que tenemos **5.504 (56,01 %)**. Nuestros 45.150 péptidos de H2-K incluyen 39.646 que él no tiene. **`negativos de wert presentes = 0`**, lo que es la comprobación de consistencia del perfil `legacy`: no descarga negativos por construcción.

### 0.6.7. Procesado: de IEDB a tabla por péptido y alelo

`data_pipeline/scripts/data_processing/build_peptide_table.py`. **Este es el paso intermedio que faltaba en el pipeline.** El histórico iba de IEDB a ventanas de 25 aa de un salto y por el camino tiraba casi toda la información del ensayo. Este script no decide la tarea: **anota, clasifica y marca contradicciones**, dejando las decisiones como filtros aplicables sobre la salida.

Salida: un Parquet por familia, **una fila por (alelo literal, péptido)**. Se agrupa por `allele_raw` y no por el normalizado, porque agrupar por el normalizado fundiría los serotipos con alelos reales.

| Columna | Para qué sirve |
|---|---|
| `allele_raw`, `allele_norm`, `allele_resolution` | Alelo literal, normalizado al vocabulario NetMHCpan, y su resolución (`4digit`/`serotype`/`mutant`). |
| **`pseudosequence`** | **34 aa del surco de unión. Es la columna que permite probar si meter el alelo en la entrada mejora la red (§0.5.3).** |
| `label`, `label_tier`, `n_positive`, `n_negative` | Etiqueta por voto mayoritario y el detalle que la sostiene. |
| **`conflicting`** | **Mismo péptido y mismo alelo con ensayos positivos Y negativos.** Ruido de etiqueta real, no artefacto del colapso por familia. |
| `assay_class` | `elution_ms` (presentación) / `binding` (afinidad) / `tcell_functional` (inmunogenicidad) / `structural`. Separa los tres objetivos del hallazgo Q. |
| `allele_evidence_class` | `direct` / `antibody` / `inferred_motif` / **`prediction`** / `binding_assay` / `tcell_assay` / `cited` / `not_determined`. Permite excluir las filas circulares del hallazgo R. |
| `affinity_nm` | Solo en nM; el resto de unidades (ángstroms, minutos, grados) se descarta. Relleno del 0,16–0,68 %: inservible para regresión. |
| `parent_accession`, `start_pos`, `end_pos` | Reconstruir ventanas o generar negativos del mismo proteoma. |
| `pmid`, `n_pmids` | **Eje de fuga no cubierto por la partición por proteína** (hallazgo O). |
| `peptide_canonical` | `False` si el péptido tiene letras fuera de los 20 canónicos. |

**Normalización de alelo.** IEDB y NetMHCpan no usan el mismo vocabulario: `HLA-A*02:01` → `HLA-A0201`, `H2-Kb` → `H-2-Kb`. Los mutantes y serotipos devuelven `None` y se quedan sin pseudosecuencia, como corresponde.

> **Limitación: NUESTRA tabla de pseudosecuencias es solo de clase I.** Comprobado: 11.839 entradas HLA-A/B/C más primates/bóvidos/cerdo, y **ninguna** de HLA-DR/DQ/DP ni de H2-IA/IE, de modo que las cuatro familias de clase II salen con `con_pseudosecuencia_pct` = 0,0 %. **No es un obstáculo conceptual: NetMHCIIpan también usa 34 residuos (15 de la cadena α + 19 de la β).** Falta el fichero, no el método — véase §0.7.1.

Validado sobre tres familias:

| Familia / perfil | Filas péptido-alelo | Péptidos | Alelos | Prevalencia | Contradictorios | Con pseudosec. |
|---|---:|---:|---:|---:|---:|---:|
| H2-K (`legacy`) | 61.917 | 45.150 | 7 | 100 % | 0 | 100,0 % |
| HLA-A (`legacy`) | 247.327 | 177.490 | 81 | 100 % | 0 | 95,4 % |
| H2-L (`full`) | 1.012 | 1.000 | 2 | **44,57 %** | **67 (6,62 %)** | 100,0 % |

La prevalencia de 100 % y los 0 contradictorios en el perfil `legacy` **no son un error: son la comprobación de que el filtro `ilike.*Positive*` hace imposible medir contradicción**. Solo con el perfil `full` aparece estructura: prevalencia real del 44,57 % y un **6,62 % de pares péptido-alelo con evidencia experimental contradictoria**. Ese número no se podía conocer antes.

```bash
P=/home/nap/miniconda3/envs/nap_env/bin/python
$P -u data_pipeline/scripts/data_processing/build_peptide_table.py \
    --raw data/data_raw_20261124 --out data/peptide_table_20261124
```

### 0.6.8. Pendiente, en orden

**Cerrado el 24 nov:** ~~esperar la re-descarga~~ (terminada, 11/11); ~~comparacion por `assay_id`~~ (hecha sobre las 11, §0.6.6); ~~cuantificar el dano del paginado~~ (1 fila; 33 intercaladas de 192.416); ~~comparar con el `H2Kb_data.csv` de Wert~~ (56,01 %); ~~explicar las 666 filas murinas~~ (hallazgo E); ~~script de descarga definitivo~~ (§0.6.5); ~~cómo procesar lo descargado~~ (§0.6.7); ~~certificar la release de IEDB~~ (no existe endpoint; sustituida por huella de contenido).

Lo que queda, por orden:

1. ~~**Decidir el universo de epítopos.**~~ **DECIDIDO el 24 nov: los dos, como dos brazos.** Se descarga el perfil `full` una sola vez y los dos subconjuntos se derivan con un filtro sobre la tabla de péptidos (`source_is_self`). Así E0 queda comparable con Wert2021 **y** se conserva el modelo de neoantígenos, y **la diferencia entre ambos universos pasa a ser un resultado medible en lugar de una limitación declarada**. Ver §0.6.9.
2. ~~**Lanzar la descarga del perfil `full`.**~~ **EN CURSO** desde el 24 nov, 14:51 UTC → `data/data_raw_full_20261124`, log en `logs/download_full_20261124.log`. Disco comprobado: el perfil `legacy` ocupa 311 MB y hay 20 TB libres en `/data`, así que el factor 12× de H2-L no es un riesgo. **Para comprobar si terminó:** `tail -3 logs/download_full_20261124.log` (buscar `DONE`) y `pgrep -f "profile full"`. Es reanudable: relanzar el mismo comando omite las consultas ya presentes en el manifiesto.
3. **Decidir la politica de filtrado sobre la tabla de peptidos**, con las columnas que §0.6.7 ya deja anotadas. Cuatro decisiones, ninguna obvia. **`assay_class` quedó pospuesta a propósito el 24 nov: se decide con los recuentos reales de las 11 familias delante, no antes** (ver §0.6.9).
   - **`allele_evidence_class`:** excluir `prediction` es obligatorio (circularidad, hallazgo R). Que hacer con `inferred_motif` (42,7 % de HLA-A) y `antibody` (95,9 % de H2-K) es un juicio de valor: excluirlos deja H2-K practicamente sin datos.
   - **`assay_class`:** elegir UN objetivo (presentacion, union o inmunogenicidad) o modelarlos por separado. Mezclarlos es lo que se ha hecho hasta ahora (hallazgo Q).
   - **`conflicting`:** excluir, o conservar como medida de ruido irreducible.
   - **`allele_resolution`:** descartar los serotipos (2,5 % en HLA-A) o resolverlos aparte.
4. **Medir la fuga por `pmid`** y anadir la particion por publicacion como control, al nivel de la particion por componentes de proteina de §0.2 (hallazgo O). No estaba contemplada y la particion por proteina no la cubre.
5. **Probar el alelo como entrada** (§0.5.3): la columna `pseudosequence` ya está poblada al 95–100 % en clase I, así que es ejecutable hoy. Para clase II hay que **conseguir primero la tabla de pseudosecuencias de NetMHCIIpan** (34 residuos, 15 α + 19 β); véase §0.7.1.
6. **Escribir el informe de procedencia** en `reports/audits/iedb_provenance_20261124.md`, actualizar §3 con filtros y criterios reales, y anadir el hallazgo D a §0.4 como quinta decision de diseno.
7. **Luego, no antes:** E0 (§0.5.1), con `LSTMcvonehot.py` como referencia, decidiendo primero si el brazo de control usa los 4.828 del paper o los 8.901 del CSV distribuido.

### 0.6.9. Decisiones tomadas en esta tarea

- Mantener los filtros IEDB **idénticos** a `build_iedb_dataset.py` en la re-descarga, para aislar el efecto del paginado. Cambiar filtros y paginado a la vez haría la comparación ininterpretable.
- Comparar por `assay_id`, no por conteo de filas: es la única forma de distinguir «IEDB cambió» de «el paginado falló».
- No borrar `data/data_raw_20261124` ni el histórico: D1 debe seguir siendo reproducible mientras no se decida reconstruirlo.

**Decisiones del 24 nov por la tarde, tras medir:**

- **Dejar de excluir los negativos experimentales en la descarga.** El filtro `ilike.*Positive*` se baja al perfil `legacy` y deja de ser el comportamiento por omisión. Motivo: hallazgo J, en H2-L había 728 ensayos negativos que el pipeline nunca vio. El carácter positive-unlabeled de §4.3 era en parte **autoimpuesto**, no inherente al problema.
- **El alelo se conserva literal y la familia pasa a ser solo un mecanismo de enumeración de consultas**, nunca una etiqueta de entrenamiento. Motivo: hallazgos F y G.
- **El universo de epítopos se resuelve con dos brazos, no eligiendo uno.** Se descarga el superconjunto (`full`) una vez y los dos universos se derivan por filtro (`source_is_self`). Convierte la quinta diferencia de formulación del hallazgo D en una comparación medible.
- **La elección de objetivo supervisado (presentación / unión / inmunogenicidad) se posterga deliberadamente** hasta tener los recuentos por `assay_class` de las 11 familias. Es una decisión que no se puede tomar bien a ciegas y que hasta ahora se había tomado por omisión, mezclando los tres.
- **Añadir un paso intermedio explícito al pipeline**: IEDB → tabla por (alelo, péptido) → ventanas/péptidos. El salto directo de IEDB a ventanas de 25 aa es lo que hacía invisibles los hallazgos L, N, O, Q y R.
- **No volver a usar `build_iedb_dataset.py` para datos nuevos.** Se conserva únicamente para reproducir la procedencia de D1.

---

## 0.7. Preguntas abiertas de diseño (planteadas el 24 nov 2026)

Cinco cuestiones que Laura planteó tras ver los hallazgos de §0.6. **No hay que resolverlas ya**; quedan aquí con lo que se sabe, lo que se ha medido y lo que falta por decidir. Dos de ellas traen decisión tomada.

### 0.7.1. ¿Por qué NetMHCpan usa 34 aminoácidos? ¿Y qué hacemos con clase II?

**Por qué 34.** No es un número arbitrario ni un hiperparámetro: son las **posiciones polimórficas del MHC que están a menos de 4,0 Å de un átomo pesado del péptido unido, con la cadena lateral orientada hacia él**, identificadas sobre estructuras cristalográficas representativas. Es decir, es **el surco de unión reducido a sus residuos que (a) tocan al péptido y (b) varían entre alelos**. Incluye además algunas posiciones que contactan a través de moléculas de agua (118 y 158). Lo que la pseudosecuencia codifica, por tanto, no es «el alelo» sino **la química del bolsillo que ve el péptido**, y eso es lo que permite que el método sea *pan-específico*: alelos nunca vistos en entrenamiento quedan interpolados por similitud de surco.

**Clase II: me equivoqué al decir que estaba bloqueada.** **NetMHCIIpan sí tiene pseudosecuencia, y también es de 34 residuos: 15 de la cadena α y 19 de la cadena β**, construida con el mismo criterio de 4,0 Å (método de Karosiene et al., NetMHCIIpan-3.0). Lo que falta **no es el concepto, es nuestra tabla de referencia**: `reference/pseudosequences/pseudosequences.netmhcpan.34aa.csv` es solo de clase I (11.839 entradas HLA-A/B/C más primates, bóvidos y cerdo; cero de HLA-DR/DQ/DP y de H2-IA/IE). Verificado el 24 nov: las 11 familias de clase II salen con **`con_pseudosecuencia_pct` = 0,0 %**.

Hay un detalle biológico que importa para clase II: **en HLA-DR el polimorfismo está casi todo en la cadena β, mientras que en DP y DQ ambas cadenas son polimórficas.** Por eso la pseudosecuencia de clase II necesita las dos cadenas, y por eso DQ/DP son más difíciles: hay que emparejar α y β, y IEDB no siempre anota las dos.

**Pendiente, y hay una acción concreta que solo puede hacer Laura.** Documentación completa en [`reference/pseudosequences/README.md`](reference/pseudosequences/README.md), escrito el 24 nov. Dos vías:

1. **Pedir el paquete autónomo de NetMHCIIpan 4.3 a DTU.** La tabla va dentro de `data.Linux.tar.gz`. El acceso es por **solicitud de licencia académica** (formulario de descarga, o `health-software@dtu.dk`). **Requiere el correo institucional de Laura; no es automatizable.** Merece la pena porque el mismo paquete resuelve dos cosas a la vez: las pseudosecuencias de clase II **y** el predictor de referencia que §0.5.7 exige para publicar.
2. **Derivarla de los alineamientos de IPD-IMGT/HLA** aplicando el criterio de 4,0 Å sobre estructuras de clase II. Sin licencia y reproducible, pero hay que elegir estructuras de referencia y validar que las posiciones coinciden con las de Karosiene et al.; cualquier desviación invalidaría la comparación directa con NetMHCIIpan.

> ⚠️ **Y un problema con el fichero de clase I que ya tenemos:** apareció en el repositorio sin README ni manifiesto. Procede presumiblemente del paquete de NetMHCpan, pero **no consta versión ni cómo se obtuvo**, y no hay ningún paquete de NetMHC instalado en este servidor. Dado que §0.5.7 exige comparar contra NetMHCpan para publicar, **su origen y versión deben certificarse antes de apoyar resultados en él.**

Hasta entonces la prioridad §0.5.3 es ejecutable en clase I y está a la espera en clase II **por falta de un fichero, no por un obstáculo conceptual**.

**¿Probar otras representaciones y tamaños de pseudosecuencia?** Sí, y es una de las pocas vías de diferenciación con fundamento (ver §0.7.5). Pero con dos condiciones metodológicas: (a) **la de 34 aa es el brazo de control obligatorio** —sin él, «nuestra representación es mejor» no se sostiene—, y (b) la comparación debe hacerse con partición por alelo, no por fila, o se medirá memorización. Ideas ordenadas por coste: pseudosecuencia completa del dominio de unión (~180 aa) en lugar de los 34; embedding del MHC con ProtT5, que ya está en el pipeline; representación por bolsillo (agrupar los 34 residuos por bolsillo A–F en vez de como vector plano); y codificación explícita del par péptido-MHC por posición en lugar de concatenación.

### 0.7.2. Usar epítopos de todas las especies — DECIDIDO

**Decisión de Laura, 24 nov: sí.** El razonamiento es sólido y conviene dejarlo escrito: *lo que interesa es la función respecto al MHC; si esa secuencia se une, da igual de dónde provenga.* Biológicamente es correcto —el surco no sabe si el péptido es vírico o propio— y además **multiplica los datos**: solo en H-2Kb recupera los ~4.300 positivos de Wert que nos faltaban (hallazgo D), y en H2-L el factor fue 12×.

Esto **refina** la decisión de los dos brazos de §0.6.9: el **brazo primario pasa a ser todos los organismos fuente**, y el subconjunto propio queda como **ablación** para cuantificar si el origen del epítopo aporta señal. Sigue derivándose por filtro sobre `source_is_self`, así que no cambia nada del pipeline de descarga.

> **Dos matices que no invalidan la decisión pero hay que declarar.** Primero: los epítopos de patógeno tienen **composición y sesgo de longitud distintos** de los propios, y el modelo final se aplicará a neoantígenos tumorales, que son propios con una mutación; conviene medir el rendimiento **en el subconjunto propio** aunque se entrene con todo. Segundo: el 31,7 % de las filas de H2-L no tiene organismo anotado (hallazgo K); con esta decisión dejan de ser un problema, porque ya no se filtran.

### 0.7.3. ¿Ampliar con otras bases de datos?

Pregunta aparcada hasta tener resultados, que es lo correcto: **primero saber si el techo es de datos o de formulación.** §0.2 sugiere que es de formulación (eliminar toda la fuga por proteína cuesta 0,0054 de ROC-AUC), así que más datos de la misma clase podrían no mover nada. Candidatos a evaluar **cuando llegue el momento**, sin verificar todavía:

- **Datos monoalélicos de inmunopeptidómica** (líneas celulares que expresan un solo alelo). Son el antídoto exacto al hallazgo L: alelo atribuido de forma directa en lugar de por anticuerpo. Probablemente la mejora de calidad más alta por unidad de esfuerzo.
- **Atlas de inmunopeptidoma** (del tipo SysteMHC / HLA Ligand Atlas) para ampliar cobertura de alelos poco representados; recordar que `HLA-A*02:01` ya es el 38,5 % de HLA-A.
- **Datos de entrenamiento de NetMHCpan/MHCflurry**, que son públicos. **Cuidado: usarlos contamina el benchmark contra esos mismos predictores.** Si se usan para entrenar, la comparación de §0.5.7 deja de ser limpia.
- **Proteomas de referencia** (UniProt) para negativos emparejados por longitud del mismo proteoma, al estilo Wert2021. Esto **no es «otra base de datos de epítopos»**, es construcción de negativos, y es más urgente que ampliar positivos.

> Antes de añadir cualquier fuente: **deduplicar por péptido contra lo que ya hay y volver a medir la fuga**. Añadir una base que solape con IEDB inflaría las métricas sin añadir información.

### 0.7.4. Elución MS como primer objetivo — DECIDIDO

**Decisión de Laura, 24 nov: empezar por elución MS**, es decir «¿se va a unir/presentar en MHC?», y dejar el reconocimiento por TCR para más adelante, como salida adicional de probabilidad de inmunogenicidad. **Los datos respaldan esta decisión de forma contundente.** Censo de `assay_class` sobre la tabla completa de las 11 familias (1.260.105 pares péptido-alelo):

| Clase de ensayo | Pares péptido-alelo | % |
|---|---:|---:|
| **`elution_ms`** (presentación) | **1.243.014** | **98,64 %** |
| `binding` (afinidad) | 14.258 | 1,13 % |
| `tcell_functional` (inmunogenicidad) | 7.478 | 0,59 % |
| `other` | 499 | 0,04 % |
| `structural` | 234 | 0,02 % |

Es decir: **la elución MS es la única clase con datos de sobra**, y la decisión de empezar por ella es robusta.

> ⚠️ **Pero estas cifras son del perfil `legacy` y el 0,59 % de inmunogenicidad se queda corto.** Medido sobre las 5 familias de ratón ya descargadas con el perfil `full`, los `tcell_export` crecen de forma brutal: **H2-K de 1.076 a 15.626 filas (14,5×)** y **H2-D de 528 a 14.830 (28×)**; en conjunto el ratón pasa de 4.004 a 46.219. Es coherente: los ensayos funcionales de célula T son justo donde más negativos experimentales hay y más epítopos de patógeno se han estudiado, y el perfil `legacy` excluía ambas cosas. **Conclusión provisional: la vía de inmunogenicidad puede resultar bastante más viable de lo que sugiere la tabla de arriba.** Recalcular este censo sobre `data_raw_full_20261124` cuando termine, antes de dar por cerrada la proporción entre clases.

Implicaciones que conviene fijar ahora:

1. **El objetivo es presentación, no afinidad ni inmunogenicidad.** Hay que decirlo así en el paper y en la documentación: lo que el modelo predice es «este péptido fue eluido de este MHC».
2. **La comparación con NetMHCpan/MHCflurry debe usar sus modos de *eluted ligand*, no los de afinidad** (§0.5.7). Comparar contra su predicción de afinidad sería comparar tareas distintas.
3. **La vía de inmunogenicidad va como modelo aparte**, no como etiqueta mezclada. Con las cifras del perfil `full` habrá que reevaluar su tamaño; si se queda en decenas de miles de pares, no sostiene una red profunda pero sí un clasificador sobre los embeddings ya calculados, o un *fine-tuning* del modelo de presentación. Encaja con lo que validó eLife 2024.
4. **Un modelo de presentación es exactamente el que necesita el ranking por expresión × presentación** que sugiere el hallazgo central de eLife 2024.

### 0.7.5. ¿En qué nos distinguimos de NetMHCpan? (la pregunta importante)

Es la pregunta estratégica de la tesis y merece una respuesta honesta, no tranquilizadora.

**Dónde NO está la diferenciación, según nuestra propia evidencia:**

- **La estructura secundaria no es un diferenciador defendible hoy.** Hay **cuatro líneas de evidencia independientes que convergen en lo mismo**: Guillén 2021 se quedó en 0,70–0,73; Sánchez 2024 no aisló su aporte; la ablación de §0.2 da **+0,0088 sobre contar C/H/E en la ventana con una regresión logística** y **aporte negativo sobre ProtT5 solo** (0,680107 frente a 0,682302); y SecondaryBERT en solitario da 0,601431. §0.5.6 recomienda cerrar la línea y publicarla **como resultado negativo**, que es en sí una contribución legítima. Hacer de ella el eje diferencial sería ir contra lo que ya hemos medido. **Si se quiere rescatar, el camino no es insistir en la misma representación sino cambiarla** —estructura por residuo en vez de agregada por ventana, o estructura predicha del complejo péptido-MHC en vez de del péptido aislado— y entonces es una hipótesis nueva que hay que medir, no una continuación.
- **«Hacer clase II» tampoco diferencia por sí solo:** NetMHCIIpan existe, está maduro y usa la misma estrategia de pseudosecuencia (§0.7.1). Cubrir clase II es necesario para ser competitivos, no suficiente para destacar.

**Dónde sí está, y además encaja con lo que el grupo ya ha publicado:**

1. **Expresión × presentación.** El hallazgo central de eLife 2024 es que **la expresión pesa más que la inmunogenicidad predicha**: \*Adar era el mejor puntuado y falló por ser el menos expresado. NetMHCpan **no modela expresión en absoluto**. Un sistema que integre RNA-seq con presentación ataca el cuello de botella que el propio grupo demostró experimentalmente. §0.5.8 ya dice que la línea RNA-seq/Scipion es camino crítico, no accesorio.
2. **El post-proceso BLOSUM62 en inferencia.** Es **nuestro, publicado, y con evidencia de que funciona** (+7,6 % de precisión; y \*Wiz, el péptido con la mejor protección in vivo —100 % de ratones con tumor <100 mm³—, **solo apareció gracias a él**). Nadie más lo hace. Es la prioridad §0.5.2 y es barata: se aplica sobre los Parquet de predicciones que ya existen.
3. **Reproducibilidad y trazabilidad de extremo a extremo en Scipion.** De FASTQ a candidato priorizado, con procedencia. NetMHCpan es un predictor, no un workflow. Esto es la línea A de la tesis y es un diferenciador real para un laboratorio que necesita ejecutar, no solo puntuar.
4. **Validación experimental propia.** El grupo tiene ELISpot, ICS y modelo de ratón. Muy pocos predictores pueden cerrar el ciclo predicción → validación in vivo.
5. **Honestidad metodológica como aportación.** Los hallazgos L, N, O, Q y R de §0.6.3 describen problemas que afectan a **todo el campo**, no solo a nosotros: etiquetas de alelo inferidas por predictores (circularidad), tres objetivos mezclados en una etiqueta, fuga por publicación. Un benchmark limpio y documentado es publicable por sí mismo.

> **Resumen sin adornos:** competir con NetMHCpan en «predecir unión péptido-MHC a partir de secuencia» es competir en su terreno, con menos datos, menos tiempo de desarrollo y una representación que de momento rinde 0,68 frente a su estado del arte. **La diferenciación realista no es ser mejor en su tarea, sino resolver la tarea que ellos no abordan**: priorizar neoantígenos *reales* en un tumor *concreto*, integrando expresión, y de forma reproducible. E0 (§0.5.1) sigue siendo el primer paso obligatorio, porque sin saber reproducir 0,865 no se puede afirmar nada sobre mejoras.

### 0.7.6. Cómo construyó Wert2021 los negativos (leído del código, 24 nov 2026)

Fuente: `reference/neoantigenpred_zip/neoantigenpred-master/media/scripts/peptides_extraction.py`. **Esto es el código real, no el resumen del paper.** Es material imprescindible para E0.

**El algoritmo, paso a paso:**

1. Del CSV de IEDB se queda con `Assay.4 != "Negative"`, deduplica por péptido y separa las filas con accession de proteína madre de las que no la tienen.
2. Para cada proteína madre única, **descarga el FASTA de UniProt** (`https://www.uniprot.org/uniprot/<acc>.fasta`).
3. Mantiene una copia de trabajo `s2 = fasta` y, para cada epítopo de esa proteína:
   - Lo **localiza por Smith-Waterman** sobre el FASTA completo (`match_score=3`, `gap_cost=2`, desemparejamiento −3) → `pos1, pos2`.
   - Calcula el centro `ctr = round(mean(pos1, pos2))` y **el positivo es `fasta[ctr − w/2 : ctr + w/2]`**, una ventana de `w` aa **centrada en el epítopo**.
   - Lo localiza también sobre `s2` y **lo extirpa**: `s2 = s2[:p1] + s2[p2+1:]`.
4. Cuando ya ha quitado todos los epítopos conocidos, **parte el resto de la proteína en trozos consecutivos y NO solapantes de `w` aa** (`textwrap.wrap(s2, w)`) y **todos esos trozos son los negativos**. El último se descarta.
5. Los epítopos sin accession y de longitud ≥ `w` entran como positivos con sus primeros `w` residuos.
6. Al final, `drop_duplicates(subset='peptides')` global.

**En una frase: los negativos son la proteína fuente con sus epítopos conocidos recortados, troceada en ventanas consecutivas sin solape.**

> ⚠️ **Corrección a lo que este documento decía antes.** En el hallazgo I y en el docstring de `build_iedb_dataset_v2.py` escribí que «Wert2021 construía negativos **explícitos**». **Es engañoso y lo corrijo:** sus negativos **no son medidas experimentales negativas**, son **señuelos** —el resto de la proteína, asumido no epitópico—. Es decir, **Wert2021 es también positive-unlabeled**, exactamente igual que nosotros (§4.3). La diferencia no es que él tuviera negativos reales; es **cómo construyó los señuelos**.

**Por qué sus señuelos son mejores que nuestras ventanas sin anotación:**

| | Wert2021 | Pipeline actual |
|---|---|---|
| Origen del negativo | la **misma proteína** que el positivo | cualquier ventana sin anotación |
| Solapamiento | **ninguno**: trozos consecutivos | ventanas deslizantes solapadas |
| Composición de aminoácidos | emparejada por construcción | no controlada |
| Prevalencia resultante | **2,67 %, emergente** de la longitud de la proteína | 25,45 %, consecuencia del criterio de contención |
| Epítopos conocidos en el negativo | **extirpados** antes de trocear | pueden colarse |

El punto clave es el primero: usar la misma proteína convierte el fondo en **difícil y emparejado**, de modo que el modelo no puede acertar por composición global ni por «esta proteína es de las que tienen epítopos». Y el segundo explica por qué su prevalencia es natural: no eligió el 2,67 %, le salió.

**Defectos del código que hay que conocer antes de usarlo como referencia en E0:**

- **No corre tal cual en un entorno moderno.** Usa `np.int` (eliminado en NumPy 1.24), `DataFrame.append` (eliminado en pandas 2.0) y `keras.preprocessing.text.Tokenizer`. **E0 exige portarlo**, no solo ejecutarlo.
- **Los epítopos cerca del extremo N producen un positivo que es la cadena vacía.** Si `ctr < w/2`, el índice inicial se vuelve negativo y Python devuelve `''`. Verificado: con `w=12` y `ctr=4`, la ventana sale de longitud 0. Y el guardia `type(...) == str` **siempre es verdadero**, así que no lo filtra: **entran positivos vacíos al dataset.**
- **Cerca del extremo C los positivos salen truncados** (longitud 9 o 7 en lugar de 12), por el mismo motivo y sin aviso.
- **Off-by-one al extirpar:** `s2[:p1] + s2[p2+1:]` elimina un residuo de más.
- **Se salta la primera proteína a propósito** (`if index == 0: continue`, comentado como «la primera línea es continuación de la cabecera»).
- **La deduplicación final es dependiente del orden**: si una misma ventana aparece como positiva en una proteína y como negativa en otra, **gana la que se procesó primero**. Es el mismo problema de etiquetas contradictorias que §11.1 midió en nuestros datos (93,53 %), aquí resuelto en silencio por orden de ficheros.
- Smith-Waterman **tolera desemparejamientos**, así que un epítopo que no esté literalmente en la proteína se coloca igualmente en algún sitio, y el positivo sale mal centrado.
- Todos los negativos de una proteína heredan el `Reference.1` del **último** epítopo, por una variable de bucle que se escapa.

**El balanceo no está aquí, está en el entrenamiento.** `LSTMcvonehot.py` usa un generador con parámetro `fracPos`: submuestrea negativos hasta la fracción de positivos deseada **y genera positivos sintéticos con `BLOSUMSIM`** sobre un positivo elegido al azar en cada lote. Eso es la «prevalencia virtual» que según el paper subió AUC y F1 un 20 %, más que la profundidad de la red. **Nunca escribió las variantes a disco**, lo que confirma §0.4.4.

**Consecuencia para la prioridad §0.5.4** («pasar de ventana a péptido, negativos como señuelos del mismo proteoma»): esa prioridad es, en esencia, **adoptar el método de negativos de Wert**, corrigiendo sus defectos: controlar los extremos de la proteína, no permitir ventanas vacías ni truncadas, resolver las contradicciones de etiqueta de forma explícita en lugar de por orden, y emparejar por longitud además de por proteína.

---

## 0.8. Revisión del MLP en ejecución (24 nov 2026, 15:30 UTC)

Al revisar qué corría en el servidor apareció un **entrenamiento que lleva 6 días y 6 horas** y que nadie había documentado aquí. Esta sección es el diagnóstico.

**Qué es.** PID 3348177, GPU 1. Lanzado el **17 nov a las 22:25**.

```text
neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py
  --root data/data_input_nn_shuffled_concatenate
  --scaler-path neural_network/MLP/standardizer_all_train_chunks.npz
  --features primary_secondary --epochs 10 --max-chunks 14499
  --eval-target-per-class 29006 --learning-rate 0.001 --seed 42
  --resume .../recovery_mlp_primary_secondary.pt
```

Salida en `results/mlp_shuffled_concatenated_14499chunks_10epochs_20261117_222538/`.

**Dónde va.** **Epoch 2 de 10**, chunk 11.690/14.499 (80,6 % de la época). Ritmo actual ~15 s/chunk, es decir **~60 h por época**; la época 1 tardó 307.480 s (85,4 h) porque incluyó la construcción de los conjuntos de evaluación.

| | |
|---|---:|
| Transcurrido | 6,24 días |
| Épocas completadas | **1 de 10** |
| Para terminar la época 2 | ~11,7 h |
| Épocas 3–10 | ~483 h (20,1 d) |
| **Total restante** | **~20,6 días** (terminaría ~15 dic) |

**Resultado de la época 1** (único `epoch_end` registrado, el 21 nov a las 23:08):

| | TRAIN | TEST |
|---|---:|---:|
| loss | 0,546633 | 0,542468 |
| accuracy | 0,707819 | 0,713352 |
| **ROC-AUC** | 0,790274 | **0,795539** |
| MCC | 0,416067 | 0,427092 |
| n | 58.012 | 58.012 |

### Cinco problemas, en orden de gravedad

1. **El 0,7955 es exactamente el número que §0.1 declara contaminado.** La tabla de §0.1 dice: «ROC-AUC histórico 0,7955 → Fuga: 99,70 % de los grupos en varias particiones, 87,38 % en las tres». **Esta ejecución está reproduciendo el artefacto de fuga, no midiendo generalización.** Verificado en el código: `meta['split_id'] == split` selecciona **por fila** dentro de cada chunk (líneas 477, 495, 520, 674, 725); `group_id` se usa **únicamente como clave para cargar el embedding secundario** (línea 573), **no para definir la partición**. Es la política histórica de §10.1, la que §11.3 decidió sustituir.

2. **Selecciona el mejor modelo por la pérdida de TEST.** El log lo dice: `BEST by TEST STAGE loss`, y el código registra `"selection_metric": "stage_fixed_50_50_test_loss"`. **No hay VALIDATION.** Esto viola directamente §13.9 («seleccionar mediante VALIDATION, sin consultar TEST») y §19 («conservar el TEST congelado»): el TEST deja de ser una estimación independiente. El script **tiene** una rama que selecciona por VALIDATION, pero depende de `getattr(args, "v2_checkpoint_contract", None)` (línea 1116) y **ese argumento no existe en el parser**, así que siempre vale `None`: **es código muerto y la rama correcta es inalcanzable.**

3. **TRAIN y evaluación están ambos forzados a 50/50.** El log: `Batch size / GPU: 8,192 (exact 50/50 TRAIN)` y `TRAIN/TEST eval per epoch: fixed STAGE and ALL 50/50 samples`. Con `--eval-target-per-class 29006` → n = 58.012 exactos. **La prevalencia real de D1 es 25,45 %**, así que este ROC-AUC **no es comparable** ni con el 0,654/0,680 honesto de §0.2 ni con el 0,865 de Wert2021 (prevalencia 2,64 %). §10.3 exige conservar la prevalencia natural en evaluación.

4. **No calcula AP ni PR-AUC.** El script solo importa `roc_auc_score` (línea 30, usado en 297); **no hay `average_precision_score` en ninguna parte**. §0.2 reporta todo en AP y lift sobre prevalencia, y §10.3 dice que la PR-AUC es la métrica informativa con clase positiva minoritaria. **Esta ejecución no puede producir la métrica que el proyecto usa para comparar.**

5. **Entrena sobre los datos aumentados.** 2.019.082.240 filas de TRAIN por época frente a 15,1 M de originales D1: expansión de ~134×, coherente con ventanas más aumento BLOSUM62 materializado. §0.5.5 dice **no ejecutar D2** y §0.4.4 explica por qué el aumento a disco no añade información (variantes a coseno 0,9883, más cerca entre sí que la distancia que separa etiquetas opuestas reales).

> **Diagnóstico.** No es que la ejecución vaya mal: va exactamente como se diseñó. El problema es que **el diseño es el que §0.1, §0.5 y §11.3 ya declararon superado**, y produce un número que este mismo documento prohíbe citar. Gastar 20,6 días más de GPU 1 daría, en el mejor caso, diez épocas de un ROC-AUC con fuga, balanceado al 50/50, sin AP y con el modelo elegido mirando el TEST.

**Recomendación: detenerla.** Los números honestos que la sustituyen **ya existen** (§0.2: 0,654641 LR y 0,680107 MLP con partición primaria exacta, y 0,662294/0,674668 con partición por componentes de proteína, todos con AP y prevalencia declaradas). Antes de volver a entrenar hay que arreglar cuatro cosas en el script: partición por grupo o por componentes en lugar de por fila, un VALIDATION real para seleccionar (añadiendo el argumento que falta), evaluación a prevalencia natural, y `average_precision_score`.

### 0.8.1. Decisión y parada programada

**Decisión de Laura, 24 nov 15:33 UTC: dejar que termine la época 2 y parar entonces.** Criterio razonable: da un **segundo punto de la curva de aprendizaje con el mismo protocolo**, lo que permite documentar que el 0,7955 no mejora con más épocas —y por tanto que el techo no es de entrenamiento insuficiente— antes de cerrar la línea histórica. Cuesta ~11,7 h en lugar de 20,6 días.

**Parada automatizada, independiente de la sesión de Claude.** Proceso vigilante lanzado con `setsid` (PID 2651898), log en `logs/mlp_stop_after_epoch2.log`. Lógica:

1. Sondea cada 120 s el fichero `history_mlp_primary_secondary.jsonl` contando líneas `"type": "epoch_end"`. Al llegar a **2**, la época 2 está cerrada.
2. **Espera 300 s de gracia** para que el script termine de escribir `best_`, `last_` e `history_` (en la época 1 se escribieron en el mismo minuto que el `epoch_end`).
3. Registra el listado de los `.pt` y envía **`SIGTERM`**, no `SIGKILL`.
4. Si tras 60 s sigue vivo, **lo deja estar y lo anota**: no escala a `KILL`, requiere revisión humana.
5. Si el proceso hubiera terminado por su cuenta antes, no hace nada.

Usa el **PID directo (3348177)**, no un patrón de `pgrep`, para evitar el fallo de auto-coincidencia que ya invalidó dos monitores en esta sesión (el patrón aparecía en la propia línea de comandos del vigilante).

**Qué hacer después de la parada:**

1. Comparar los `epoch_end` 1 y 2 y **anotar aquí si el 0,7955 se movió**. Es el único resultado que esta ejecución aporta.
2. **No citar sus métricas como generalización** en ningún caso (§0.1).
3. Antes de volver a entrenar, **arreglar las cuatro cosas del script** (§0.8): partición por grupo o componentes en lugar de por fila; VALIDATION real para seleccionar, añadiendo el argumento `--v2-checkpoint-contract` que falta en el parser y que deja inalcanzable la rama correcta; evaluación a prevalencia natural en lugar de 50/50 forzado; y `average_precision_score`.
4. Liberada GPU 1, queda disponible para la primera prueba con `pseudosequence` (§0.5.3), que es la que sí puede dar un resultado nuevo.

---

## 1. Contexto doctoral y finalidad científica

El trabajo se desarrolla en el Centro Nacional de Biotecnología (CNB-CSIC), dentro del proyecto RISE (PREX2023-000056), mediante contrato predoctoral FPI iniciado el 1 de enero de 2026. El doctorado pertenece al programa de Biociencias Moleculares de la Universidad Autónoma de Madrid, con matrícula del 17 de febrero de 2026. Título de tesis: «Desarrollo de algoritmos para el diseño de inmunoterapias en oncología (RISE)». Dirección: Esteban Veiga; Carlos Óscar S. Sorzano participa en la supervisión computacional. Tutora UAM: Blanca Lizarbe. Horizonte previsto: marzo de 2029.

NAP-CNB es el modelo de predicción de epítopos; la adquisición, transformación y representación de los datos son componentes que alimentan ese modelo, no sinónimos del mismo. El objetivo amplio es contribuir a la identificación y priorización de candidatos inmunogénicos, especialmente en oncología, mediante métodos reproducibles y eventualmente integrados en workflows de Scipion.

### Líneas de tesis

- A. Integración en Scipion y reproducibilidad de workflows bioinformáticos.
- B. Desarrollo y evaluación de una versión mejorada de NAP-CNB basada en deep learning.
- C. Comparación e integración de predictores externos de epítopos.
- D. Validación experimental de candidatos y predicciones.
- E. Estudio de mutaciones somáticas, escape de presentación por MHC-I y estrategias alternativas, incluyendo CAR-T.

Estas líneas están relacionadas, pero no todas se encuentran en el mismo grado de madurez. La validación experimental y las aplicaciones de escape inmunitario no deben presentarse como resultados ya obtenidos.

## 2. Fundamento inmunológico y definición del problema

Los linfocitos T reconocen complejos péptido-MHC mediante el TCR. MHC-I presenta principalmente péptidos intracelulares a linfocitos CD8+, mientras que MHC-II se asocia principalmente a presentación a CD4+. En humanos las moléculas se denominan HLA; en ratón, H-2. Los péptidos de clase I suelen tener 8–11 residuos y los de clase II suelen ser más largos, con un núcleo de unión de aproximadamente nueve residuos. Estas longitudes son contexto biológico, no filtros confirmados del dataset.

Las mutaciones somáticas pueden originar secuencias peptídicas ausentes del proteoma normal y potenciales neoantígenos. Sin embargo, la presencia de una mutación no garantiza procesamiento, presentación, unión al MHC ni reconocimiento inmunitario. El objetivo supervisado actual es la presencia de un epítopo anotado dentro de una ventana proteica, no una medición directa de afinidad, presentación o inmunogenicidad clínica. Esta distinción es fundamental para interpretar las métricas y comparar predictores.

## 3. Fuentes y organización de datos

Se ha desarrollado la recuperación automatizada de epítopos de IEDB y su organización por especie, clase y familia de MHC, junto con el procesamiento de secuencias proteicas de origen. UniRef50 se utiliza en el trabajo de preentrenamiento de representaciones de estructura secundaria. COSMIC constituye una línea complementaria para mutaciones recurrentes asociadas a cáncer.

No consta en el contexto recuperado la release exacta de IEDB, los filtros de ensayo, los criterios de evidencia, el método completo de recuperación de proteínas, ni la versión de COSMIC. Deben recuperarse de scripts y manifiestos antes de publicar el método.

### 3.1. Once conjuntos MHC

| Especie | Clase | Familia | Filas BLOSUM históricas aproximadas |
|---|---|---|---:|
| Humano | I | HLA-A | 266 M |
| Humano | I | HLA-B | 277 M |
| Humano | I | HLA-C | 203 M |
| Humano | II | HLA-DR | 62 M |
| Humano | II | HLA-DQ | 64 M |
| Humano | II | HLA-DP | 55 M |
| Ratón | I | H2-K | 77 M |
| Ratón | I | H2-D | 67 M |
| Ratón | I | H2-L | 69 M |
| Ratón | II | H2-IA | 77 M |
| Ratón | II | H2-IE | 63 M |

Total aproximado: 1.280 millones de filas aumentadas, según cifras redondeadas de una versión histórica. Las familias no equivalen a alelos individuales; no está confirmado que el modelo reciba el alelo como feature.

## 4. Construcción de ejemplos supervisados

### 4.1. Ventanas deslizantes

La unidad de entrada actual es una ventana de longitud fija de 25 aminoácidos, con posición central 13 en numeración de base uno. Se recorre la secuencia proteica y se generan ventanas asociadas a anotaciones de epítopos. Una ventana se etiqueta como positiva cuando contiene íntegramente un epítopo seleccionado; una intersección parcial no basta bajo esta definición.

Formalmente, para una ventana W=[s,s+24] y un epítopo E=[a,b], usando coordenadas inclusivas, la condición de contención es s ≤ a y b ≤ s+24. Esta formulación explica la regla, pero no certifica el convenio de coordenadas usado por el código.

La posición relativa del epítopo se refiere a su ubicación dentro de la ventana de 25 aa, no a su coordenada absoluta en la proteína. El campo `epitope_pos_score` recoge información posicional; su fórmula exacta, rango y tratamiento de múltiples epítopos deben verificarse. También queda por documentar el tratamiento de extremos de proteínas, padding, stride, secuencias ambiguas y epítopos de más de 25 aa.

### 4.2. Esquema de datos conocido

| Campo | Función |
|---|---|
| `blosum_seq` | Secuencia de entrada tras aumento, o secuencia original según fila |
| `contains_epitope` | Etiqueta binaria histórica |
| `selected_epitope` | Epítopo seleccionado asociado a la observación |
| `epitope_pos_score` | Información posicional relativa dentro de la ventana |
| `group_id` | Identificador de grupo para vincular observaciones y representaciones |
| `protein_group_id` | Identificador relacionado con la proteína de origen |

El significado exacto y ámbito de unicidad de cada identificador deben comprobarse antes de concatenar datasets. `group_id` y `protein_group_id` no son intercambiables. Una misma secuencia puede aparecer en varias proteínas, posiciones o familias MHC y recibir anotaciones diferentes.

### 4.3. Positivos y negativos

La ausencia de anotación positiva no demuestra ausencia de capacidad inmunogénica. Es preferible distinguir positivos conocidos de ejemplos no etiquetados (`unlabeled`), aunque operativamente se utilicen estos últimos como clase negativa para el entrenamiento binario. Se trata de una aproximación positive-unlabeled con potencial ruido de etiqueta, no de negativos experimentalmente confirmados.

## 5. Aumento de datos con BLOSUM62

La estrategia histórica genera el original y 25 variantes por observación, utilizando sustituciones basadas en BLOSUM62. BLOSUM62 expresa preferencias evolutivas de sustitución; no garantiza que una variante conserve unión a MHC o reconocimiento por TCR. La etiqueta heredada de una variante es una hipótesis de aumento, no una nueva anotación experimental.

La política de selección de posiciones, distribución de sustituciones, protección del núcleo epitópico, semilla y tratamiento de variantes idénticas debe recuperarse del código. No se debe asumir que todas las sustituciones son conservadoras ni que las 25 variantes son únicas.

### Riesgos metodológicos

- Fuga entre TRAIN y VALIDATION/TEST si se separan variantes de un mismo original después del aumento.
- Fuga por ventanas solapadas, secuencias idénticas o proteínas homólogas.
- Ruido por alteración de residuos esenciales del epítopo.
- Inflación de tamaño efectivo: 26 filas relacionadas no equivalen a 26 observaciones independientes.
- Duplicados dentro de un grupo o entre grupos y familias.

La estrategia reciente es restringir el aumento a TRAIN y mantener VALIDATION/TEST con secuencias originales intactas. Esta decisión permite medir mejor la generalización sobre observaciones naturales.

> **Superado por §0.4 y §0.5.** La recomendación vigente es no materializar aumento BLOSUM62 en absoluto. El método publicado lo aplicaba **on-batch** durante el entrenamiento y, sobre todo, como **post-proceso en inferencia** (+7,6 % de precisión), no como filas escritas a disco.

## 6. Representación de secuencia primaria: ProtT5

Modelo empleado: `Rostlab/prot_t5_xl_half_uniref50-enc`. Se utiliza el encoder para generar representaciones contextualizadas de aminoácidos, agregadas mediante mean pooling a un vector de 1024 dimensiones por ventana. Deben excluirse del pooling los tokens especiales y padding según la implementación efectiva.

La entrada histórica es `blosum_seq`; se conservan etiqueta, posición e identificadores. Los archivos NumPy por chunk permiten trabajar sin cargar el dataset completo en memoria.

Ejemplo histórico HLA-A: 2.661 chunks y aproximadamente 266,1 millones de filas, con arrays X de dimensión `(N,1024)`. Se comunicó una comprobación de diez chunks con 1.000.000 de filas y 73.944 positivas (7,3944 % en esa muestra, no prevalencia global).

El modelo descargado ocupaba aproximadamente 2,42 GB. En abril se observó un problema de compatibilidad CUDA/driver que provocó ejecución en CPU. Se evolucionó hacia ejecución paralela por GPU mediante procesos independientes, patrones de entrada no solapados y `CUDA_VISIBLE_DEVICES`.

## 7. Representación de estructura secundaria

### 7.1. Antecedentes

El sistema de referencia utilizaba ProteinUnet para predicción de estructura secundaria sobre ventanas de 30 aa. Se manejaban salidas Q8, Q3 y regresión; la representación conservada era Q3: H (hélice), E (lámina beta), C (coil). Se excluían secuencias con letras desconocidas. Los BERT históricos de primaria y secundaria tenían hidden size 768, 12 capas, 12 cabezas y vocabularios de 30 y 8 tokens, respectivamente. Se describieron `max_position_embeddings=30`, probabilidad de máscara 0,15, máximo cinco máscaras, batch 32 y entrenamientos de 14 M/500 k pasos; estas cifras corresponden al antecedente, no necesariamente al nuevo modelo. La extracción histórica usaba [CLS] de la última capa.

La transición a ventanas de 25 aa requirió revisar compatibilidad de tokenización, longitud y posiciones. No debe suponerse que el padding a 30 o el reentrenamiento se aplicaron exactamente como se propusieron sin comprobar configuración.

### 7.2. Nuevo SecondaryBERT

Se trabajó en predicción de estructura secundaria de UniRef50 y entrenamiento MLM de un BERT especializado. El corpus se divide en chunks FASTA independientes. Se realizaron ejecuciones paralelas en CPU y pruebas de preentrenamiento; una ejecución inicial alcanzó aproximadamente 500.000 pasos sin finalizar. Se revisaron workers y paralelismo.

En septiembre se comunicó la finalización de la generación multi-GPU de embeddings secundarios para los once datasets, con 55.763.575 filas y vectores `(N,768)`. En mayo se manejaban representaciones por grupo `(N,25,768)` susceptibles de mean pooling; la salida posterior ya era de 768 dimensiones. El checkpoint nuevo se situaba en `/home/nap/lperez_nn/model/secondary_bert`.

La unión primaria-secundaria histórica se hacía por `group_id`, no por orden implícito de filas. En HLA-A se comunicaron 10.214.658 grupos en una versión de mayo. Si una variante BLOSUM reutiliza el embedding secundario de su padre, la representación secundaria no refleja necesariamente el efecto estructural de la sustitución; esta política debe verificarse por versión y documentarse como limitación.

### 7.3. Incidencia del checker

Un patrón `*_group_id.npy` capturaba también `*_protein_group_id.npy`, duplicando el recuento. Se identificó como falso fallo del checker y se corrigió el patrón. Se comunicaron comprobaciones de shapes, IDs y variabilidad; el resultado esperado era 11/11 PASS, 0/11 FAIL y 55.763.575 filas. Los embeddings antiguos no se conservaron según el historial comunicado.

## 8. Fusión de features y escalado

La configuración principal combina 1024 dimensiones de ProtT5 y 768 de SecondaryBERT: 1792 features por observación. La posición relativa se ha considerado como feature adicional en experimentos de ablación, dando 1793 dimensiones cuando se incluye. No debe confundirse con la configuración principal de 1792.

Combinaciones propuestas: primaria, secundaria, posición, primaria+secundaria, primaria+posición, secundaria+posición y las tres juntas. Las siete combinaciones permiten estimar el valor incremental de cada modalidad con splits idénticos.

Se utiliza StandardScaler ajustado exclusivamente sobre TRAIN. Para datasets masivos puede calcularse incrementalmente mediante `partial_fit`, conservando medias, varianzas y número de observaciones. VALIDATION y TEST deben transformarse con el scaler congelado. Se comunicó un cálculo histórico sobre 14.503 chunks y aproximadamente 1,16×10^9 filas TRAIN. Esta cifra y el total BLOSUM redondeado no deben reconciliarse sin los manifiestos de sus respectivas versiones.

En noviembre se realizó shuffling, recálculo del scaler y concatenación de representaciones primaria y secundaria para mejorar la eficiencia del entrenamiento. Cualquier reconstrucción del split o de las etiquetas requiere revisar la validez del scaler anterior y recalcularlo si cambia TRAIN.

## 9. Infraestructura y organización del código

### 9.1. Repositorios

- `https://github.com/LauraPerezLiens/lperez_nn/tree/main`: repositorio principal comunicado en noviembre.
- `NAP-CNB`: nombre del modelo y también de componentes/repositorios históricos.
- `NAP-CNB-ML`: repositorio/documentación histórica de entrenamiento.
- `MHC-Epitope-Prediction`: repositorio comunicado el 17 de noviembre.
- `https://github.com/scipion-chem/scipion-chem/pull/237/changes`: PR relacionado con trabajo de Scipion-Chem.

No se ha comprobado la relación exacta entre ramas, repositorios, visibilidad y commits actuales.

### 9.2. Rutas históricas

```text
/home/nap/lperez_nn/
├── NAP-CNB/scripts/
│   ├── data_download/
│   ├── data_classification/
│   ├── data_augmentation/
│   ├── embeddings/
│   ├── NN/
│   ├── secondaryBERT/
│   ├── secondary_structure_prediction/
│   └── BERT/                     # organización histórica
├── data/data_intermediate/
├── data/data_uniref50/secondary_structure_prediction/
└── model/secondary_bert/

/data/nap/lperez_nn/data/data_input_nn/
└── {human,mouse}/{mhc-I,mhc-II}/{familia}/
```

Ejemplo de directorios: `classification_human_mhc-I_HLA-A_blosum_ProtT5_chunks` y `classification_human_mhc-I_HLA-A_SecondaryBERT_by_group`.

Scripts históricos: `prott5_embeddings.py`, `NAP-CNB/scripts/NN/validate_primary_secondary_alignment.py`, `NAP-CNB/scripts/BERT/train_secondary_mlm.py`, `NAP-CNB/scripts/BERT/secondary_structure_uniref.py`, `NAP-CNB/scripts/embeddings/secondary_structure/check_secondary_embeddings.py`, `run_missing_cpu.sh`.

Archivos por chunk: `*_ProtT5_X.npy`, `*_y.npy`, `*_pos.npy`, `*_group_id.npy`, `*_protein_group_id.npy` cuando disponible. Verificar prefijos y formato exacto por versión.

### 9.3. Recursos computacionales

Servidor Pascal: cuatro RTX 3090 de 24 GB, aproximadamente 376 GiB de RAM y 26 TB en `/data`. También se trabajó en Cori. En abril se comunicó una máquina de 80 CPU y ~385 GB RAM. Entorno histórico `protein_pipeline`; en etapas iniciales se manejaban entornos BERT y ProteinUnet separados, con propuesta de integración en Python 3.10 y TensorFlow 2.12.

La generación de embeddings y el entrenamiento requieren procesamiento por chunks, control de memoria, logs separados, reanudación y asignación explícita de GPU. El almacenamiento es una restricción importante: 1.280 millones de vectores de 1792 dimensiones ocuparían aproximadamente 9,18 TB decimales solo en float32, o 4,59 TB en float16, sin contar metadatos ni copias. Es una estimación teórica, no ocupación medida.

Incidencias históricas: argumentos CLI ausentes en una versión de ProtT5, CSV HLA-A hardcodeado, batch 32, rutas incorrectas, typo HLAR/HLA-DR, eliminación incompleta de chunks por comandos partidos y mensajes `Skipping chunk ... output already exists`. La existencia de un archivo no garantiza que sea íntegro ni compatible con la versión actual.

## 10. Entrenamiento y evaluación histórica

### 10.1. Split inicial

Se utilizó 80/10/10 por filas y chunks para TRAIN/VALIDATION/TEST. Se permitía que grupos o proteínas aparecieran en distintas particiones. Esta política histórica es vulnerable a leakage por ventanas solapadas, variantes y secuencias repetidas; no constituye una evaluación independiente por proteína.

Se reconstruyó un `master_index` para H2-D (94/95 según el registro histórico, significado exacto del denominador por confirmar), se utilizó `check_master_split` y se comunicó una evaluación global de 58.012 filas. No se dispone aquí del manifiesto completo de esas pruebas.

### 10.2. Modelos

Baseline de regresión logística (LR) y MLP. Arquitectura MLP principal: `1792 → 512 → 128 → 1`, dropout 0,30, AdamW con learning rate 0,001 y batch size 8192. En documentación histórica aparece LayerNorm y entrenamiento acumulativo por chunks. Se propone salida logit y BCEWithLogitsLoss; confirmar activaciones, normalización y scheduler del commit concreto.

Se comunicó ROC-AUC de test aproximadamente 0,99999 en una prueba de diez chunks. **Queda descartado: es un artefacto de partición por fila (véase §0.1) y no debe volver a citarse.** En noviembre se observaron pruebas de 10, 50 y 100 chunks con sobreajuste; con 10 chunks se detectaba alrededor de epoch 5 y con 50 alrededor de epoch 15. No consta un resultado final concluyente para 100 chunks.

### 10.3. Desbalanceo y experimentos

Estrategias planteadas: `none`, `balanced`, `focal`, `undersampling`. La focal loss incorpora parámetros alpha y gamma configurables. La ponderación de clases y el undersampling deben derivarse únicamente de TRAIN. La evaluación debe conservar la prevalencia natural del conjunto de referencia. Históricamente se planteó seleccionar por validation log-loss y usar threshold 0,5; si se optimiza un umbral, debe hacerse en VALIDATION y congelarse antes de TEST.

Métricas recomendadas para el protocolo definitivo: ROC-AUC, PR-AUC/AP, log-loss, sensibilidad, especificidad, precisión, F1, MCC, matriz de confusión, calibración y prevalencia. Reportar por familia, especie y clase, además de agregados micro/macro. La PR-AUC es especialmente informativa cuando la clase positiva es minoritaria. Estas son recomendaciones metodológicas, no resultados ya calculados.

## 11. Auditoría de etiquetas y cambio de diseño (noviembre)

### 11.1. Hallazgos comunicados el 18 de noviembre

| Magnitud | Valor |
|---|---:|
| Filas originales auditadas | 55.763.575 |
| Secuencias únicas | 15.135.904 |
| Secuencias con ambas etiquetas históricas | 3.494.284 |
| Filas asociadas a secuencias con ambas etiquetas | 21.877.306 |
| Secuencias globalmente positivas | 3.717.641 |
| Secuencias unlabeled | 11.418.263 |
| Filas globalmente positivas | 22.514.914 |
| Filas unlabeled | 33.248.661 |
| Filas cuyo label cambia | 12.659.367 (22,70 %) |
| Candidatas de coincidencia exacta en misma proteína | 596.063 filas / 167.502 secuencias |

Las sumas de positivos y unlabeled coinciden con los totales de filas y secuencias comunicados. Aproximadamente 23,09 % de las secuencias únicas presentaban etiquetas contradictorias y 39,23 % de las filas pertenecían a ese conjunto. La etiqueta global positiva alcanza aproximadamente 24,56 % de secuencias únicas y 40,38 % de filas. Estas proporciones se calculan a partir de los recuentos anteriores.

### 11.2. Interpretación

Una misma ventana puede aparecer como positiva en un contexto y como no positiva en otro. Si el modelo recibe únicamente la secuencia y su representación estructural, ejemplos con features idénticas y etiquetas opuestas introducen contradicciones que no puede resolver determinísticamente. Parte de esa heterogeneidad puede ser biológicamente legítima: especificidad de MHC, proteína de origen o evidencia experimental diferente. Por ello, una etiqueta global positiva por secuencia modifica la pregunta científica hacia «existe evidencia positiva en algún contexto», y no demuestra positividad en todas las familias MHC.

La auditoría de coincidencias en la misma proteína permite investigar errores de anotación o propagación, pero el recuento de candidatas no equivale a correcciones verificadas. Es necesario conservar procedencia, etiqueta original y etiqueta global para permitir trazabilidad y análisis de sensibilidad.

### 11.3. Decisiones comunicadas

- Eliminar duplicados con misma secuencia, embeddings y etiqueta global.
- Reconstruir splits por `group_id`.
- Tratar operativamente unlabeled como negativos.
- Entrenar un modelo conjunto y realizar reentrenamientos por especie, clase y familia.
- Evitar que el aumento BLOSUM afecte a VALIDATION/TEST.

El split por `group_id` es una mejora, pero por sí solo no garantiza independencia por proteína, secuencia o homología. Deben comprobarse explícitamente intersecciones de secuencias entre particiones y, para evaluar generalización a proteínas nuevas, considerar particiones por proteína o clúster de homología. La elección de agrupación debe responder a la pregunta científica, no únicamente maximizar métricas.

## 12. Estado reciente: D1, D2 y E3/E4

Último estado disponible en la conversación del 23 de noviembre, referido al commit `1c1a419` (sin verificación directa en GitHub). D1 corresponde al catálogo de originales utilizado como base certificada; D2 se refiere al diseño con aumento BLOSUM62 exclusivamente en TRAIN. La nomenclatura exacta de E1/E2 y la diferencia experimental específica entre E3 y E4 no se han recuperado con suficiente evidencia y no se inventan aquí.

### Evidencia comunicada

- Matriz BLOSUM62 de 24×24 verificada, con SHA-256 registrado.
- Censo del alfabeto D1: 377.514.800 posiciones, todas canónicas; coincide con 15.100.592 ventanas × 25 residuos.
- Catálogo SQLite persistente de 15.100.592 originales con split certificado, aproximadamente 2,1 GB; doce pruebas e `integrity_check ok`.
- Piloto de recuperación histórica en H2-L: 89.179 variantes de 3.569 observaciones TRAIN; 46 filas retiradas por fuga a VALIDATION/TEST y 550 duplicadas. El orden de estos recuentos respecto a filtros debe verificarse en el log.
- E3/E4 figuran como `not_executed` en `experiment_status.json`.
- Bloqueo: ninguno de los 3.569 padres comparados coincidía bit a bit entre las representaciones comparadas en el piloto. El fragmento recuperado no identifica íntegramente los dos artefactos ni la magnitud de la diferencia.

La diferencia entre 15.135.904 secuencias únicas de la auditoría y 15.100.592 originales D1 es de 35.312. No se atribuye a un filtro concreto sin el manifiesto correspondiente.

> **Superado por §0.1.** El bloqueo se resolvió: las auditorías de embeddings salieron limpias y la hipótesis de corrupción quedó descartada. El apartado siguiente se conserva como registro del razonamiento del 23 de noviembre de 2026.

### Diagnóstico recomendado del bloqueo

Comprobar primero identidad de secuencia, grupo, orden de features, checkpoint, tokenización, pooling, dtype, scaler, versión de librerías y procedencia de archivos. Comparar arrays antes de normalización con métricas de diferencia absoluta, relativa y similitud coseno, además de igualdad exacta. Una discrepancia bit a bit puede deberse a precisión numérica o a un cambio sustantivo de pipeline; no permite concluir por sí sola cuál es la causa. No reutilizar embeddings históricos de variantes como si fueran compatibles hasta resolver esta cuestión.

Si no puede garantizarse compatibilidad, regenerar originales y variantes de TRAIN bajo una única configuración reproducible es una opción metodológica, con coste computacional considerable. Mantener D1 como referencia inmutable y registrar hashes, manifiestos, seeds, versiones y conteos de D2. No declarar E3/E4 ejecutados hasta disponer de logs y resultados completos.

## 13. Protocolo experimental propuesto para consolidación

1. Congelar originales, esquema, procedencia y política de etiquetas.
2. Definir la unidad de independencia del split y certificar ausencia de intersecciones prohibidas.
3. Crear catálogo de TRAIN, VALIDATION y TEST con hashes y conteos por familia.
4. Resolver compatibilidad de embeddings y generar variantes únicamente de TRAIN.
5. Filtrar variantes duplicadas y coincidencias exactas con VALIDATION/TEST.
6. Construir representaciones con checkpoint y pooling consistentes; verificar alineamiento por IDs.
7. Ajustar scaler exclusivamente en TRAIN de cada configuración pertinente.
8. Entrenar LR y MLP con controles de desbalanceo y ablaciones; registrar seeds y presupuesto computacional.
9. Seleccionar modelos mediante VALIDATION, sin consultar TEST para ajustar hiperparámetros.
10. Evaluar TEST original congelado, incluyendo análisis estratificado y calibración.
11. Comparar con predictores externos bajo una tarea y unidades de evaluación compatibles.
12. Documentar limitaciones y seleccionar candidatos para validación experimental.

Este protocolo es una propuesta de consolidación, no una afirmación de que todos los pasos se hayan ejecutado.

## 14. Comparación con predictores externos

Herramientas consideradas: NetMHCpan, MHCflurry, NetMHCIIpan y pVACtools. NetMHCpan y MHCflurry se relacionan principalmente con MHC-I; NetMHCIIpan con MHC-II; pVACtools es un conjunto de workflows para priorización de neoantígenos, no un único modelo equivalente a NAP-CNB.

Para una comparación justa, definir cómo se transforma una ventana de 25 aa en péptidos candidatos, qué longitudes se evalúan, qué alelos se consideran y cómo se agregan los scores a nivel de ventana. Un predictor de afinidad o presentación no responde exactamente a la tarea binaria de presencia de epítopo anotado. Evitar comparar directamente AUC de tareas incompatibles. Revisar además solapamiento de datos de entrenamiento externos con IEDB y posible contaminación de benchmark.

## 15. COSMIC, neoantígenos y escape inmunitario

Se ha trabajado en recopilación de mutaciones recurrentes de cáncer desde COSMIC y generación de candidatos. La conexión conceptual con NAP-CNB consiste en construir secuencias mutadas y de referencia, extraer ventanas alrededor de variantes y priorizar candidatos para análisis de presentación y reconocimiento. No consta una evaluación final integrada de esta línea.

Un workflow completo necesitaría identificar variante, ensamblaje, transcrito, consecuencia codificante, proteína, posición aminoacídica, secuencias wild-type/mutant y evidencia de expresión. Las variantes no sinónimas, indels y frameshifts requieren tratamientos distintos. Debe mantenerse la correspondencia entre coordenadas genómicas, transcriptómicas y proteicas.

El escape por pérdida o alteración de MHC-I puede limitar inmunoterapias dependientes de presentación antigénica. CAR-T reconoce antígenos de superficie de forma generalmente independiente de MHC; es una línea complementaria, no una aplicación automática del predictor de epítopos T. La selección de dianas CAR-T requiere criterios de expresión superficial, especificidad tumoral y seguridad diferentes.

## 16. Integración en Scipion-Chem y RNA-seq

Scipion permite organizar protocolos, objetos, dependencias, procedencia y ejecución reproducible. La línea de RNA-seq busca preparar datos que puedan alimentar análisis de expresión y detección de mutaciones relacionados con NAP-CNB.

### 16.1. Protocolos y entorno

- `import_fastq`: importación de lecturas single-end o paired-end.
- `fastp`: preprocesamiento, filtrado y control de calidad.
- `alignment`: alineamiento mediante STAR o HISAT2.
- `download_genome`: descarga de referencias desde Ensembl o NCBI.
- Entorno `rnaseq-1.0`: FastQC 0.12.0, fastp 0.23.4, STAR 2.7.11b, HISAT2 2.2.1, samtools 1.19.
- Referencias probadas: GRCh38.116 y GRCm39.116 (la numeración 116 se asocia a la release de anotación comunicada).
- Muestras de prueba: SRR390728 paired-end y SRR1552445 single-end.

Se continúa testeando el pipeline con diferentes muestras utilizadas en NAP-CNB. La detección de variantes a partir de RNA-seq requiere precauciones adicionales por splicing, cobertura desigual, expresión alélica y RNA editing; no equivale a un pipeline validado de llamada somática a partir de DNA tumor-normal.

### 16.2. Modelo de objetos

La regla de diseño comunicada es que los protocolos de importación pueden admitir rutas externas, pero deben producir objetos Scipion; los protocolos posteriores deben consumir objetos mediante punteros, no rutas arbitrarias como sustituto del modelo de datos.

En la revisión de la PR 237 se discutieron `SequenceVariants`, `MutationReport`, un posible objeto `VCFFile` y visualización IGV. Debe distinguirse el nivel genómico (VCF, coordenadas, alelos, genotipo y metadatos) del nivel proteico (sustituciones o variantes de secuencia y reportes). No se ha verificado aquí qué clases existen exactamente en la PR ni qué campos almacena cada una. No atribuir `SequenceVariants` a una implementación propia sin revisar el código.

### 16.3. Infraestructura y restricciones

`/home/nap/ScipionUserData`, `/home/nap/ScipionUserData-tfgnoelia` y `/data/nap/ScipionUserData/projects` son rutas comunicadas. Conda ha estado restringido por TI; se ha trabajado con migración mediante conda-pack. VS Code remoto/ACP ha presentado bloqueos, aunque el trabajo local funciona. Estas restricciones afectan instalación y reproducibilidad operativa.

El TFG de Noelia (`Antimicrobial_Target_Workflow`) es un proyecto paralelo relacionado con buenas prácticas de Scipion, no parte del entrenamiento de NAP-CNB. Se revisó `protocol_download_proteome`, proponiendo GFF3 como opción de descarga y objetos Scipion como entradas de protocolos posteriores.

## 17. Cronología resumida

| Periodo de 2026 | Trabajo comunicado |
|---|---|
| Enero–febrero | Inicio doctoral, revisión del sistema de referencia ProteinUnet/BERT, adaptación a ventanas de 25 aa y entornos |
| Marzo | Automatización IEDB, clasificación de ventanas, posición relativa, representaciones y COSMIC |
| Abril | ProtT5 a gran escala, predicción secundaria UniRef50, paralelización y resolución de incidencias CUDA/rutas |
| Mayo–junio | MLM SecondaryBERT, alineamiento primaria/secundaria por grupo, procesamiento BLOSUM y migración a `/data` |
| Agosto | Diseño de baselines LR/MLP, ablaciones de features, scaler TRAIN y estrategias de desbalanceo |
| Septiembre | Generación secundaria multi-GPU completada; revisión de checker; presentación y seguimiento TAC |
| Octubre | Separación conceptual modelo/pipeline; documentación NAP-CNB-ML, entrenamiento por chunks |
| 10–12 noviembre | Curso Scipion-Chem |
| Primera mitad de noviembre | Shuffling, recálculo scaler, concatenación primaria/secundaria y entrenamiento |
| 17–18 noviembre | Sobreajuste, auditoría de etiquetas globales, duplicados y revisión de splits |
| 23 noviembre | D1 certificado según resumen, piloto H2-L, preparación D2/E3/E4 y bloqueo de compatibilidad |

## 18. Estado y pendientes prioritarios

| Componente | Estado según contexto |
|---|---|
| Recuperación IEDB y ventanas | Desarrollado históricamente; falta certificar versión y filtros |
| ProtT5 | Generación histórica a gran escala; compatibilidad reciente pendiente |
| SecondaryBERT | Generación para 11 datasets comunicada como completada |
| Etiquetas | Auditoría cuantitativa realizada; política global decidida |
| D1 | Catálogo y split certificados según resumen del 23/11 |
| D2 | En preparación; piloto histórico H2-L |
| E3/E4 | No ejecutados según último estado disponible |
| LR/MLP | Pruebas históricas realizadas; evaluación definitiva pendiente |
| Comparación externa | Planificada |
| Scipion RNA-seq | Desarrollo y testing en curso |
| Validación experimental | Pendiente de resultados documentados |

**Prioridad obsoleta, sustituida por §0.5.** El bloqueo de embeddings quedó resuelto y D2 no debe ejecutarse. Se conserva el texto siguiente como registro de lo que se pensaba el 23 de noviembre de 2026: resolver el bloqueo de embeddings del piloto antes de escalar D2. Después, completar evaluación reproducible de originales frente a aumento TRAIN-only y comparar estrategias de entrenamiento. No utilizar resultados históricos con split por filas como estimación definitiva de generalización.

## 19. Información que debe acompañar cada ejecución

Registrar commit y estado del repositorio, versión de fuentes, hashes de datasets y matriz BLOSUM, política de etiquetas, definición de grupo, manifiesto de split, conteos de originales y variantes, duplicados retirados, checkpoints, tokenización, pooling, dtype, scaler, arquitectura, optimizer, learning rate, batch, epochs, scheduler, loss, class weights, seeds, hardware, tiempo, logs, checkpoints y métricas. Conservar el TEST congelado y registrar cualquier acceso que pueda influir en decisiones posteriores.

Pruebas mínimas: integridad de archivos, shapes, ausencia de NaN/Inf, consistencia de IDs, secuencias de 25 aa, alfabeto canónico, ausencia de fugas según unidad elegida, coherencia de labels, consistencia de embeddings entre ejecuciones, reproducibilidad de split y comprobación de que scaler y sampling no usan VALIDATION/TEST.

## 20. Glosario

- **IEDB:** Immune Epitope Database.
- **MHC/HLA/H-2:** complejo mayor de histocompatibilidad y nomenclaturas humana/murina.
- **ProtT5:** modelo de lenguaje proteico basado en T5.
- **SecondaryBERT:** modelo BERT especializado en secuencias de estructura secundaria.
- **MLM:** masked language modeling.
- **BLOSUM62:** matriz de puntuación de sustituciones de aminoácidos.
- **LR/MLP:** regresión logística y perceptrón multicapa.
- **Chunk:** fragmento de datos para procesamiento y entrenamiento escalable.
- **Leakage:** transferencia indebida de información entre particiones.
- **Unlabeled:** observación sin etiqueta positiva conocida, no necesariamente negativa biológica.
- **COSMIC:** Catalogue of Somatic Mutations in Cancer.
- **VCF:** Variant Call Format.
- **IGV:** Integrative Genomics Viewer.
- **D1/D2:** identificadores de versiones experimentales de datos; verificar definición formal en repositorio.

## 21. Límites de esta reconstrucción y documentación pendiente

Las secciones 1 a 21 se basan en conversaciones históricas y resúmenes recuperados, no en una lectura exhaustiva de los repositorios, Notion, artículos de referencia o archivos de ejecución. **La sección 0 sí procede de artefactos del repositorio y de la lectura directa de Wert-Carvajal 2021, Méndez-Pérez 2024, Guillén 2021, Ballesteros 2022 y Sánchez 2024.** Faltan fórmulas exactas de posición, filtros IEDB, releases, esquema de alelos, política detallada de BLOSUM, arquitectura final de SecondaryBERT, definición de E1/E2/E3/E4, manifiestos y métricas recientes. No se han inventado esos detalles. Las propuestas metodológicas se han separado de los resultados comunicados. Las cifras de distintas etapas pueden corresponder a snapshots incompatibles; deben conservarse como historial hasta reconciliarlas con los artefactos originales.

Para mantener este documento como memoria de proyecto, añadir futuras actualizaciones con fecha, commit, cambios de diseño, evidencia, resultados, incidencias y decisiones; conservar las versiones anteriores en lugar de sustituir retrospectivamente la historia experimental.
