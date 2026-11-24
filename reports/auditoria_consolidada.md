# NAP-CNB · Auditoría consolidada, diagnóstico y plan

**Fecha:** 23 de noviembre de 2026 · **Rama:** `ml_model_comparison`

Este documento reúne en un solo lugar qué se auditó, qué se encontró, qué se hizo
en consecuencia y qué se propone a continuación. Está escrito para que sustituya a
la lectura de las 44 carpetas de `results/`: cada hallazgo queda aquí con sus
cifras, de modo que los directorios que se archiven o borren más adelante dejen
constancia previa. El índice carpeta por carpeta está en
[docs/INDICE_EVIDENCIA.md](../docs/INDICE_EVIDENCIA.md).

---

## 1. Resumen ejecutivo

El predictor rinde mal y las auditorías han localizado la causa. **No está en los
datos ni en el código: está en cómo se ha formulado la tarea.**

Tres hechos lo resumen:

1. **Las auditorías de embeddings salieron limpias.** Muestras bit-exactas,
   finitud, cobertura y digests verificados. La hipótesis de corrupción queda
   descartada. No procede seguir auditando embeddings.
2. **Las cifras históricas altas eran fuga de información, pero el 0,68 de v2 no
   lo es.** El 99,70 % de los grupos aparecía en varias particiones del protocolo
   histórico y el 87,38 % en las tres a la vez; su ROC-AUC de 0,795 cae a 0,680 con
   particiones por primaria exacta. Pero al eliminar **toda** la fuga restante con
   una partición por componentes de proteína, el rendimiento se mantiene: 0,674668
   en la MLP y 0,662294 en la LR. **El nivel de 0,66–0,68 es generalización real a
   proteínas no vistas.**
3. **El techo de rendimiento es estructural.** Ventanas contiguas de 25 aa
   comparten 24 residuos y difieren en la etiqueta. Medidas en el espacio
   normalizado de E1, esas parejas con etiqueta opuesta están a distancia mediana
   **12,71**, frente a **58,13** entre ventanas de proteínas distintas (coseno
   0,9455). La etiqueta cambia mientras las características apenas se mueven: eso
   es error irreducible y explica por sí solo un ROC-AUC de 0,65–0,68.

A ello se añade que el dataset es mucho más pequeño de lo que sugieren sus cifras:
**49.123.503 ventanas proceden de 28.872 proteínas, que a su vez forman solo 16.349
unidades independientes**. Los 1.449.852.950 de filas del corpus histórico son
redundancia sobre redundancia.

**Recomendación central:** cerrar la línea histórica aumentada con BLOSUM62, no
ejecutar D2, y reinvertir el cómputo en (a) medir qué aporta cada modalidad, (b)
una partición honesta por proteína, (c) incorporar el contexto MHC a la entrada y
(d) pasar de ventana a péptido con representación por residuo.

---

## 2. Qué se auditó y qué salió

### 2.1 Embeddings y representaciones — sin corrupción

| Auditoría | Resultado |
|---|---|
| Redundancia exacta (muestra) | De 1.203 secuencias repetidas, 1.203 con todos los ProtT5 idénticos y 1.197 con ambas modalidades idénticas |
| Modalidades muestreadas | 33 grupos (3 por familia): coincidencia exacta con Primary archivado y Secondary original, diferencia máxima cero, todos los valores finitos |
| Representaciones divergentes | Seis secuencias con representaciones distintas, caracterizadas e imputadas a su origen |
| Sensibilidad a sustituciones | 110 grupos y 2.750 sustituciones BLOSUM62: coseno mediano 0,9883 |

**Conclusión:** los embeddings son correctos. Esta vía de investigación está cerrada.

### 2.2 Procedencia de los embeddings históricos — irresuelta, y por eso se regeneró

La auditoría de embeddings históricos sobre la selección definitiva encontró:

| Métrica | ProtT5 | SecondaryBERT |
|---|---:|---:|
| Entradas únicas v2 | 14.530.324 | 1.847.436 |
| Con embedding histórico localizado | 14.260.167 | 1.819.032 |
| **Con embedding reutilizable verificado** | **0** | 1.819.032 |
| Con procedencia insuficiente | 14.260.167 | 0 |

La fase 3A.3 confirmó por qué: de 14.503 bloques canónicos se identificaron 12
series probables (13.399 bloques, 92,388 %), pero **0 ejecuciones identificables y
0 configuraciones vinculadas por recibo a sus salidas**. H2-D quedó sin procedencia
resuelta, con 1.104 bloques y 18 inversiones cronológicas.

