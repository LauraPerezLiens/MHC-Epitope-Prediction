# PIPELINE — cómo se construye el dataset y cómo se ejecuta

Refunde `nap_cnb_v2_dataset_organization.md`, `nap_cnb_v2_prott5.md`, `nap_cnb_v2_secondarybert.md`, `nap_cnb_v2_consistencia_estructural.md`, `NAP_CNB_v2_BLOSUM62_storage.md`, `NAP_CNB_v2_BLOSUM62_D2.md` y `nap_cnb_v2_organizacion.md`.

> Para las decisiones vigentes y lo que está en revisión, **[`CLAUDE.md`](../CLAUDE.md) manda sobre este documento.** En particular, §0.6 corrige la procedencia IEDB y §0.4–0.5 cuestionan varias decisiones de diseño descritas aquí.

---

## 1. De IEDB a ventanas

**Fuente.** Exportaciones MHC y T-cell de IEDB para once familias: HLA-A/B/C, HLA-DP/DQ/DR, H2-D/K/L, H2-IA/IE. Las proteínas madre se descargan de UniProt.

> ⚠️ Los filtros exactos de esa descarga **no estaban documentados** y se certificaron el 24 nov 2026 leyendo el código. Están en CLAUDE.md §0.6.3, hallazgo I. Dos que importan: solo se descargaban ensayos `*Positive*` (ningún negativo experimental) y solo epítopos de la propia especie. El script nuevo, `build_iedb_dataset_v2.py`, cambia ambas cosas.

**Unidad de entrada.** Una ventana de **25 aminoácidos**. Una ventana es positiva cuando contiene íntegramente un epítopo verificado; la intersección parcial no basta. El intervalo de inicios positivos es `max(1, epitope_end - 24) .. min(epitope_start, protein_length - 24)`.

**Identidad.** `group_id` identifica la ventana original dentro de un fichero de clasificación y `protein_group_id` la proteína dentro de ese mismo fichero. **Los dos se reinician entre ficheros**, así que un entero suelto no identifica nada: cualquier unión externa necesita el fichero de origen o la entrada del manifiesto.

**Resultado (fase 1):**

| | |
|---|---:|
| Proteínas elegibles | 78.620 |
| Ventanas generadas | 49.486.659 |
| **Ventanas binarias** | **49.205.104** |
| Positivas | 5.594.529 |
| Negativas operativas | 43.610.575 |
| Primarias únicas | 14.554.919 |
| Holdouts (péptidos modificados) | 281.555 |

> **«Negativa operativa» no significa negativa experimental.** Significa que esa ventana no tiene anotación positiva. Es una tarea *positive-unlabeled*; tratarla como negativa es una decisión operativa, no un hecho medido.

---

## 2. Estructura secundaria C/H/E

**Predictor.** UNet-C Ensemble (en documentación antigua, *ProteinUnet*), TensorFlow/Keras. Procesa la proteína completa en segmentos con relleno de hasta 1.024 residuos; para proteínas más largas usa solape, descarta márgenes internos, promedia probabilidades y asigna el estado de máxima probabilidad por residuo. El recorte aplica `i = window_start - 1` y `[i:i+25]`, y comprueba longitud, rango y coincidencia exacta con los 25 aa esperados.

**Cobertura: 99,834 %, y es el techo.** Las 159 proteínas pendientes (81.601 ventanas) contienen residuos que el predictor **rechaza antes de inferir**. Se ejecutaron 0 predicciones nuevas y hubo 0 errores: son incompatibilidades de alfabeto, no fallos. Insistir no las resuelve.

**Selección definitiva** — solo ventanas con C/H/E verificada:

| | Dataset binario | Selección definitiva |
|---|---:|---:|
| Ventanas | 49.205.104 | **49.123.503** |
| Positivas | 5.594.529 | 5.587.074 |
| Negativas operativas | 43.610.575 | 43.536.429 |
| Prevalencia | 11,370 % | **11,374 %** |

El impacto por familia es despreciable salvo en **H2-L, que pierde 46 de sus 145 positivos (31,7 %)** y se queda con 99. Esa familia no sostiene ningún análisis.

