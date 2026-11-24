# NAP-CNB v2 · fase 3A de ProtT5

El checkpoint público reprodujo el procedimiento documentado, con diferencias numéricas frente a los 68 vectores de la muestra. La magnitud y la estabilidad de esas diferencias delimitan la evidencia de compatibilidad. Los bloques carecen de una huella de ejecución que permita certificar, solo con este piloto, las 14.260.167 entradas con candidato histórico.

## Modelo, tokenizador y procedencia

El generador registra `Rostlab/prot_t5_xl_half_uniref50-enc` y carga tanto el encoder como `T5Tokenizer` sin fijar revisión. El cambio entre `9731ea3` y `57628ce` ajustó las rutas de los datos. [Generador del repositorio](../../data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py)

El piloto fijó la revisión pública `94a6abc029ae13029317b140b7424e012bf8dfbf`. El archivo público de pesos de 2.416.373.051 bytes se publicó en `e380a83`. La revisión `f94c9e6` fijó la configuración y los archivos del tokenizador. Las revisiones posteriores de la rama principal solo cambiaron el README. Esto sustenta la elección de la copia pública. Los metadatos locales históricos carecen de un identificador de revisión, hashes de pesos y tokenizador o manifiesto de la ejecución que la vincule directamente. [Historial de Rostlab](https://huggingface.co/Rostlab/prot_t5_xl_half_uniref50-enc/commits/main) · [Pesos en revisión fija](https://huggingface.co/Rostlab/prot_t5_xl_half_uniref50-enc/blob/94a6abc029ae13029317b140b7424e012bf8dfbf/pytorch_model.bin) · SHA-256 verificados (`checkpoint_hashes.json`, artefacto retirado)

No se encontró el checkpoint en el directorio de modelos del proyecto, la caché Hugging Face de Pascal, la copia de respaldo del repositorio ni las rutas de caché configuradas en la sesión. Se descargó una sola copia pública en almacenamiento temporal y se cotejó el SHA-256 LFS de los pesos y los identificadores de objeto Git de los archivos auxiliares. Se usó `spiece.model`, con SHA-256 `74da7b4afcde53faa570114b530c726135bdfcdb813dec3abfb27f9d44db7324`.

El código histórico limpia las secuencias, convierte U/Z/O/B y caracteres fuera del alfabeto declarado en X, separa residuos con espacios, activa tokens especiales y aplica padding y truncado a un máximo de 30 tokens. Promedia el último estado oculto según la máscara de atención, que incluye EOS. Usa lotes de 32 entradas limpias por primera aparición dentro de cada bloque. En CUDA carga FP16 y escribe los 1.024 componentes como float32. El código incluye una ruta CPU en FP32. Se desconoce qué versión de PyTorch, Transformers y CUDA se usó efectivamente en cada ejecución histórica y si todos los bloques se generaron en el mismo entorno.

## Piloto y criterios

- Se seleccionaron filas originales con semilla 20261119. Se cubrieron las once familias y se añadieron bloques central y final para HLA-A, HLA-B y H2-K. Es una muestra estratificada dirigida.
- Se verificaron el checksum de cada archivo histórico de vectores, la secuencia primaria exacta y su dirección mediante Parquet, CSV e identificadores físicos del bloque. Se verificaron la forma y el tipo de las matrices, además de la finitud de las filas originales comprobadas en los bloques examinados.
- Cada comparación se ejecutó con el lote de entradas limpias reconstruido a partir de los CSV y la deduplicación del generador. Se ejecutó dos veces para medir repetibilidad en el entorno actual. El criterio de igualdad exacta compara los valores float32 almacenados. Las métricas de diferencia se exponen sin declarar un umbral de aceptación aproximada.
- Transformers 5.17.0 del entorno principal no cargó `spiece.model` mediante la API histórica. El piloto utilizó una instalación temporal de Transformers 4.57.6, SentencePiece 0.2.3 y tokenizers 0.22.2, con PyTorch 2.14.0, CUDA 13.0 y una NVIDIA GeForce RTX 3090 en FP16. Se ejecutó offline después de verificar los archivos públicos.

| Métrica | Resultado |
|---|---:|
| Vectores comparados | 68 |
| Bloques / familias | 17 / 11 |
| Filas con primaria presente en la selección v2 | 65 |
| Coincidencias exactas en toda la muestra | 0 / 68 |
| Coincidencias exactas entre entradas presentes en v2 | 0 / 65 |
| Diferencia absoluta máxima | 0.00085449219 |
| RMSE mediano | 4.0100779e-05 |
| Distancia L2 relativa máxima | 0.0029240324 |
| Similitud coseno mínima | 0.9999957277 |
| Diferencia máxima al repetir el mismo lote | 0 |
| Secuencias tokenizadas comparadas con SentencePiece | 2176 |
| Discrepancias de tokenización | 0 |
| Entradas por pasada / lotes | 2176 / 68 |
| Vectores de la muestra con limpieza aplicada | 0 |
| Lectura de matrices históricas comprimidas | 4.142 GB |
| VRAM pico asignada por PyTorch | 3.097 GiB |

| Familia | Filas | Iguales | Error absoluto máximo |
|---|---:|---:|---:|
| HLA-A | 12 | 0 | 0.00036621094 |
| HLA-B | 12 | 0 | 0.00030517578 |
| HLA-C | 4 | 0 | 0.00030517578 |
| HLA-DP | 4 | 0 | 0.00030660629 |
| HLA-DQ | 4 | 0 | 0.00048828125 |
| HLA-DR | 4 | 0 | 0.00085449219 |
| H2-D | 4 | 0 | 0.00054931641 |
| H2-K | 12 | 0 | 0.00048828125 |
| H2-L | 4 | 0 | 0.00061035156 |
| H2-IA | 4 | 0 | 0.00024414062 |
| H2-IE | 4 | 0 | 0.00024414062 |

El tokenizador del piloto coincidió con SentencePiece en todas las entradas probadas. Los tokens no se guardaron como parte de la generación histórica. La coincidencia del piloto verifica la preparación actual, mientras que el cotejo contra los vectores archivados mide su compatibilidad numérica.

Las marcas de modificación archivadas de los bloques muestreados abarcan del 09/06/2026 al 30/06/2026. Se usan como indicio temporal de los archivos, sin atribuirles una versión de software.

## Control de precisión

Se repitieron cuatro lotes de HLA-A bajo tres configuraciones. Desactivar la reducción FP16 de precisión reducida dejó las métricas idénticas. El control en FP32 con TF32 desactivado redujo el error máximo de esas cuatro filas, aunque tampoco reprodujo exactamente ningún vector histórico.

| Configuración | Coincidencias exactas | Diferencia absoluta máxima | L2 relativa máxima |
|---|---:|---:|---:|
| FP16 por defecto | 0 / 4 | 0,000244141 | 0,124348 % |
| FP16 sin reducción de precisión reducida | 0 / 4 | 0,000244141 | 0,124348 % |
| FP32 en GPU sin TF32 | 0 / 4 | 0,000149071 | 0,074744 % |

Este control muestra sensibilidad a la precisión y deja abierta la causa exacta de la diferencia histórica. Mediciones del control (`precision_control.tsv`, artefacto retirado) · Configuración (`precision_environment.json`, artefacto retirado)

## Decisión de reutilización

La prueba aporta evidencia directa de la salida del checkpoint público para las filas identificadas. Una decisión de reutilización a escala de corpus requiere una garantía del origen por lote o un criterio explícito de compatibilidad empírica, con muestreo ampliado por fecha, familia y bloque y un umbral numérico justificado si se acepta una equivalencia aproximada. Los 270.157 casos sin candidato exacto siguen siendo una categoría aparte. El piloto no cambia la clasificación del corpus en la auditoría anterior.

El TSV conserva la dirección, secuencia, efecto de la limpieza y métricas por fila. Los artefactos guardan metadatos, hashes y comparaciones numéricas. Los vectores experimentales se mantuvieron en memoria. Comparaciones (`pilot_comparisons.tsv`, artefacto retirado) · Resumen reproducible (`pilot_summary.json`, artefacto retirado) · Código del piloto (`pilot.py`, artefacto retirado)