**Consecuencia:** ProtT5 se regeneró íntegramente (14.530.324 embeddings, 146
shards, revisión Rostlab fijada `94a6abc0…`, verificación de reapertura con cero
inferencias nuevas). SecondaryBERT se reutilizó con procedencia verificada. Esto
es correcto y no hay que repetirlo. Pero **implica que D2 exigiría regenerar
también las variantes BLOSUM62 en GPU**, porque los embeddings históricos de las
variantes no coinciden bit a bit (L2 mediana 0,00178).

### 2.3 Etiquetas — el problema grave

| Hallazgo | Cifra |
|---|---:|
| Secuencias distintas en el corpus original | 15.135.904 |
| Secuencias con ambas etiquetas al combinar las 11 familias | 3.494.284 (23,09 %) |
| Filas que contienen esas secuencias | 21.877.306 (39,23 %) |
| Filas con ambas etiquetas **dentro de su propia familia** | 916.544 (1,64 %) |
| **Filas positivas cuya secuencia aparece como negativa en algún sitio** | **93,53 %** |
| Filas negativas cuya secuencia aparece como positiva en algún sitio | 27,58 % |

La causa es de diseño, no un error: la etiqueta marca positiva una ventana si
*cualquiera* de las 11 familias registra un epítopo ahí, y **el alelo no forma
parte de la entrada**. Se está pidiendo al modelo predecir una magnitud que no es
función de su input, porque la presentación antigénica es específica de alelo. La
prevalencia lo refleja: 11,37 % en la selección por familia frente a 25,46 % con
etiqueta global.

A esto se suma el ruido en la clase negativa: la auditoría de epítopos omitidos
revisó 30.383 proteínas y 681.805 epítopos positivos distintos, y encontró
**596.063 filas con coincidencia de secuencia (170.771 ventanas distintas)** sin
anotación global positiva. Los negativos se construyen por ausencia de anotación,
no por evidencia experimental negativa.

### 2.4 Particiones — el problema que invalidaba las métricas

Revisadas las 1.449.852.950 filas aumentadas y los 55.763.575 grupos:

| Medida | Valor |
|---|---:|
| Reparto por filas | 80/10/10 exacto |
| Grupos en varias particiones | 55.595.967 (99,70 %) |
| Grupos en las tres particiones | 48.726.754 (87,38 %) |
| Grupos solo en TRAIN | 167.608 |
| Grupos exclusivos de VALIDATION o TEST | 0 |

No es una avería: la política reparte filas *después* de generar 26 variantes por
grupo. Sirve para evaluar variantes de grupos conocidos, no para estimar
generalización. Sumado a que el protocolo histórico seleccionaba checkpoint en
TEST STAGE, las cifras históricas no son un TEST independiente.

### 2.5 Fuentes IEDB y coordenadas — reconstruidas y acotadas

| Auditoría | Resultado |
|---|---|
| Descarga y normalización | 1.985.260 registros en 22 exportaciones. La reproducción A coincide exactamente con las claves de los 948.344 eventos históricos. La variante B conserva los mismos ensayos en 1.016.016 grupos |
| Deduplicación histórica | Colapsaba 1.034.878 registros; 327.644 eventos tenían varios ensayos y el fusionado no guardaba los IRI |
| Coordenadas recuperadas | De 102.654 eventos, 102.420 con una única ocurrencia exacta y 234 con varias; ninguno sin ocurrencia dentro del grupo |
| Contrafactual de coordenadas | 92.623 eventos recuperados (90,23 %); 10.031 sin resolver |
| Eventos pendientes | 56.192 registros de ensayo para 44.907 grupos; 253 sin esqueleto en la referencia parent y 254 sin intervalo verificado |
| Péptidos modificados | 147.985 registros modificados y 81.679 esqueletos lineales; 54.686 esqueletos con entidad simple distinta y 49.237 con respaldo positivo simple |

**Conclusión:** la reconstrucción v2 desde IEDB está acreditada y sus límites están
cuantificados. No procede ampliar estas auditorías.

---

## 3. Qué se hizo en consecuencia

1. **Reconstrucción v2 desde IEDB** con procedencia verificada por familia.
2. **Selección definitiva:** 49.123.503 ventanas con estructura secundaria
   verificada al 100 % (se excluyeron 7.455 positivas y 74.146 negativas
   operativas por falta de C/H/E).
3. **Regeneración completa de ProtT5** y reutilización verificada de SecondaryBERT.
4. **Vista certificada D1:** 15.100.592 representaciones, 14.530.324 primarias
   únicas, splits por primaria exacta con semilla 42, prevalencia ~25,46 %.
5. **Protocolo de evaluación corregido:** selección de checkpoint en VALIDATION y
   TEST puntuado una sola vez, con hashes de insumos cotejados antes de entrenar.
6. **Dos referencias limpias y comparables:**

