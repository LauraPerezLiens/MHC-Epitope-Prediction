# HISTORIAL — qué se ha probado, qué salió y por qué se rehízo

Refunde `NAP_CNB_technical_history.md`, `mlp_experiment_history.md`, `INDICE_EVIDENCIA.md`, `NAP_CNB_v2_training_guide.md`, `NAP_CNB_pipeline_refactoring_plan.md` y `nap_cnb_v2_reutilizacion.md`.

> Los números vigentes están en **[`results/RESULTADOS.md`](../results/RESULTADOS.md)**. Las decisiones abiertas, en **[`CLAUDE.md`](../CLAUDE.md)**.

---

## 1. Qué predice realmente el modelo

La unidad de predicción es una **ventana de 25 residuos** de una proteína madre. La etiqueta positiva indica que la ventana contiene un epítopo con evidencia positiva registrada en el contexto MHC correspondiente.

**Eso no es lo mismo que afinidad, presentación ni inmunogenicidad.** Son cosas distintas y el dataset las mezcla:

- Un **ensayo de unión a MHC** mide la unión péptido-MHC.
- La **identificación de un ligando eluido** da evidencia de presentación bajo las condiciones del ensayo.
- Un **ensayo de respuesta de célula T** mide reconocimiento o respuesta celular.

NAP-CNB combina evidencia de las exportaciones MHC y T-cell en **una sola etiqueta binaria de ventana**. El objetivo es, por tanto, «evidencia registrada de epítopo bajo las reglas del dataset», y **no cuantifica ninguna de las tres propiedades por separado**. Los negativos son operativos: no afirman ausencia verificada de nada.

> Medido el 24 nov 2026: el **98,64 %** de los pares péptido-alelo proviene de elución por espectrometría de masas. Lo que el dataset mide mayoritariamente es **presentación**. Ver CLAUDE.md §0.7.4.

---

## 2. El pipeline histórico y sus trampas

El descargador fusionaba registros de ensayo por texto del péptido, coordenadas e identificadores de fuente. El clasificador descargaba la proteína madre, mapeaba la evidencia y enumeraba ventanas de 25 aa. Para una ventana con varios epítopos candidatos guardaba **un epítopo seleccionado y una puntuación de posición**: un formato compacto que ayudó al entrenamiento y **dejó mucho menos detalle de ensayo disponible para revisar después**.

Tres trampas que conviene recordar:

1. **Los identificadores son locales al fichero.** `group_id` y `protein_group_id` se reinician entre ficheros. Una unión externa por un entero suelto está mal por construcción.
2. **Una primaria compartida entre familias, proteínas o coordenadas puede ser observaciones distintas.** Solo el hash de la proteína completa identifica alias exactos.
3. **El aumento BLOSUM62 heredaba la etiqueta y la estructura del padre.** Una secuencia sintética con la etiqueta del progenitor es una suposición de modelado, no un resultado de ensayo.

**SecondaryBERT** se preentrenó con enmascaramiento sobre estructuras predichas de un corpus derivado de UniRef. Su subconjunto de validación de 100.000 proteínas dio **accuracy de token enmascarado 0,885621 y macro-F1 C/H/E 0,873589**. Eso mide reconstrucción del alfabeto estructural, no utilidad para predecir epítopos.

---

## 3. Los experimentos históricos, y por qué no valen

**Protocolo:** arquitectura 1792 → 512 → 128 → 1, LayerNorm, ReLU, dropout 0,30, BCEWithLogitsLoss, AdamW, lr 0,001, decay 0,0001, batch 8.192 con 4.096 filas por clase, coseno con T0=20, semilla 42, sin early stopping. `STAGE` evalúa sobre el alcance de chunks actual; `ALL` sobre el conjunto completo; ambas con muestras balanceadas fijas.

**Tres defectos de diseño, asumidos entonces como exploratorios:**

1. **Partición por fila**, permitiendo que grupos y proteínas aparezcan en varios splits.
2. **Selección del checkpoint por la pérdida de TEST STAGE**, lo que convierte TEST en población de selección.
3. **Evaluación balanceada al 50/50**, que no es la prevalencia real.

### Qué salió