**Consistencia verificada.** En los seis casos de secuencia primaria con más de una entrada estructural: 0 inconsistencias en 15 apariciones y 12 loci. Las 11 comparaciones con SecondaryBERT distinto tienen exactamente un estado C/H/E distinto; las 4 con la misma entrada y configuración dan vectores idénticos, diferencia máxima 0. **Las diferencias de vector siempre van acompañadas de un cambio real en la entrada.**

---

## 3. Representaciones

### 3.1 ProtT5 — 1.024 dimensiones por primaria exacta

Modelo `Rostlab/prot_t5_xl_half_uniref50-enc`, revisión `94a6abc029ae13029317b140b7424e012bf8dfbf`, copia local en `model/prott5/`.

**Configuración fijada.** Los 25 caracteres originales se conservan; U, B y Z se convierten a X y X sigue X; el resto de caracteres fuera del alfabeto se rechaza. Residuos separados por espacios. SentencePiece genera 25 tokens de residuo más EOS, todos activos: **26 posiciones activas por fila, sin padding**. El último estado oculto del encoder se promedia en float32 **con EOS incluido**. Cálculo en FP16, vectores en float32. Atención eager, algoritmos deterministas, TF32 deshabilitado. Lote medido óptimo: **256**.

**Resultado certificado:**

| | |
|---|---:|
| Embeddings | **14.530.324** |
| Shards NPY | 146 (100.000 filas cada uno) |
| Tamaño | 59.516.225.792 bytes |
| Tiempo | 7,054 h |
| Ritmo | 572,17 secuencias/s |
| GPU | 1 × RTX 3090, VRAM pico 2,76 GiB |

La reapertura verificó forma, tipo, finitud y digest de **todas** las filas con **cero inferencias nuevas**; el inventario pasó recuento, unicidad y SHA-256 **sin colisiones**.

```bash
PY=python; M=data_pipeline.scripts.embeddings.primary_structure.prott5_v2
CKPT=model/prott5/94a6abc029ae13029317b140b7424e012bf8dfbf
export PYTHONPATH="$PWD/.venv/prott5-v2-deps:."; export CUDA_VISIBLE_DEVICES=2

"$PY" -m "$M" inventory                       # claves, longitudes, hashes; sin cargar el modelo
"$PY" -m "$M" full --checkpoint "$CKPT" --output results/nap_cnb_v2_prott5/final --batch-size 256
"$PY" -m "$M" progress --output results/nap_cnb_v2_prott5/final   # SQLite de solo lectura
"$PY" -m "$M" verify   --output results/nap_cnb_v2_prott5/final   # con el escritor detenido
"$PY" -m "$M" locate --sequence MMKFKPNQTRTYDREGFKKRAACLC
```

Cada lote se valida, se sincroniza y se confirma en una transacción SQLite con un SHA-256 que vincula claves ordenadas y bytes. **Un corte entre inferencia y confirmación puede repetir como mucho un lote.** Se necesita un único escritor por almacén. Reanudar es relanzar el mismo comando.

### 3.2 SecondaryBERT — 768 dimensiones por cadena C/H/E exacta

`BertForMaskedLM` de 12 capas, 12 cabezas y dimensión oculta 768, en `model/secondary_bert`. Se usa el encoder y se promedian las posiciones biológicas de su última capa. Cada cadena produce 27 tokens: `CLS=2, C=5, H=6, E=7, SEP=3`. Autocast FP16 en CUDA, salida float32.

| | |
|---|---:|
| Estructuras C/H/E únicas | **1.847.436** |
| Ventanas cubiertas | 49.123.503 |
| Reutilizadas del histórico | 1.819.032 |
| Generadas nuevas | 27.404 (en 13,99 s) |
| Pendientes | **0** |
| Índice SQLite | 416.288.768 bytes |

**La compatibilidad con el histórico está demostrada**: 264 comparaciones sobre las once fuentes dieron **diferencia máxima 0, RMSE máximo 0 y coseno mínimo 1**, es decir coincidencia bit a bit, frente a criterios de ≤ 0,01, ≤ 0,002 y ≥ 0,99999. Huella del modelo: `7714351fc71dd4c3b929d9835d00bdb7d4869e982b9fb32054e4bf9c3846b72d`.

```bash
python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 index
python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 pilot
python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 generate
```