| Experimento | TEST ROC-AUC | TEST AP | Log loss | Parámetros |
|---|---:|---:|---:|---:|
| E1 · Regresión logística | 0,654641 | 0,375738 | 0,539791 | 1.793 |
| E2 · MLP 1792-512-128-1 | 0,680107 | 0,412129 | 0,527197 | 985.089 |

La MLP aporta **+0,025 ROC-AUC** sobre la regresión logística con 550 veces más
parámetros. Las 1.792 características tienen poca estructura no lineal explotable:
el problema no está en la arquitectura.

---

## 4. Diagnóstico: por qué el rendimiento es bajo

Cuatro factores, en orden de impacto estimado.

### 4.1 El objetivo no es función de la entrada

El alelo no está en el input y la etiqueta global une las 11 familias. Es la causa
del 93,53 % de positivos que aparecen también como negativos.

### 4.2 Las ventanas contiguas son casi indistinguibles, y la etiqueta cambia

Ventanas de 25 aa con desplazamiento de 1 comparten 24 residuos. Medición sobre
4.000 parejas reales de H2-D (adyacentes, etiqueta opuesta), en el espacio del
scaler de E1:

| Parejas | Distancia mediana | p10 | p90 |
|---|---:|---:|---:|
| Adyacentes, etiqueta opuesta (1.792) | **12,71** | 8,07 | 26,33 |
| Aleatorias, proteínas distintas (1.792) | 58,13 | 42,82 | 75,11 |
| Adyacentes opuesta — solo ProtT5 (1.024) | 10,89 | 6,93 | 25,47 |
| Aleatorias — solo ProtT5 (1.024) | 43,58 | 31,51 | 56,20 |
| Adyacentes opuesta — solo SecondaryBERT (768) | **4,20** | 1,67 | 9,83 |
| Aleatorias — solo SecondaryBERT (768) | 36,74 | 19,77 | 55,85 |

Ratio de medianas 0,219; coseno 0,9455. La causa inmediata es que ProtT5 se agrega
como **media sobre las 25 posiciones**, lo que destruye la información posicional
de la que depende la etiqueta. Para MHC-I el epítopo ocupa 8–11 de los 25
residuos: menos de la mitad de la ventana decide la clase, y el promedio la diluye.

**SecondaryBERT es el caso extremo** (ratio 0,114): la estructura secundaria de
ventanas contiguas es prácticamente idéntica, justo donde la etiqueta se decide.
La ablación en curso cuantifica si sus 768 características aportan algo.

### 4.3 El tamaño efectivo del estudio es 16.349, no 49 millones

| Nivel | Unidades |
|---|---:|
| Filas aumentadas (histórico) | 1.449.852.950 |
| Ventanas seleccionadas (v2) | 49.123.503 |
| Representaciones D1 | 15.100.592 |
| Primarias únicas | 14.530.324 |
| **Proteínas distintas (`parent_accession`)** | **28.872** |
| **Componentes independientes** | **16.349** |

Un componente es un grupo de proteínas que no se pueden separar porque comparten
al menos una ventana de 25 aa. Distribución:

| Proteínas por componente | Componentes | Proteínas |
|---:|---:|---:|
| 1 | 8.265 | 8.265 |
| 2 | 6.228 | 12.456 |
| 3 | 896 | 2.688 |
| 4 | 489 | 1.956 |
| 5 | 177 | 885 |
| ≥6 | 294 | 2.622 |

El mayor reúne 73 proteínas. **20.607 proteínas (71 %) comparten componente con
otra**, por lo que una partición por `parent_accession` habría seguido filtrando.

### 4.4 La fuga por proteína **no** inflaba las métricas

D1 reparte por primaria exacta, y las ventanas contiguas son primarias distintas
(en H2-D, 3.036.554 secuencias distintas para 3.072.856 ventanas). Con un reparto
80/10/10, la probabilidad de que una ventana de TEST tenga al menos un vecino
inmediato en TRAIN es 1 − 0,2² ≈ 96 % (valor derivado). De ahí la hipótesis de
que el 0,680 de E2 estuviera inflado.

**La hipótesis se ha comprobado y es falsa.** Con una partición por componentes de
proteína, que deja TEST sin un solo vecino en TRAIN
([informe](experiments/d1_protein_split.md)):

| Modelo | Partición | TEST ROC-AUC | TEST AP | AP / prevalencia |
|---|---|---:|---:|---:|
| LR | primaria exacta | 0,654641 | 0,375738 | 1,4763 |
| LR | componentes de proteína | **0,662294** | 0,379399 | 1,5559 |
| MLP | primaria exacta | 0,680107 | 0,412129 | 1,6193 |
| MLP | componentes de proteína | **0,674668** | 0,395093 | 1,6202 |

