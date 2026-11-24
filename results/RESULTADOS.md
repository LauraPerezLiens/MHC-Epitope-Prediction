# Resultados de NAP-CNB v2 — resumen

**Fecha:** 24 de noviembre de 2026. Extraído de los 17 directorios `nap_cnb_v2_*` de `results/`.

Este documento recoge **los números**. El razonamiento, las decisiones y lo pendiente están en `CLAUDE.md`, secciones 0.x.

---

## 1. Lo importante en una tabla

Todo lo de abajo es **TEST puntuado una sola vez**, con el modelo elegido por VALIDATION y la prevalencia real conservada. Son los resultados honestos.

| Experimento | Features | Partición | ROC-AUC | AP | Prevalencia | **AP / prevalencia** |
|---|---|---|---:|---:|---:|---:|
| **E1** · Regresión logística | 1.792 | primaria exacta | 0,654641 | 0,375738 | 25,451 % | **1,476×** |
| **E2** · MLP | 1.792 | primaria exacta | 0,680107 | 0,412129 | 25,451 % | **1,619×** |
| MLP · solo ProtT5 | 1.024 | primaria exacta | **0,682302** | **0,415255** | 25,451 % | **1,632×** |
| MLP · solo SecondaryBERT | 768 | primaria exacta | 0,601431 | 0,316272 | 25,451 % | 1,243× |
| LR | 1.792 | componentes de proteína | 0,662294 | 0,379399 | 24,385 % | 1,556× |
| MLP | 1.792 | componentes de proteína | 0,674668 | 0,395093 | 24,385 % | 1,620× |

### Las tres cosas que dicen estos números

**1. El 0,66–0,68 es generalización real, no artefacto.** Pasar de la partición por primaria exacta a la partición por **componentes conexos de proteína** —que elimina toda la fuga por homología— cuesta apenas **0,0054 de ROC-AUC** en el MLP (0,680107 → 0,674668). Si el resultado fuera fuga, se habría hundido.

**2. SecondaryBERT no aporta; resta.** El MLP con **solo ProtT5** (0,682302) es **mejor** que el MLP con ProtT5 + SecondaryBERT (0,680107). Añadir las 768 dimensiones de estructura secundaria **empeora** el modelo en 0,0022. Y SecondaryBERT en solitario se queda en 0,601431, apenas por encima del azar ajustado.

**3. El techo no es el modelo.** La diferencia entre un modelo lineal y una red neuronal es de **0,0255 de ROC-AUC**. Cambiar de familia de modelo no va a mover esto.

---

## 2. Comparación con lo publicado por el grupo

| | Wert2021 (Sci Rep) | E2, lo nuestro |
|---|---:|---:|
| ROC-AUC en held-out | **0,865** | 0,680 |
| AP (PR-AUC) | 0,4197 | 0,4121 |
| Prevalencia | 2,64 % | 25,45 % |
| **Lift (AP / prevalencia)** | **15,9×** | **1,62×** |

> ⚠️ **El AP parece casi igual (0,4197 frente a 0,4121) y eso engaña.** Lo que importa es el **lift**: con una prevalencia diez veces mayor, obtener el mismo AP es un resultado **diez veces peor**. La distancia real con el trabajo publicado es de un orden de magnitud.
>
> No citar nunca el 0,95 de Wert2021: ese es de validación cruzada. El número comparable es **0,865**.

---

## 3. Cómo se construyó el conjunto de datos

### 3.1. Fase 1 — ventanas originales (`nap_cnb_v2_phase1`)

| | |
|---|---:|
| Proteínas elegibles | 78.620 |
| Ventanas generadas | 49.486.659 |
| **Ventanas binarias** | **49.205.104** |
| Positivas | 5.594.529 |
| Negativas operativas | 43.610.575 |
| Secuencias primarias únicas | 14.554.919 |
| Combinaciones únicas secuencia + C/H/E | 15.006.963 |
| Cobertura estructural | 98,882 % |
| Holdouts (péptidos modificados excluidos) | 281.555 |

Cambios frente al histórico: salieron **4.138.869** posiciones, entraron **1.644.663** nuevas, **200.456** cambiaron de 0 a 1 y **100.025** de 1 a 0.

### 3.2. Selección definitiva (`nap_cnb_v2_final_selection`)

Se conservan solo las ventanas con estructura secundaria verificada.

| | Dataset binario | Selección definitiva |
|---|---:|---:|
| Ventanas | 49.205.104 | **49.123.503** |
| Positivas | 5.594.529 | 5.587.074 |
| Negativas | 43.610.575 | 43.536.429 |
| Cobertura estructural | 99,834 % | 100 % |
| Prevalencia | 11,370 % | **11,374 %** |