| Experimento | Resultado observado | Qué lo invalida |
|---|---|---|
| BatchNorm, 10 chunks | Estadísticas en inferencia: loss 1,880200, AUC 0,986282. Diagnóstico con estadísticas de lote: loss 0,050603, AUC 0,998883 | **Dependencia brutal de la normalización en inferencia.** Motivó el cambio a LayerNorm |
| LayerNorm, 10 chunks | TEST época 98: AUC **0,999990**, accuracy 99,9269 % | Subconjunto diminuto, partición por fila, selección en TEST |
| Escalera barajada, 20 chunks | AUC 0,999996 | Igual |
| Doble evaluación, 100 chunks | **STAGE AUC 0,999086 · ALL AUC 0,585285**, con los mismos pesos | **El mismo checkpoint pasa de 0,999 a 0,585 solo cambiando el alcance de evaluación** |
| MLP directo, 14.503 bloques | Época 1: AUC 0,665027 | Una sola época |
| Barajado global, 10/50/100 chunks | STAGE AUC 0,704909 / 0,744102 / 0,749762 | Presupuestos de épocas distintos; no comparables entre sí |
| LR balanceada, histórica | TEST ALL AUC **0,6962** (época 1) | Mismo protocolo defectuoso |
| MLP histórica, 14.499 chunks | TEST **0,795539** (época 1) | **99,70 % de los grupos en varias particiones, 87,38 % en las tres** |

### La lección

**El contraste entre STAGE 0,999086 y ALL 0,585285 con los mismos pesos es el resultado más informativo de toda la línea histórica.** Demuestra que aquellas cifras describían la muestra de evaluación, no la capacidad del modelo.

La auditoría de grupos midió **55.595.967 de 55.763.575 grupos en varias particiones, y 48.726.754 en las tres**. Con eso, el 0,7955 no estima generalización: mide fuga.

> **Ninguna métrica de esta sección debe citarse como generalización.** Se conservan porque documentan por qué se rehízo todo.

---

## 4. Por qué se pasó a v2

### 4.1 La evaluación no significaba nada

Un buen resultado sobre una muestra local con partición por fila **no dice nada sobre el comportamiento en una cohorte independiente por proteína**. La respuesta de v2 fue una partición compartida por **identidad primaria exacta** con comprobación de procedencia. Eso elimina el solape exacto de primaria y de representación. **El solape por proteína y por coordenadas siguen siendo limitaciones medidas aparte** — y de ahí la partición por componentes.

### 4.2 Las etiquetas se contradicen

La auditoría encontró **3.494.284 primarias distintas con ambas etiquetas**, de 15.135.904 secuencias únicas sobre 55.763.575 filas originales. Un modelo que solo ve la secuencia y su estructura se topa con etiquetas opuestas para observaciones idénticas.

Parte de esa heterogeneidad **puede ser biológicamente legítima** —especificidad de MHC, proteína de origen, evidencia distinta—, pero eso no elimina la ambigüedad para representaciones exactas que llevan las dos etiquetas.

La decisión fue **reconstruir evidencia y etiquetas desde registros validados con su traza, en lugar de editar filas históricas en disputa**. La reconstrucción conserva las etiquetas por familia y añade la agregación global como vista separada: dos preguntas científicas, un solo registro de procedencia.

### 4.3 Los embeddings no eran reutilizables

La auditoría encontró candidatos históricos exactos para 14.260.167 claves, pero **una clave coincidente no acredita un vector compatible**. Las pruebas numéricas ampliadas dieron cuatro fallos; dos mejoraron con diagnóstico FP32 y dos empeoraron. El direccionamiento era correcto y **la causa quedó sin determinar**. → **Regeneración completa de ProtT5 bajo protocolo fijado.**

Para SecondaryBERT la evidencia fue más fuerte: mapeo documentado, dimensión, acuerdo numérico entre candidatos repetidos y huella de configuración. → **Conservar las direcciones históricas certificadas y generar solo las claves que faltaban.** Los `chunks_pooled/` antiguos quedaron fuera de la reutilización certificada.

---

## 5. Los resultados que sí valen

TEST puntuado una vez, modelo elegido por VALIDATION, prevalencia real conservada:

| Experimento | Partición | ROC-AUC | AP | Prevalencia |
|---|---|---:|---:|---:|
| **E1** · LR | primaria exacta | 0,654641 | 0,375738 | 25,451 % |
| **E2** · MLP | primaria exacta | 0,680107 | 0,412129 | 25,451 % |
| MLP · solo ProtT5 | primaria exacta | **0,682302** | **0,415255** | 25,451 % |
| MLP · solo SecondaryBERT | primaria exacta | 0,601431 | 0,316272 | 25,451 % |
| LR | componentes de proteína | 0,662294 | 0,379399 | 24,385 % |
| MLP | componentes de proteína | 0,674668 | 0,395093 | 24,385 % |

Tres lecturas, desarrolladas en [`results/RESULTADOS.md`](../results/RESULTADOS.md):

1. **Es generalización real.** Eliminar toda la fuga por homología cuesta 0,0054.
2. **SecondaryBERT resta.** Solo ProtT5 (0,682302) supera a ProtT5 + SecondaryBERT (0,680107).
3. **El techo no es el modelo.** Entre lineal y red hay 0,0255.

**Y con el protocolo contaminado el MLP aparentaba +0,0987 sobre la LR, frente a +0,0255 con partición limpia: alrededor del 74 % de su ventaja aparente era fuga.** La capacidad extra se gastaba en memorizar grupos compartidos, algo que un modelo lineal no puede hacer. (Los dos protocolos difieren también en balanceo y datos aumentados, así que es una magnitud consistente, no una descomposición causal.)