Eliminar la fuga cuesta 0,0054 de ROC-AUC en la MLP y **mejora** 0,0077 en la LR.
La caída de AP se debe al cambio de prevalencia, no al modelo: normalizada por la
prevalencia es 1,6193 frente a 1,6202, es decir, idéntica.

**El nivel de 0,66–0,68 es generalización real a proteínas no vistas.** El 0,7955
histórico sigue explicándose por su partición **por fila**, una fuga mucho más
severa, porque con 26 variantes BLOSUM62 de la misma ventana repartidas por fila
TEST contenía casi duplicados exactos de TRAIN.

Consecuencia para el diagnóstico: el techo **no** se explica por fuga, ni por
ruido de etiqueta (D1 no tiene ni un grupo mixto por primaria), ni por corrupción
de embeddings. Queda atribuido íntegramente a la representación y a la
formulación de la tarea, es decir a 4.1 y 4.2.

Además, ninguno de los dos modelos con partición por componentes había convergido:
su log loss de VALIDATION descendía de forma monótona y seguía mejorando al
acabar la época 3, mientras que E2 toca su mínimo en la época 2 y empeora en la 3.
Por tanto **0,674668 es una cota inferior**, y repetir con 10 épocas es el
experimento pendiente de mayor valor por coste.

---

## 5. Qué se está ejecutando ahora

| Experimento | Pregunta | Estado |
|---|---|---|
| Ablación por modalidad | ¿Aportan las 768 de SecondaryBERT, o basta ProtT5? | ProtT5-solo y SecondaryBERT-solo, protocolo idéntico a E2 |
| Partición por componente de proteína | ¿Cuánto de 0,680 sobrevive? | LR y MLP, scaler reajustado sobre el nuevo TRAIN |
| MLP histórica (14.499 chunks) | Cierre documental de la línea histórica | Época 2; época 1 dio ROC-AUC 0,7955 |

Partición nueva, con los componentes como unidad indivisible y semilla 42:

| Split | Componentes | Filas | Prevalencia |
|---|---:|---:|---:|
| TRAIN | 13.105 | 12.079.478 | 25,76 % |
| VALIDATION | 1.504 | 1.510.799 | 24,15 % |
| TEST | 1.701 | 1.510.315 | 24,38 % |

Los tamaños son casi idénticos a los de D1 (12.083.630 / 1.507.558 / 1.509.404),
de modo que la diferencia de métricas será atribuible a la partición y no al
volumen de entrenamiento. El scaler se reajusta sobre el nuevo TRAIN: reutilizar
el de E1 habría filtrado las proteínas de TEST. Recuentos y población de ajuste
verificados contra el resumen de la partición; scaler publicado con SHA-256
`2470f082007368ca00de8d8b5d799b3984558747f5d60a735b50b1684060e7d7`, distinto del
de E1/E2 (`0a983b6c…`) como corresponde.

**Al comparar, dos cautelas.** El ROC-AUC es insensible a la prevalencia y es
directamente comparable con el 0,680 de E2. La *average precision* no lo es: la
prevalencia de TEST baja de 25,45 % a 24,38 %, lo que deprime la AP de forma
mecánica con independencia del modelo. Y la asignación por componente no permite
igualar la prevalencia exactamente, porque el componente es indivisible.

---

## 6. Plan propuesto

Ordenado por coste creciente y por valor decreciente de la información que aporta.

**Inmediato, sin coste nuevo**

1. **Cerrar la línea histórica.** Conservar la época 1 como cierre documental. Las
   épocas 2–10 no cambian ninguna conclusión: la partición ya invalida la métrica,
   y a 85,4 h por época terminarían hacia el 23 de diciembre.
2. **No ejecutar D2 (aumentación BLOSUM62).** Las variantes están a coseno 0,9883 y
   distancia 6,60 tras el scaler, **más cerca entre sí que la distancia que separa
   etiquetas opuestas reales (12,71)**. Heredan la etiqueta, así que no añaden
   información sobre el objetivo; multiplicarían ×26 un corpus ya redundante ×600;
   el experimento histórico ya fue ese experimento y no ayudó; y exigiría regenerar
   los embeddings en GPU porque la procedencia histórica está irresuelta.

**Esta semana, con los artefactos ya materializados**

3. **Ablación por modalidad** (en curso). Si SecondaryBERT aporta poco, es un
   hallazgo crítico sobre la contribución novedosa del trabajo y hay que conocerlo
   ahora, no dentro de seis meses.
4. **Partición por componente de proteína** (en curso). Da el número honesto. Sin
   él no puede afirmarse generalización.

**Siguiente fase, por orden de impacto esperado**

