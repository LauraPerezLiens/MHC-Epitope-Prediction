# Fase 3B · piloto de ProtT5 v2

**Recomendación tras revisión:** lanzar el procesamiento completo con una RTX 3090, lote 256, inferencia FP16 y salida float32. El piloto de 10.000 claves pasó las comprobaciones de integridad, repetición y reanudación. El almacén definitivo queda pendiente de autorización. [Comando preparado](../../docs/PIPELINE.md)

## Entrada y protocolo

Se reutilizó el inventario exacto de la auditoría anterior. Se cotejaron la selección, firmas de archivos y hashes de suplementos. El inventario contiene **14.530.324 primarias distintas** vinculadas a 49.123.503 ventanas. Se comprobaron todos los SHA-256 de clave sin colisiones observadas, y las longitudes y el alfabeto. Todas las primarias v2 usan los 20 símbolos canónicos. Las reglas de U/B/Z/X se comprobaron en el tokenizador con entradas de control, sin incorporar secuencias artificiales al almacén.

El piloto se eligió con semilla 20261119, sin reemplazo. Las 10.000 claves aparecen en la selección final. De ellas, **7,836** se comparten entre familias y tienen **9,998** composiciones distintas. Se observaron los 20 residuos canónicos y una longitud tokenizada fija de 26, con EOS. Los patrones de IDs de residuo varían con la secuencia. La muestra no incluye entradas especiales porque están ausentes del inventario.

Se verificaron los archivos del checkpoint Rostlab `94a6abc029ae13029317b140b7424e012bf8dfbf`, ya disponible de 3A. Se dejó una copia persistente cotejada de 2,417 GB en `model/prott5/`. Esta copia de modelo se contabiliza aparte de los embeddings. El encoder se ejecuta en modo evaluación, con atención eager y algoritmos deterministas. La media se acumula en FP32 sobre los 26 tokens activos, incluido EOS. Es un protocolo nuevo con acumulación explícita, y las mediciones no dependen de los vectores históricos. [Configuración del almacén](pilot/manifest.json)

## Rendimiento medido

Se expuso únicamente la RTX 3090 física 2, con unos 24.112 MiB libres en la inspección. Las GPU 0 y 1 tenían procesos de cómputo registrados. Pascal disponía de unos 170 GiB de RAM disponible y 20 TiB de espacio libre en el volumen del proyecto.

| Batch FP16 | Entradas | Tokenización (s) | Cálculo y transferencia (s) | Entradas/s sin escritura | VRAM pico asignada (GiB) |
|---|---:|---:|---:|---:|---:|
| 32 | 1024 | 0.095 | 1.436 | 669.1 | 2.34 |
| 128 | 1024 | 0.147 | 1.279 | 718.3 | 2.52 |
| 256 | 1024 | 0.107 | 1.234 | 763.1 | 2.76 |

El control emparejado de 128 entradas FP16/FP32 tuvo una diferencia absoluta máxima de 0.00086499 y un error L2 relativo máximo de 0.397 %. Esta comparación cuantifica el cambio de precisión. La calidad de un entrenamiento futuro y el rendimiento completo de FP32 siguen sin medirse. La salida float32 conserva los valores calculados por la receta elegida, incluida la media en FP32.

| Métrica del piloto durable | Resultado |
|---|---:|
| Carga del modelo por sesión | 2.20 / 2.09 s |
| Lectura del inventario por sesión | 1.71 / 1.63 s |
| Tokenización acumulada | 0.848 s |
| Cálculo y transferencia acumulados | 12.920 s |
| Escritura sincronizada y digest, antes del commit | 1.500 s |
| Tiempo de generación y verificación en la reanudación | 27.609 s |
| Ritmo de extremo a extremo en la reanudación | **334.4 secuencias/s** |
| VRAM pico asignada durante el piloto | 2.76 GiB |
| RAM residente pico del proceso durante el piloto | 4.36 GiB |
| Matriz + manifiesto + SQLite del piloto | 41.115 MB |

El ritmo de extremo a extremo incluye indexación de las claves muestreadas, escritura, commits y verificación. El benchmark corto de 763 entradas/s mide tokenización y cómputo, y se conserva como referencia de capacidad. La parte completa usará rangos contiguos, mientras que el piloto seleccionó posiciones dispersas.

## Integridad y reanudación

- La primera sesión se detuvo tras **768** filas confirmadas. La segunda calculó **9.232**, para un total de **10.000** en **40 lotes** sin repetición de los ya confirmados.
- La verificación cotejó dimensiones 1.024, tipo float32, finitud y SHA-256 que vincula claves y vectores en orden para los 10.000 resultados.
- Una nueva ejecución sobre el piloto completo verificó las 10.000 filas e hizo **0 inferencias**. Repetir un lote de 256 en otra sesión produjo valores **idénticos bit a bit**.
- La consulta de ordinal y fila por ID exacto funcionó. Un intento con lote 128 sobre el mismo almacén fue rechazado. Las pruebas sintéticas comprobaron la detección de bytes alterados y la reanudación sin repetir lotes.
- La fase completa está preparada para una GPU. La escritura usa shards y recibos SQLite con sincronización. Un corte previo al commit puede repetir el lote que estaba en vuelo. Se conservan los resultados ya confirmados.

## Extrapolación

A 334.4 secuencias/s, **14.530.324** claves darían **12.07 horas de GPU** en una GPU. Reservar **14.48 h de pared** con 20 % de margen para carga, validación, variaciones de E/S y cortes. Es una extrapolación del piloto. El escalado multi-GPU no se midió y depende de la E/S y los recursos disponibles.

La matriz completa ocuparía **59.516 GB** decimales en float32. Habría 146 shards y recibos compactos en SQLite. La reserva recomendada es **61 GB para el nuevo almacén** con margen para validación y un shard inicial en vuelo de hasta 0,410 GB, además de la copia persistente del modelo que ya se cotejó. Los embeddings por ventana permanecen como uniones lógicas por la primaria exacta. La ruta propuesta es `results/nap_cnb_v2_prott5/final/`.

[Benchmark](benchmark.json) · [Arranque detenido](pilot_first.json) · [Reanudación](pilot_resume.json) · [Repetición](pilot_repeat.json) · [Reapertura](pilot_complete_reopen.json) · [Inventario validado](inventory_validation.json) · [Organización](../../docs/PIPELINE.md)


## Lanzamiento de producción

El 19 de noviembre de 2026 a las 13:41 CET se inició la generación autorizada en `tmux`, sesión `nap-prott5-v2`. Se verificó que el manifiesto completo coincide con la configuración del piloto y que usa el inventario entero. Las cifras anteriores corresponden al piloto. La ejecución de producción registra sus mediciones y verificaciones por separado. [Log principal](full_run.log)
