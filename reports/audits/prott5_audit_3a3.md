# NAP-CNB v2 · fase 3A.3 de procedencia ProtT5

El catálogo canónico contiene **14.503 bloques de 11 fuentes, una por familia**. Se identificaron **12 series probables** que reúnen **13.399 bloques (92,388 %)** y **1 estrato sin procedencia resuelta**, H2-D, con **1.104 bloques**. Se acreditaron **0 grupos de procedencia común**, **0 ejecuciones identificables de los bloques de junio** y **0 configuraciones efectivas vinculadas por recibo a sus salidas**. El número real de ejecuciones sigue indeterminado. Las series permiten organizar un muestreo. La evidencia actual es insuficiente para certificar reutilización por grupo.

## Reconstrucción documental

- El Git de respaldo conserva un log de HLA-A retirado en abril por `8f400fe`. El proceso falló al importar NumPy. El log demuestra un intento y una ruta anterior, con un resultado anterior a los archivos de junio. Registro estructurado (`prott5_provenance_evidence.json`, artefacto retirado)
- El commit `8226263` del 14 de mayo registró chunks, deduplicación y media sobre tokens activos, con encoder Rostlab. `a16f051` del 27 de mayo reorganizó el generador y conservó lote 32, límite 30 y media mediante máscara. `ee001fb` del 10 de junio añadió la entrada por CLI, metadatos de proteína y un NPY auxiliar. El cambio de noviembre `57628ce` documentado en 3A ajustó rutas en el generador actual. El respaldo permite distinguir versiones de código. Las matrices carecen de una relación verificable con un commit de ejecución. [Código actual](../../data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py)
- La interfaz de junio y el código actual procesan un CSV por invocación. El modelo se carga una vez y se emiten consecutivamente bloques de hasta 100.000 filas. Dentro de cada bloque se deduplican entradas limpias para inferir y se expanden según el índice de filas. Se escriben el NPY y los identificadores, CSV y entradas de índice. El código omite matrices existentes y elimina el índice maestro al arrancar. Esto permite conservar vectores anteriores al reanudar con otro entorno. El índice maestro posterior puede recopilar direcciones de varios periodos.
- La huella de esquema de las salidas indica el generador con identificador de proteína o un procedimiento equivalente. Los 14.503 recibos encajan con archivos de 1.024 float32 si se descuenta la cabecera NPY observada de 128 bytes. Los encabezados CSV de todos los bloques contienen el identificador de proteína. Los tres primeros bloques HLA-A/B/C tienen recibos del 9 de junio, antes del commit del 10. En esos puntos, los recibos de sus NPY auxiliares e índices se sitúan a menos de un segundo del vector. Es compatible con código local adelantado a Git u otro flujo de escritura. La fecha del commit por sí sola carece de poder para identificar con certeza el código ejecutado.
- El modelo del código es `Rostlab/prot_t5_xl_half_uniref50-enc`, con `T5Tokenizer` sin minúsculas automáticas, limpieza de residuos raros, espacios, límite 30 y media con máscara que incluye EOS. La ruta CUDA usa FP16 y la salida float32, con CPU FP32 como alternativa. Se desconoce la rama efectivamente ejecutada, revisión de pesos, hash de tokenizador, versiones de librerías, dispositivo y backend efectivos por bloque. La revisión pública `94a6abc029ae13029317b140b7424e012bf8dfbf` y sus hashes pertenecen al protocolo de validación. [Fase 3A](prott5_audit_3a.md)
- El manifiesto de barajado referencia las once fuentes originales. Los 14.499 chunks concatenados son salidas derivadas de 1.792 dimensiones que conservan referencias y datos float32, con `normalized=false`. Por tanto, se inventariaron los 14.503 bloques originales como entidades primarias. [Manifiesto de derivados](../../data/data_input_nn_shuffled_concatenate/reorder_manifest.json)

## Cronología y grupos

Los recibos de archivo conservan las marcas de modificación de origen. Las fechas describen escritura o copia del archivo. Los 14.503 SHA-256 originales consignados son distintos. Esto descarta bloques completos idénticos en el catálogo por huella, mientras que la redundancia por fila sigue existiendo. La secuencia de identificadores es contigua en cada familia.