5. **Incorporar el contexto MHC a la entrada.** Las columnas `family`, `organism` y
   `mhc_class` ya están en los Parquet de familia. Mejor aún, la pseudosecuencia
   del alelo, al estilo NetMHCpan. Es el cambio con mayor ganancia esperada, porque
   convierte una tarea mal planteada en la que el campo resuelve.
6. **Pasar de ventana a péptido.** 8–11 aa para MHC-I y 13–25 para MHC-II;
   representación por residuo en lugar de la media; negativos como señuelos del
   mismo proteoma emparejados por longitud, deduplicados por péptido exacto para
   que ningún péptido sea a la vez positivo y negativo. Ataca directamente la causa
   de 4.2.
7. **Comparar contra NetMHCpan y MHCflurry** sobre un conjunto de test común. Es
   requisito para publicar. Si NAP-CNB v2 no los supera, hay que reencuadrar la
   contribución —por ejemplo la modalidad de estructura secundaria como
   complemento— y conviene saberlo antes de invertir más.

Cualquier resultado nuevo debe heredar un protocolo explícito: unidad de
partición declarada, selección en VALIDATION, TEST puntuado una vez, y reporte de
prevalencia y matriz de confusión. No comparar con las cifras históricas altas.

---

## 7. Inventario: qué se conserva, qué se archiva y qué se borra

Ninguna ruta se ha modificado al escribir este informe. `results/*` y `data/*`
están en `.gitignore`: **no tienen historia en git y su borrado es irreversible.**
Esta tabla queda como constancia previa a cualquier retirada.

### 7.1 Conservar

| Ruta | Tamaño | Motivo |
|---|---:|---|
| `results/nap_cnb_v2_prott5/` | 56G | Almacén certificado. Referencia de los embeddings |
| `results/nap_cnb_v2_d1_materialized/` | 99G | Única ruta a D1 sin acceso aleatorio. En uso activo |
| `results/nap_cnb_v2_training/` | 3,3G | E1, E2, ablación y sus predicciones |
| `results/nap_cnb_v2_protein_split/` | 326M | Componentes y partición nueva |
| `results/nap_cnb_v2_dataset_views/`, `nap_cnb_v2_final_selection/`, `nap_cnb_v2_phase1/`, `nap_cnb_v2_secondarybert/` | 2,8G | Contratos y construcción del dataset certificado |
| `data/data_input_nn/`, `data/used_data/` | 3,4T + 31G | Raíz de procedencia comprimida |
| `tests/`, `data_pipeline/`, `neural_network/`, `docs/`, `reports/` | 9M en total | 216 pruebas en 62 s, en CI. Ningún script está huérfano: el mínimo son 5 referencias |

### 7.1 bis · Auditorías retiradas el 23 de noviembre de 2026

Las 22 carpetas de auditoría de las secciones 2.1–2.5 se retiraron de `results/`
tras verificarse que sus hallazgos quedan recogidos en este informe. Liberaron
**3,2 GB**.

Antes de borrarlas se migraron sus 20 informes y 5 resúmenes JSON —185 KB en
total— a [reports/audits/](audits/README.md), copiados con verificación de SHA-256
y ahora versionados en git, que es más de lo que estaban antes. Lo que no se
conservó son los artefactos de datos: CSV, Parquet, JSONL y matrices intermedias.

| Carpetas retiradas |
|---|
| `data_contradictions`, `group_split_check`, `sampled_modalities_check`, `primary_mutation_test` |
| `nap_cnb_v2_embedding_audit`, `nap_cnb_v2_prott5_audit_3a`, `3a2`, `3a3` |
| `exact_embeddings_sample`, `exact_embeddings_cost`, `embedding_representation_cases`, `global_epitope_labels_sample` |
| `iedb_download_audit`, `iedb_modified_audit`, `iedb_pending_evidence`, `iedb_rebuild_v1_pilot`, `source_audits_inputs` |
| `omitted_epitopes_full`, `omitted_epitopes_sample`, `epitope_counterfactual`, `epitope_coordinate_provenance`, `recovered_epitope_coordinates` |

**Consecuencia asumida:** si en el futuro hiciera falta la evidencia fila a fila de
alguno de estos hallazgos —por ejemplo el CSV por grupo que sostiene el 99,70 % de
solapamiento, o el detalle por secuencia del 93,53 %— habría que regenerarla
reejecutando su script, que sigue en `data_pipeline/scripts/`. Las cifras
agregadas no se pierden.

### 7.2 Comprimir

| Ruta | Tamaño | Medición |
|---|---:|---|
| `data/data_input_nn_shuffled_concatenate/` | 9,5T | Medido sobre un chunk real de 0,67 GiB: zstd −1 ahorra 20,1 %, −3 ahorra 28,7 %, −9 ahorra 35,7 % |