Se excluyeron 7.455 positivas y 74.146 negativas. El impacto por familia es despreciable salvo en **H2-L, que pierde el 31,7 % de sus positivos** y se queda con 99 — esa familia no da para nada.

**Prevalencia por familia**, de mayor a menor: HLA-B 21,0 % · HLA-A 16,0 % · HLA-C 10,4 % · HLA-DR 7,1 % · H2-K 6,3 % · HLA-DP 5,6 % · HLA-DQ 5,1 % · H2-D 4,1 % · H2-IA 2,8 % · H2-IE 2,2 % · H2-L 2,2 %.

### 3.3. Cobertura estructural: tope alcanzado (`nap_cnb_v2_structure_completion`)

La cobertura se queda en **99,834 %** y no sube más. Las **159 proteínas pendientes** (81.601 ventanas) contienen residuos que **ProteinUnet rechaza antes de inferir**. Se ejecutaron 0 predicciones nuevas y hubo 0 errores: son incompatibilidades de alfabeto detectadas estáticamente, no fallos. **No es un problema que se pueda resolver insistiendo.**

### 3.4. D1 y las particiones (`nap_cnb_v2_dataset_views`, `nap_cnb_v2_protein_split`)

D1 es la vista deduplicada por la pareja **(secuencia, estructura secundaria)**, sin aumento. De 49,1 M de ventanas quedan **15.100.592 observaciones**. Semilla 42, partición `primary-blake2b-mod10-v1`.

**Partición por componentes de proteína** — la que elimina la fuga por homología:

| | Componentes | Filas | Prevalencia |
|---|---:|---:|---:|
| TRAIN | 13.105 | 12.079.478 | 25,758 % |
| VALIDATION | 1.504 | 1.510.799 | 24,151 % |
| TEST | 1.701 | 1.510.315 | 24,385 % |

Construida sobre 28.872 accessions de UniProt agrupadas en **16.349 componentes conexos** mediante 12.523 fusiones por homología; 8.265 son componentes de una sola proteína.

---

## 4. Las representaciones

### 4.1. ProtT5 (`nap_cnb_v2_prott5`) — validado

| | |
|---|---:|
| Embeddings generados | **14.530.324** |
| Ventanas cubiertas | 49.123.503 |
| Dimensión | 1.024 (float32) |
| Shards | 146 |
| Tamaño | 59.516.225.792 bytes (**59,5 GB**) |
| Tiempo de generación | 7,054 h |
| Ritmo | 572,17 secuencias/s |
| GPU | 1 × RTX 3090 |
| VRAM pico | 2,76 GiB |

Checkpoint Rostlab `94a6abc029ae…`, lote 256, inferencia FP16 y media FP32. La reapertura verificó forma, tipo, finitud y digest de **todas** las filas con **cero inferencias nuevas**, y el inventario pasó recuento, unicidad y SHA-256 **sin colisiones**.

### 4.2. SecondaryBERT (`nap_cnb_v2_secondarybert`) — validado

| | |
|---|---:|
| Estructuras C/H/E únicas | **1.847.436** |
| Ventanas cubiertas | 49.123.503 |
| Dimensión | 768 (float32) |
| Reutilizadas del histórico | 1.819.032 |
| Generadas nuevas | 27.404 (en 13,99 s) |
| Pendientes | **0** |
| Índice SQLite | 416.288.768 bytes |

Modelo `BertForMaskedLM`, 12 capas, 12 cabezas, dimensión 768. **La compatibilidad con el histórico quedó demostrada**: 264 comparaciones sobre las once fuentes dieron **diferencia máxima 0, RMSE máximo 0 y coseno mínimo 1** — es decir, coincidencia bit a bit.

> **El bloqueo de compatibilidad de embeddings que figuraba como problema crítico quedó resuelto.** No hay corrupción. El techo de 0,68 no se explica por ahí.

---

## 5. La línea BLOSUM62 (D2): por qué está parada

Piloto sobre H2-L (`nap_cnb_v2_blosum_materialized`): **89.179 variantes** a partir de **3.569 observaciones de TRAIN**. Se retiraron 46 filas por fuga a VALIDATION/TEST y 550 copias duplicadas.

Dos resultados que desaconsejan continuar:

1. **La etiqueta heredada no es fiable.** La etiqueta de la fuente histórica **difiere de la heredada en 51.717 filas** — el 58 % de las variantes. Heredar la clase del padre es una hipótesis, y en más de la mitad de los casos contradice lo que decía el dato original.
2. **Los embeddings históricos no son los certificados.** De 3.569 padres comparados, **coincidieron bit a bit 0**. Distancia L2 mediana 0,00178512 (rango 0,00110911–0,0537279). Es una diferencia pequeña, compatible con otra precisión numérica, pero **impide mezclar históricos y certificados sin resolver la procedencia del encoder**.