> **Coste de lectura:** la mediana de leer, descomprimir y verificar un bloque histórico fue **4,73 s**. Es la limitación real para lecturas aleatorias. Un almacén compacto de las 1.819.032 claves históricas ocuparía 5.588.066.304 bytes en float32 y simplificaría el acceso, a costa de mantener una copia derivada.

### 3.3 Reglas de reutilización

**Compartir un vector exige que la entrada sea idéntica y la configuración también.**

- **ProtT5:** 25 aa exactos, misma limpieza, mismos pesos y tokenizer, mismo pooling y misma política numérica.
- **SecondaryBERT:** los 25 estados C/H/E exactos más la huella de pesos, tokenizer, mapa de tokens y pooling. **Compartir por 25 aa no vale**: la misma primaria puede tener estructuras distintas en proteínas distintas.
- Ante vectores distintos para entradas idénticas: comprobar configuración y **conservar las representaciones separadas mientras la diferencia no se explique**.

---

## 4. Vistas, D1 y particiones

| Vista | Filas | Etiqueta |
|---|---:|---|
| Selección definitiva | 49.123.503 | por familia y ventana |
| Base v2 | 49.022.360 | `label_original` |
| Índice global | 14.530.324 | `label_global` por primaria |
| **D1** | **15.100.592** | `label_global`, clave `(secuencia, estructura)` |

`label_original` describe la evidencia verificada en el contexto familiar de una ventana. `label_global` es el **máximo** de las etiquetas originales observadas para una primaria exacta: responde a «existe evidencia positiva en algún contexto», que es una pregunta distinta.

**Partición de D1:** por **primaria exacta**, semilla 42, versión `primary-blake2b-mod10-v1`. La misma primaria conserva su split aunque cambie su estructura.

| | Filas |
|---|---:|
| TRAIN | 12.083.630 |
| VALIDATION | 1.507.558 |
| TEST | 1.509.404 |

**Partición alternativa por componentes conexos de proteína** (`results/nap_cnb_v2_protein_split/`), que sí elimina la fuga por homología:

| | Componentes | Filas | Prevalencia |
|---|---:|---:|---:|
| TRAIN | 13.105 | 12.079.478 | 25,758 % |
| VALIDATION | 1.504 | 1.510.799 | 24,151 % |
| TEST | 1.701 | 1.510.315 | 24,385 % |

Las 28.872 accessions de UniProt colapsan en **16.349 componentes** tras 12.523 fusiones, porque una misma primaria de 25 aa aparece en varias proteínas. 8.265 son componentes de una sola proteína. **16.349 es el número real de unidades independientes del estudio**, frente a los 49,1 M de ventanas.

> **Lo que la partición de D1 mide y lo que no.** Mide generalización a primarias exactas no vistas. **No acredita independencia por proteína** ni controla homología. Para eso está la partición por componentes.

**Condición de comparabilidad:** cualquier conjunto futuro que se compare con D1 **debe conservar exactamente su VALIDATION y su TEST**, con sus identidades, etiquetas y asignaciones.

---

## 5. Almacenamiento y acceso

| Ruta | Tamaño | Qué es |
|---|---:|---|
| `data/data_input_nn_shuffled_concatenate/` | 9,5 T | Histórico concatenado, float32 × 1.792, 14.499 chunks. Entrada de los entrenadores históricos |
| `data/data_input_nn_shuffled/` | 3,6 T | Histórico barajado, `.zst` + índice maestro |
| `data/data_input_nn/` | 3,4 T | Embeddings originales `.zst`. Raíz de procedencia |
| `results/nap_cnb_v2_d1_materialized/` | 99 G | D1 materializado: NPY + Parquet por bloque |
| `results/nap_cnb_v2_prott5/` | 56 G | Los 146 shards certificados |
| `data/used_data/` | 31 G | Archivos verificados de fuentes, con SHA-256 |

**D1 materializado.** Cada bloque es `NNNN.npy` (matriz C, float32: columnas 0–1023 ProtT5, 1024–1791 SecondaryBERT) más `NNNN.parquet` con `observation_id`, `group_id`, `global_label` y `split`. **La fila 0 del Parquet es la fila 0 de la matriz.** Para trabajar con una partición, seleccionar primero las posiciones en el Parquet y después indexar la matriz. Las características **no están normalizadas**.