Se separaron las secuencias cronológicas en pausas de más de una hora. HLA-C tiene una pausa de **24 h 19 min 46 s** entre 1930 y 1931. HLA-DR tiene una de **20 h 23 min 30 s** entre 408 y 409. H2-D tiene **18 inversiones** y se dejó sin asignar a una ejecución ni configuración común. En las comprobaciones puntuales, los recibos de los auxiliares acompañan las inversiones. La causa podría ser generación paralela, escrituras posteriores o copias. Los índices maestros de HLA-C, HLA-DR y H2-D conservan marcas del 22 de septiembre, meses después de sus vectores. Todos los índices maestros consultados empiezan en chunk 0. Esto acredita diferencias de cronología del índice y el vector, con reanudación o reconstrucción entre las hipótesis. No se vinculó ningún salto temporal con un cambio concreto de modelo o precisión.

## Cobertura de las series

La pasada de metadatos leyó **3.219 GB** comprimidos y reconcilió **1.449.852.950 filas** y todas las multiplicidades por clave de la auditoría anterior. El cálculo por grupo usa la unión de claves primarias exactas. Los recuentos de ventanas ponderan cada clave por su número de apariciones v2. Las filas de la tabla pueden solaparse entre sí.

| Serie o estrato | Nivel | Bloques | Periodo del archivo | Claves v2 potenciales | Ventanas potenciales | Bloques con 3A o 3A.2 | Fallos 3A.2 |
|---|---|---:|---|---:|---:|---:|---:|
| HLA-A-period-1 | probable | 2.656 | 2026-06-09 a 2026-06-17 | 9.393.089 | 40.513.092 | 6 | 0 |
| HLA-B-period-1 | probable | 2.767 | 2026-06-09 a 2026-06-17 | 9.395.159 | 40.523.758 | 6 | 0 |
| HLA-C-period-1 | probable | 1.931 | 2026-06-09 a 2026-06-15 | 7.360.957 | 34.266.313 | 4 | 0 |
| HLA-C-period-2 | probable | 94 | 2026-06-16 a 2026-06-16 | 370.287 | 1.824.835 | 0 | 0 |
| HLA-DP-period-1 | probable | 1.308 | 2026-06-18 a 2026-06-22 | 4.606.784 | 24.586.530 | 4 | 0 |
| HLA-DQ-period-1 | probable | 622 | 2026-06-23 a 2026-06-25 | 2.257.811 | 13.301.609 | 4 | 1 |
| HLA-DR-period-1 | probable | 409 | 2026-06-16 a 2026-06-17 | 1.232.238 | 6.279.727 | 2 | 0 |
| HLA-DR-period-2 | probable | 1.564 | 2026-06-18 a 2026-06-22 | 5.367.814 | 25.935.147 | 2 | 3 |
| H2-D-unresolved | unknown | 1.104 | 2026-06-19 a 2026-06-25 | 3.874.247 | 13.806.301 | 4 | 0 |
| H2-K-period-1 | probable | 1.566 | 2026-06-10 a 2026-06-15 | 5.792.734 | 18.541.569 | 6 | 0 |
| H2-L-period-1 | probable | 2 | 2026-06-30 a 2026-06-30 | 4.727 | 39.546 | 2 | 0 |
| H2-IA-period-1 | probable | 466 | 2026-06-25 a 2026-06-26 | 1.741.052 | 6.886.102 | 4 | 0 |
| H2-IE-period-1 | probable | 14 | 2026-06-30 a 2026-06-30 | 56.182 | 305.930 | 4 | 0 |

La unión de las series probables cubre **14.079.212 de 14.260.167 claves candidatas (98,731 %)** y **48.538.951 ventanas**. El estrato H2-D aporta **180.955 claves** y **196.618 ventanas** exclusivas. En conjunto son 14.260.167 claves y 48.735.569 ventanas. La cobertura por procedencia común demostrada y por reutilización certificada es **0**.

La evidencia experimental existente abarca **644 comparaciones** en **48 bloques distintos**. Dentro de v2, corresponde a **641 claves** con **3.778 apariciones**. La frecuencia de una clave mide cuántas ventanas se beneficiarían de resolver esa entrada; cada comparación se hizo con una dirección histórica concreta.

## Cuatro fallos