**Estado de los experimentos** (`experiment_status.json`): E1 ✅ ejecutado · E2 ✅ ejecutado · **E3 ❌ no ejecutado** · **E4 ❌ no ejecutado**.

> El método publicado **nunca materializó variantes a disco**: aplicaba BLOSUM62 *on-batch* durante el entrenamiento y, sobre todo, como **post-proceso en inferencia** (+7,6 % de precisión). Esa es la vía con evidencia de que funciona.

---

## 6. Lo que estos resultados NO permiten afirmar

- **No se ha comparado con NetMHCpan ni MHCflurry.** Sin eso no hay afirmación de competitividad posible.
- **No hay validación experimental** de estas predicciones.
- **No se ha probado el alelo como entrada.** El pipeline colapsa 276 alelos en 11 etiquetas de familia, y eso no se ha corregido en ningún experimento de esta tabla.
- **Las métricas antiguas de 0,99999 y 0,7955 no aparecen aquí a propósito**: la primera es un artefacto de partición por fila y la segunda tiene fuga en el 99,70 % de los grupos. No deben citarse.

---

## 7. Qué hay en cada directorio

| Directorio | Qué contiene | Tamaño |
|---|---|---:|
| `nap_cnb_v2_d1_materialized` | **Matrices de características de D1** (ProtT5 + SecondaryBERT concatenados, float32) | **100 GB** |
| `nap_cnb_v2_prott5` | **Los 146 shards de embeddings ProtT5** | **57 GB** |
| `nap_cnb_v2_training` | Resultados de E1, E2 y la ablación por modalidad | 3,5 GB |
| `nap_cnb_v2_phase1` | Construcción de ventanas y estructura secundaria | 1,7 GB |
| `nap_cnb_v2_dataset_views` | Vista D1 y asignación de particiones | 852 MB |
| `nap_cnb_v2_blosum_preparation` | Recuperación e inventario del histórico BLOSUM | 561 MB |
| `nap_cnb_v2_blosum_materialized` | Piloto H2-L de variantes | 481 MB |
| `nap_cnb_v2_protein_split` | Partición por componentes y sus dos modelos | 333 MB |
| `nap_cnb_v2_d1_experimental` | Catálogo SQLite de D1 y estado de experimentos | 289 MB |
| `nap_cnb_v2_secondarybert` | Índice SQLite de SecondaryBERT | 273 MB |
| `nap_cnb_v2_d1_original_manifest` | Manifiesto certificado de D1 | 189 MB |
| `nap_cnb_v2_phase1_structure` | Detalle de huecos estructurales | 26 MB |
| `_informes_archivados_20261124.tar.zst` | Los 5 directorios de informe ya volcados en este documento | 524 KB |

> ⚠️ **Los dos primeros, 157 de los 165 GB, NO son informes de auditoría: son los datos generados.** Borrarlos destruiría 7 horas de GPU (ProtT5) y la materialización completa de D1, y obligaría a regenerarlos antes de cualquier entrenamiento nuevo.

### Limpieza del 24 nov 2026

Se pasó de **18.293 ficheros a 5.756**:

- **Borrada `phase1/reference_cache/`**: 12.361 ficheros, 202 MB. Era una caché regenerable y suponía el 68 % de todos los ficheros.
- **Borrados y archivados** `nap_cnb_v2_phase1_pilot`, `_structure_recovery`, `_structure_completion`, `_final_selection` y `_d1_representations`. Sus números están en este documento y sus manifiestos y recibos SHA-256 quedan en `_informes_archivados_20261124.tar.zst` (524 KB), para no perder procedencia.

```sh
# recuperar un informe archivado
tar -xf <(zstd -dc results/_informes_archivados_20261124.tar.zst) -C /donde/sea
```

**Se conservó todo lo demás**: los 157 GB de datos, las métricas de entrenamiento, los manifiestos certificados y la línea BLOSUM, que es la evidencia de por qué se descartó D2.

---

## 8. Hacia dónde apuntan estos números

1. **Reproducir Wert2021 como brazo de control** (one-hot, 12-mer, biLSTM, solo H-2Kb, prevalencia natural). Sin ese anclaje no se puede defender ninguna mejora.
2. **Cerrar la línea de estructura secundaria y publicarla como resultado negativo.** La ablación de la sección 1 lo demuestra limpiamente, y hay tres TFG/TFM previos que convergen en lo mismo.
3. **Meter el alelo en la entrada** como pseudosecuencia.
4. **Pasar de ventana de 25 aa a péptido de 8–11 aa**, que es la unidad biológica real.
5. **No ejecutar D2.**
6. **Aplicar el post-proceso BLOSUM62 en inferencia**, que es el único uso de BLOSUM62 con evidencia publicada de que funciona.