```python
np.load(path, mmap_mode="r", allow_pickle=False)
```

**Rendimiento medido** (lector de bloques NPY directo, retirado el 24 nov 2026; caché caliente): secuencial sin caché de aperturas 503 MB/s, con caché de 4 → 1.914 MB/s; aleatorio 722 → 1.316 MB/s. Una apertura con validación cuesta 226 µs. **Para resolver por ID puntual, SQLite gana a Parquet por dos órdenes de magnitud** (7,88 µs frente a 2.312 µs); Parquet sigue siendo mejor para escanear columnas de lotes grandes.

> **Un offset del NPY descomprimido no sirve en Zstandard.** Para `.npy.zst` hay que agrupar por fichero y decodificar secuencialmente. No hay índices de frames seekables.

---

## 6. BLOSUM62 y el estado de D2

**D2 no está construido y la recomendación vigente es no construirlo** (CLAUDE.md §0.5.5).

El corpus histórico declara **55.763.575 grupos y 1.449.852.950 filas**, compatible con 26 filas por grupo (el original más 25 variantes). Una auditoría comprobó 286 filas en 11 grupos: **la aritmética y esa muestra no certifican uniformidad por grupo, ausencia de repeticiones, ni una versión fijada de código, semilla o dependencias.**

**Contrato de etiquetas.** Las variantes conservan la etiqueta de la secuencia original. Una etiqueta heredada **identifica el origen de la anotación y no añade evidencia experimental sobre la variante**.

**Piloto H2-L** (`results/nap_cnb_v2_blosum_materialized/`): 89.179 variantes de 3.569 observaciones TRAIN; se retiraron 46 filas por fuga a VALIDATION/TEST y 550 duplicadas. Dos resultados desaconsejan continuar:

1. **La etiqueta de la fuente histórica difiere de la heredada en 51.717 filas**, el 58 %.
2. **De 3.569 padres comparados, coincidieron bit a bit 0.** Distancia L2 mediana 0,00178512 (rango 0,00110911–0,0537279): diferencia pequeña, compatible con otra precisión numérica, pero **impide mezclar históricos y certificados sin resolver la procedencia del encoder**.

Estado: **E1 ✅ · E2 ✅ · E3 ❌ no ejecutado · E4 ❌ no ejecutado**.

> El método publicado (Wert2021) **nunca materializó variantes a disco**: aplicaba BLOSUM62 *on-batch* durante el entrenamiento y como **post-proceso en inferencia**, con +7,6 % de precisión. Esa es la vía con evidencia.

---

## 7. Verificación

```bash
python -m unittest discover -s tests -t . -v
```

**135 pruebas, todas pasan** (24 nov 2026). Cubren reconstrucción, estructuras, splits, concatenación, ProtT5 v2, SecondaryBERT, archivado y los entrenadores.

> **La CLI de consulta `data_pipeline.nap_cnb_v2` se retiró el 24 nov 2026**, junto con el resto del instrumental de auditoría. Daba estados `CERTIFIED`/`PRESENT`/`MISSING`/`INCONSISTENT` leyendo footers y catálogos, sin recorrer las matrices. Cumplió su función —certificar D1— y el proyecto ha pasado de auditar a corregir. Se recupera del historial de git si vuelve a hacer falta:
>
> ```sh
> git show <commit-anterior>:data_pipeline/nap_cnb_v2.py
> ```

## 8. Reglas que conviene no romper

1. **Fijar la GPU explícitamente** con `CUDA_VISIBLE_DEVICES` y comprobar antes que está libre. Ver las reglas de servidor compartido en CLAUDE.md §0.0.
2. **Un solo escritor por almacén.**
3. **El scaler se ajusta solo con TRAIN**, y cada población tiene el suyo: los scalers histórico, base y D1 **representan poblaciones distintas y no son intercambiables**.
4. **Un puntero físico válido no acredita** correspondencia con D1, unicidad de secuencia, equivalencia entre versiones de embeddings ni identidad estructural de una variante.
5. **Registrar siempre** revisión del modelo, tokenizer, pooling, dtype, semilla y configuración. Sin eso, un vector no es reutilizable.