Son 14.499 chunks de cuatro arrays; los ficheros `X` concentran prácticamente todo
el volumen. A nivel −3 el ahorro esperado es de **~2,7 TB**, y a −9 de **~3,4 TB**,
con un coste de entrada/salida de unas 16 TB leídas y escritas.

**Dos condiciones:** (a) la MLP histórica está leyendo ahora mismo ese directorio,
así que la compresión no puede empezar hasta que se detenga; (b) comprimido deja de
ser entrenable directamente y habría que descomprimirlo para reanudar esa línea.

### 7.3 Candidatos a retirada, con constancia en este informe

| Ruta | Tamaño | Situación |
|---|---:|---|
| `results/nap_cnb_v2_d1_experimental/`, `d1_representations/`, `d1_original_manifest/` | 479M | Etapas intermedias superadas por la vista certificada D1 |
| `results/nap_cnb_v2_phase1_pilot/`, `phase1_structure/` | 28M | Pilotos superados por la fase 1 definitiva |
| `results/logistic_regression_balanced/`, `logistic_regression_all/`, `logistic_regression_balanced_epoch2_archived/` | 1,6G | Línea histórica, partición por fila |
| `results/nap_cnb_v2_blosum_preparation/`, `blosum_materialized/` | 1,0G | Preparación de D2, que se propone no ejecutar |
| `data/data_input_nn_shuffled/` | 3,6T | Reproducible desde `data_input_nn` y `reorder_manifest.json` |

---

## 8. Revisión de código: defectos y oportunidades

Revisión línea a línea del 23 de noviembre de 2026 sobre el clasificador de
etiquetas, la descarga de IEDB, la aumentación BLOSUM62, los splits, los scalers y
el entrenamiento histórico.

### 8.1 Solo se descargan ensayos positivos de IEDB