---

## 6. Perfiles de entrenamiento

| Perfil | Script | Modelo y optimización |
|---|---|---|
| `lr_balanced` | `neural_network/logistic_regression/train.py` | Logit lineal 1.792 → 1, BCEWithLogitsLoss, AdamW, lr 0,001, decay 0,0001, batch 8.192 con 50/50 exacto |
| `lr_natural` | `neural_network/logistic_regression/train_natural.py` | Logit lineal, BCE + L2 explícito, Adam. Prevalencia natural. **Sustituido por el balanceado** |
| `mlp_historical` | `neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py` | 1792 → 512 → 128 → 1, LayerNorm, dropout 0,30, coseno T0=20 |

**Matriz de compatibilidad con v2:** LR y MLP sobre datos originales con etiqueta original o global están en `INCOMPLETE` (base y D1 validados, falta el scaler TRAIN de producción). Sobre BLOSUM62 con etiqueta original, `INCOMPATIBLE`: el histórico solo sirve para *replay* con sus propios splits y scaler. Con etiqueta global, **no disponible**: D2 no existe.

> ⚠️ **El motor histórico tiene un defecto que hay que arreglar antes de volver a entrenar.** Su rama de selección por VALIDATION depende de `getattr(args, "v2_checkpoint_contract", None)`, y **ese argumento no existe en el parser**: siempre vale `None`, así que la rama correcta es **inalcanzable** y siempre selecciona por TEST. Además solo importa `roc_auc_score`: **no calcula AP ni PR-AUC**, que es la métrica con la que compara el proyecto. Detalle en CLAUDE.md §0.8.

---

## 7. Deuda técnica

La revisión del pipeline recomendó **reorganización mínima**: mantener los scripts donde están y añadir una interfaz de consulta y validación de solo lectura. Esa interfaz se construyó (`data_pipeline/nap_cnb_v2.py`) y **se retiró el 24 nov 2026 junto con el resto del instrumental de auditoría**, una vez certificado D1: el proyecto pasó de auditar a corregir. Sigue en el historial de git.

**La idea que sigue vigente:** separar tres cosas que aparecen mezcladas en la documentación y en los imports —**construir** artefactos de una fase, **consultar** una entrega certificada y **reproducir** un experimento histórico.

Inventario: **0 grupos de scripts idénticos byte a byte**, pero sí responsabilidades repetidas. Hay normalización de URL en clasificación, FASTA, recorte estructural y rebuild, con tratamientos distintos de esquemas, barras y valores vacíos. `archive_inputs.signature` usa identidad física y tamaño; `rebuild.signature` usa ruta resuelta, tamaño y mtime: **consolidarlas exige preservar ambos contratos**.

Dependencias que impiden retiradas directas:

- `rebuild_iedb/rebuild.py` importa `FAMILIES`, `ROOT`, bloqueo y JSON de `global_epitope_labels/build.py`. **Eliminar ese módulo rompe el constructor.**
- `iedb_modified_audit` importa lógica de `iedb_pending_audit` y de descarga, con tests que comprueban esos contratos.
- `source_audits/investigate_embedding_cases.py` consume `exact_embeddings.OriginalVectors`; `recover_epitope_coordinates` consume `omitted_epitopes`.

**Oportunidades de espacio**, por orden, y ninguna sin migrar antes a sus consumidores:

1. **9,5 TiB** del concatenado histórico. Es dependencia activa de MLP y LR.
2. **Hasta 3,6 TiB** del árbol barajado, conservando índice maestro, manifiestos y checksums.
3. Cachés de evaluación de ~799 MiB en los resultados históricos.

---

## 8. Cronología

| Fecha (2026) | Hito |
|---|---|
| 26 y 28 oct | Compilación del historial MLP; barajado global previo a la generación de splits |
| 10 y 17 nov | Retirada de artefactos experimentales antiguos |
| 16–19 nov | Auditorías de fuentes y de evidencia; informes de reconstrucción |
| 19 nov | **ProtT5 regenerado y certificado**, 7,05 h |
| 20 nov | **SecondaryBERT fase 3C cerrada** |
| 22–23 nov | D1 certificado; piloto BLOSUM H2-L; E1 y E2 ejecutados; ablación por modalidad |
| 23 nov | Partición por componentes de proteína |
| 24 nov | Verificación de procedencia IEDB; revisión del MLP en ejecución; refundición de esta documentación |

> El commit más antiguo del repositorio principal es `9731ea3` (11 nov 2026), **pero el trabajo es anterior**. Varios logs y checkpoints originales ya no están en el árbol, y las cifras de aquellas ejecuciones se conservan reconstruidas desde históricos JSONL archivados.