Las cuatro entradas son secuencias de 25 aminoácidos estándar y su entrada limpia coincide con la primaria cruda. Se mantuvieron como D **HLA-DQ/31, HLA-DR/876 y HLA-DR/1350**. Los tres están dentro de sus series sin pausa local larga. Sus vecinos inmediatos siguen en C y se conservaron sin reasignarlos por proximidad. Las asociaciones fueron verificadas en 3A.2. El diagnóstico actual compara un vector histórico alternativo por clave y reutiliza las métricas archivadas del piloto, cuyos vectores inferidos no se guardaron.

| Bloque y fila | Clave | Candidatos históricos | Alternativa histórica | ¿Históricos idénticos? | L2 relativa 3A.2 FP16 → FP32 |
|---|---|---:|---|---|---:|
| HLA-DQ/31/22158 | `GQLALNLSSIILDVNQDRLTQRAIE` | 6 | HLA-A/179/35944 (C) | Sí | 1,213 % → 1,493 % |
| HLA-DR/876/41398 | `KMPLKSIAESRILPLMTIGMHLSQA` | 5 | HLA-A/1037/10750 (C) | Sí | 0,754 % → 0,169 % |
| HLA-DR/876/58506 | `VKIRNKVFGLQGVSRGMYDGPVYEV` | 4 | HLA-A/1037/34046 (C) | Sí | 0,459 % → 0,075 % |
| HLA-DR/1350/14984 | `SFKGHINEKNFVGLASNGDYIACGS` | 6 | HLA-A/1747/94256 (C) | Sí | 1,606 % → 2,329 % |

Los controles de precisión anteriores rescataron dos casos en FP32 y empeoraron otros dos. En la comparación histórica se encontraron **4 alternativas idénticas de cuatro**. Para esas filas, una coincidencia exacta en otro bloque debilita la hipótesis de una corrupción aislada de la fila, sin identificar el backend de generación. Se mantienen abiertas varias hipótesis, como diferencias de librería o kernels, procedencia compartida entre copias y configuraciones sin registrar. La evidencia disponible carece de un vínculo que señale un cambio de modelo, tokenizador o pooling como causa. La lectura dirigida fue de **1.533 GB** en **6** matrices. Las cuatro direcciones alternativas de HLA-A quedan señaladas individualmente. Al almacenar el mismo vector, presentan la misma discrepancia FP16 que la fila D para esa clave. Los bloques HLA-A siguen en C y requieren evidencia adicional. Investigación por fila (`prott5_failure_investigation.tsv`, artefacto retirado)

## Viabilidad y recomendación

La validación por grupos solo sustituiría al criterio por bloque si se demuestra la procedencia y se define qué riesgo de bloques atípicos se acepta. Con el Wilson de 3A.2 hacen falta **73 aciertos por unidad**. La validación individual nominal de los 14.503 bloques sumaría **1.058.719 comparaciones** y leería unos **3.589 TB**. Mientras se mantienen los tres D apartados, los otros 14.500 requieren **1.058.500** nominales. El [plan para 3A.4](prott5_audit_3a4_estrategia.md) cuantifica las alternativas, sus riesgos y propone una etapa acotada de 160 comparaciones.

Usar las doce series probables para estratificar el muestreo y perseguir evidencia documental por lote. Mantener H2-D sin atribución común y los tres D identificados. La cobertura potencial es alta y justifica ampliar la evidencia antes de considerar una regeneración general. La fase 3A.4 queda pendiente de revisión.

Inventario de bloques (`prott5_block_provenance.tsv`, artefacto retirado) · Resumen de procedencia (`prott5_provenance_groups.tsv`, artefacto retirado) · Evidencias y uniones exactas (`prott5_provenance_evidence.json`, artefacto retirado) · [Estrategia y costes](prott5_audit_3a4_estrategia.md)

La fase de auditoría se ejecutó en lectura sobre los archivos históricos y v2. Los productos guardan descripciones, hashes y recuentos.

Para reproducir desde la raíz, ejecutar `inventory.py`, compilar `coverage_scan.cpp` con C++17, hilos y libzstd, y ejecutar el binario con `/tmp/nap_prott5_3a3 8`. Después ejecutar `investigate.py` y `publish.py` en el entorno con NumPy, pandas y PyArrow, con la raíz del repositorio en `PYTHONPATH`. Las rutas de entradas y de Git se fijan en los scripts. La cobertura se contrasta clave por clave con los recuentos previos. Las matrices puntuales se usaron en memoria y se ejecutaron **0 inferencias**.