[`build_iedb_dataset.py:254`](../data_pipeline/scripts/data_download/build_iedb_dataset.py#L254)
filtra `assay__qualitative_measurement = ilike.*Positive*`. **Los ensayos con
resultado negativo nunca se descargan.** Por eso la clase negativa se construye
por ausencia de anotación y no por evidencia experimental, con el ruido que
documenta la sección 2.3 (596.063 filas con coincidencia de secuencia sin
anotación positiva).

IEDB publica también los ensayos negativos. Obtenerlos es cambiar un filtro.
Es la corrección de mayor valor por unidad de esfuerzo de todo el proyecto.

### 8.2 La etiqueta mezcla unión a MHC con reconocimiento por células T

[`build_iedb_dataset.py:291`](../data_pipeline/scripts/data_download/build_iedb_dataset.py#L291)
concatena `rows_mhc + rows_tcell` en un único conjunto de eventos y descarta la
distinción. Son dos fenómenos biológicos distintos: la presentación por MHC y la
inmunogenicidad. Un péptido puede unirse con fuerza y no ser inmunogénico, que es
el caso de la mayoría de los péptidos propios. Para neoantígenos el objetivo es la
inmunogenicidad, y la unión es solo un filtro previo. La auditoría de descarga
cuantifica la proporción: 1.962.329 registros MHC frente a 22.931 de células T.

### 8.3 La aumentación BLOSUM62 enseña la invarianza contraria a la tarea

[`generate_blosum62_variants.py:63`](../data_pipeline/scripts/data_augmentation/generate_blosum62_variants.py#L63)
fija **una única sustitución por aminoácido**, el argmax de BLOSUM62, y genera 25
variantes de un solo cambio más el original. El mapa resultante:

| | |
|---|---|
| Aminoácidos que aparecen como sustituto | **11 de 20** (`ADEFIKLRSVY`) |
| Nunca aparecen como sustituto | `C G H M N P Q T W` |
| Empates resueltos por orden alfabético | `E D F G L N P S` |
| Sustituciones **no** conservativas | **P → A con score −1**; C → A y G → A con score 0 |

Prolina es estructuralmente única y rompe hélices; convertirla en alanina no es
una sustitución conservativa. Cisteína a alanina destruye puentes disulfuro.

El problema de fondo es conceptual: **un neoantígeno se diferencia de lo propio en
un solo residuo.** Esta aumentación asigna la misma etiqueta a secuencias que
difieren en un residuo, es decir, entrena exactamente la invarianza que la tarea
exige no tener. Es el argumento más fuerte para no ejecutar D2, por encima del
coste.

### 8.4 El techo de información de la estructura secundaria

Cálculo sobre las 12.083.630 filas de TRAIN de D1, agrupando por clave y tomando
la etiqueta mayoritaria de cada grupo. Da el máximo de exactitud alcanzable por
cualquier modelo que use solo esa información.

| Información disponible | Grupos | Techo de exactitud |
|---|---:|---:|
| Clasificador trivial (siempre la mayoritaria) | 1 | 74,5388 % |
| Solo composición C/H/E (3 números) | 342 | **74,5391 %** |
| Cadena C/H/E completa, 25 posiciones ordenadas | 1.587.321 | **77,7605 %** |
| Primaria exacta de 25 aa | 11.627.152 | 100,0000 % |
| Primaria + secundaria, la representación de D1 | 12.083.630 | 100,0000 % |

Dos consecuencias:

1. La cadena C/H/E completa tiene un techo de exactitud solo **+3,2 puntos** por
   encima del clasificador trivial, y su composición no añade prácticamente nada
   a ese techo. El margen disponible para la modalidad es estrecho de partida.
2. La primaria determina la etiqueta de D1 sin un solo grupo mixto. **D1 no tiene
   ruido de etiqueta**, su techo es el 100 %. Por tanto el 0,680 de E2 no se
   explica por etiquetas contradictorias, sino **íntegramente** por la
   representación y la generalización.

El techo de exactitud por mayoría es poco sensible con una prevalencia del
25,46 %, porque la clase mayoritaria domina casi todos los grupos. La medida
directa en capacidad de ordenación es más informativa, y se obtuvo entrenando
modelos sobre las mismas particiones de D1:

| Representación | Características | VALIDATION ROC-AUC |
|---|---:|---:|
| Composición C/H/E, regresión logística | **3** | **0,592364** |
| C/H/E posicional one-hot, regresión logística | 75 | 0,594317 |
| **SecondaryBERT promediado, MLP** | **768** | **0,601155** |
| ProtT5 promediado, MLP | 1.024 | 0,681629 |

Esto corrige una afirmación anterior más fuerte de lo que los datos sostienen. El
promediado **no** destruye por completo el orden: SecondaryBERT supera a la
composición. Pero la magnitud es la que importa:

- **Tres enteros** —el recuento de C, H y E en la ventana— alcanzan 0,592364.
- Todo el aporte de SecondaryBERT sobre esos tres enteros, incluyendo el
  preentrenamiento sobre UniRef30, el modelado de lenguaje enmascarado y sus 768
  dimensiones, es de **+0,0088 ROC-AUC**.
- Añadir el orden completo de forma lineal (75 características) aporta +0,002
  sobre la composición, de modo que el orden de C/H/E apenas contiene señal
  explotable para esta tarea.
- La modalidad de estructura secundaria es, en la práctica, **sustituible por tres
  características con el 98,5 % de su rendimiento aislado**, y es redundante
  cuando ProtT5 está presente.

El pooling es `mean_25_biological_tokens`
([`secondarybert_v2.py:86`](../data_pipeline/scripts/embeddings/secondary_structure/secondarybert_v2.py#L86)).

### 8.5 Criterio de contención y epítopos largos

[`epitope_classification.py:385`](../data_pipeline/scripts/data_classification/epitope_classification.py#L385)
exige `window_start <= ep_start and window_end >= ep_end`: contención **completa**
en 25 aa. Un epítopo de más de 25 residuos no puede ser positivo nunca, y sus
proteínas aportan solo negativos. La prevalencia lo refleja: MHC-I 10–21 % frente a
MHC-II 5,1–7,1 %, siendo los epítopos de MHC-II los más largos. Además, una ventana
que contiene 24 de los 25 residuos de un epítopo se etiqueta negativa, que es el
origen del acantilado de adyacencia de la sección 4.2.

### 8.6 Multiplicidad de filas y sobremuestreo de positivos

El clasificador emite **una fila por epítopo contenido** con características
idénticas. En el corpus histórico eso infló los positivos: 55.763.575 filas frente
a 49.205.104 ventanas. **La reconstrucción v2 lo corrigió**: multiplicidad medida
exactamente 1,0000 por `(parent_accession, window_start)` en las once familias.

En el entrenamiento histórico, `iter_balanced_chunk_batches` recicla la clase
minoritaria y fija el número de lotes según la mayoritaria, de modo que la época 1
presentó 1.009.541.120 positivos, unas 6 veces los positivos distintos. Al
multiplicarse con el solapamiento de ventanas, las 26 variantes BLOSUM62 y el
93,7 % de ventanas que comparten su primaria exacta con otra
(`windows_related_by_exact_primary = 46.034.117`), un único epítopo observado
experimentalmente llega a la red miles de veces por época en forma casi idéntica.

### 8.7 Campos de IEDB descartados y recuperables

La tabla de eventos fusionados conserva **6 columnas**:
`epitope__name_canonical`, posiciones de inicio y fin, `source_id`, `parent_id` y
`protein_id` ([`build_iedb_dataset.py:234`](../data_pipeline/scripts/data_download/build_iedb_dataset.py#L234)).
Los exports completos sí guardaban todos los campos de la API y están archivados
en `data/used_data/data_raw.tar.zst`, de modo que **nada hay que volver a
descargar**. Lo que se descarta en la fusión:

| Campo | Contenido | Por qué importa |
|---|---|---|
| `mhc_restriction__name` | El **alelo concreto** (H2-IEk, H2-IEp, H2-IEd…) | Solo sobrevive la familia. La unión es específica de alelo, no de familia |
| `assay__method` | Distingue ligandos eluidos por espectrometría de masas de los ensayos de unión competitiva | Es la separación EL/BA que usa NetMHCpan-4.1 |
| `assay__quantitative_measurement` | IC50 en nM, presente en el 22,7 % de la muestra inspeccionada | Permite regresión en lugar de clasificación binaria |
| `assay__qualitative_measurement` | Cuatro niveles: Positive, Positive-Low, Positive-Intermediate, Positive-High | Señal ordinal, colapsada a 1 |
| Tipo de ensayo | MHC frente a células T | Ver sección 8.2 |

### 8.8 Sensibilidad del modelo a una sustitución de un residuo

Requisito que la segunda parte de la tesis impone a la primera: si a la red se le
pasan péptidos mutados de un paciente, su puntuación debe moverse respecto al
silvestre, o el listado de probabilidades no contiene información.

Medición sobre las **89.179 variantes BLOSUM62 archivadas de 3.569 observaciones
TRAIN**, puntuando padre y variante con los checkpoints seleccionados. Las
variantes son de **una sola sustitución** y **heredan la etiqueta**, así que el
cambio correcto de puntuación es aproximadamente cero.

| Medida | E2 (1.792) | Ablación (1.024) |
|---|---:|---:|
| Separación entre clases en VALIDATION completa (mediana pos − neg) | +0,4035 | +0,4524 |
| d de Cohen aproximada | 0,631 | 0,683 |
| \|Δlogit\| por una sustitución, mediana | 0,0524 | 0,0555 |
| \|Δlogit\| p90 | 0,2015 | 0,2079 |
| \|Δlogit\| p99 | 0,5930 | 0,5518 |
| Variantes que cruzan la mediana de decisión | **8,16 %** | **8,72 %** |

Lectura: el modelo **no** es invariante a las mutaciones, luego la segunda parte no
sería degenerada. Pero su respuesta no está calibrada con la relevancia del
cambio. Una sustitución que por construcción no debería alterar la respuesta mueve
el logit un 13 % de la separación entre clases en la mediana, **un 50 % en el
percentil 90 y más del 100 % en el percentil 99**, y una de cada doce cruza el
umbral de decisión.

Dos cautelas. Estas sustituciones son las más conservativas posibles, así que esto
mide la **especificidad** de la sensibilidad —la respuesta falsa a un cambio
irrelevante— y no la sensibilidad a un cambio que sí altera el estatus de epítopo.
Medir lo segundo exige pares de péptidos con etiqueta opuesta que difieran en un
residuo, lo que requiere los **ensayos negativos de la sección 8.1**. Además, la
etiqueta heredada de D1 difiere de la etiqueta histórica en **51.717 de las 89.179
variantes (57,99 %)**, lo que por sí solo cuestiona la herencia de etiqueta de la
aumentación.

### 8.9 Lo que está correcto

Conviene no corregir lo que ya funciona:

- **Asignación de splits.** `split_nap_cnb_v2.py` usa blake2b con clave sobre la
  primaria de 25 aa, módulo 10, y verifica la reproducibilidad al reabrir. Correcto.
- **Scaler histórico.** `fit_shuffled_scaler.py:78` filtra a TRAIN antes de
  acumular momentos. No hay fuga por normalización.
- **Estructura secundaria.** Se predice sobre la **proteína completa** y luego se
  recorta a la ventana, no por ventana aislada. Correcto.
- **Alfabeto de D1.** Las 12.083.630 filas de TRAIN usan solo los 20 aminoácidos
  estándar, sin residuos ambiguos.
- **Archivado.** `archive_inputs.py` verifica el SHA-256 descomprimido antes de
  desenlazar el original, con recibos atómicos y reanudable.

## 9. Trazabilidad

Cada hallazgo de la sección 2 procede de un informe en `results/`. La
correspondencia completa, con tamaños y estado, está en
[docs/INDICE_EVIDENCIA.md](../docs/INDICE_EVIDENCIA.md). Los experimentos E1 y E2
tienen informe propio en [reports/experiments/](experiments/), con hashes de
insumos, configuración, selección y matrices de confusión.
