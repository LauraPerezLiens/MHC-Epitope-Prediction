# ProtT5 · propuesta para 3A.4

La unidad de evidencia determina qué se puede extrapolar. El límite inferior de Wilson bilateral al 95 % para `n/n` es `n/(n+z²)`. Con `z=1,95996` y un límite exigido de 0,95 hacen falta **73 aciertos de 73**. En 3A.2 la regla A exigía además que todas las comparaciones fueran válidas y satisfactorias. Se conservan los umbrales de coseno, L2 relativa y diferencia máxima. Los 12 aleatorios por bloque de 3A.2 daban 75,751 % incluso con todos aprobados.

| Estrategia | Unidades | Comparaciones o inferencias | Lectura histórica | Escenario GPU a 100 entradas/s |
|---|---|---:|---:|---:|
| A · individual, tres D en cuarentena | 14.500 bloques | 1.058.500 comparaciones nominales; 1.058.152 adicionales si esos 348 ensayos aleatorios son elegibles | 3.588 TB | 2.940–94.089 h GPU |
| B · grupos demostrados | 0 grupos demostrados hoy | A sigue siendo el coste de referencia; por cada grupo futuro, 73 sería el mínimo nominal de claves iid y se añade muestreo de bloques | Sin ahorro demostrado | Sin ahorro demostrado |
| C · 12 series probables como unidades, solo hipótesis | 12 series y 1.104 bloques H2-D sin agrupar | 876 comparaciones nominales para las series; 81.468 si además se valida H2-D individualmente | Para las series se debe presupuestar según bloques abiertos; H2-D completo añade 290.174 GB | 876 objetivos requieren 0,002–0,078 h; 81.468 requieren 0,226–7,242 h |
| D · regeneración parcial | 270.157 primarias sin candidato si se aceptaran todas las alternativas; 14.530.324 con el criterio de evidencia vigente | 270.157–14.530.324 inferencias | Referencias de secuencia v2 | 0,750–40,362 h |

Las cifras GPU son sensibilidad aritmética, sin benchmark. Para cada comparación, la reconstrucción exacta de lotes consume entre una y hasta 32 entradas de modelo por objetivo, según solapamiento. Los tiempos de E/S y verificación se suman. A–C solo necesitan metadatos y métricas permanentes; conservar los vectores del piloto sería redundante. D ocuparía **1,107–59,516 GB** de float32, una fila por primaria única. Descartar solo los tres D no deja claves exclusivamente D, según 3A.2. Las alternativas siguen sin certificar. El escenario C tiene **14.079.212 claves potenciales** y **48.538.951 ventanas potenciales** en la unión de las series, antes de retirar específicamente las direcciones D. Como cota conservadora, la retirada puede reducir esa unión hasta en 11.306 claves y 54.638 ventanas si sus alternativas quedaran fuera de las series.

## Qué garantiza cada método

- La validación individual controla un umbral de frecuencia de éxito **por bloque** con muestreo independiente. Su coste se acerca al de leer todos los bloques. Un fallo medido mantiene su consecuencia bajo la regla fijada.
- Un grupo demostrado exige un manifiesto de ejecución o evidencia equivalente que enlace pesos, tokenizador, código, parámetros y salidas. El intervalo de grupo se refiere a su población muestreada. Como ejemplo de riesgo, 29 bloques elegidos al azar dan al menos 95 % de probabilidad de tocar un bloque atípico si el 10 % de los bloques lo es y la prueba interna lo detecta siempre. Para el 5 % hacen falta 59. Si el bloque atípico tiene 10 % de filas incompatibles y se muestrean 12, la sensibilidad interna es aproximadamente 72 % y el ejemplo del 10 % requiere unos 41 bloques. Son cálculos de planificación con independencia aproximada; los bloques pequeños admiten corrección de población finita.
- Un modelo jerárquico por bloque y serie puede estimar heterogeneidad y predecir riesgo en bloques sin abrir. Requiere suficientes bloques en cada estrato, validación fuera de muestra y un modelo explícito de selección. La contracción entre grupos es útil para priorizar, con riesgo de enmascarar atípicos si se agrupan ejecuciones heterogéneas. El resultado seguiría siendo una estimación y cualquier uso operativo exigiría acordar su papel junto al criterio A.
- Combinar evidencia documental y muestreo en dos etapas preserva el control de bloque y concentra lecturas. Las series probables sirven de estratos hasta que exista una razón demostrable para extrapolar.

## Primera etapa propuesta

Seleccionar dos series por cobertura marginal de ventanas, dejando para diagnóstico las series con bloques D o filas idénticas a fallos, con bloques inéditos repartidos en cinco puntos del orden de archivo. En cada bloque, elegir doce primarias v2 distintas por un sorteo dentro del catálogo elegible y cuatro controles positivos dirigidos por multiplicidad, frecuencia e intervalo de escritura. Reservar negativos difíciles de un residuo con entradas limpias distintas. Excluir de los estimadores las 644 observaciones anteriores; se reutilizan para fijar referencias, comprobar los rangos de error, detectar patrones y mantener en cuarentena HLA-DQ/31, HLA-DR/876 y HLA-DR/1350.

| Serie | Bloques concretos propuestos | Ventanas candidatas del grupo |
|---|---|---:|
| HLA-B-period-1 | 1, 692, 1384, 2074, 2765 | 40.523.758 |
| H2-K-period-1 | 1, 392, 784, 1173, 1564 | 18.541.569 |

Son **160 comparaciones nuevas** en diez bloques y **2.568 GB** comprimidos de matrices. La cota de contexto es **5.120 entradas de modelo** si cada objetivo ocupa su propio lote de 32. Una pasada FP16 y un control FP32 focalizado son suficientes para el cribado. Un positivo fuera de umbral, una discrepancia de dirección o un negativo discriminable que pase detiene la promoción de la serie y dirige una investigación del bloque. Si todo pasa, el resultado permite planificar la segunda etapa, con un sorteo probabilístico de bloques y potencia definida. La categoría A individual sigue exigiendo el criterio original. Promover una serie requeriría además acreditar la procedencia o aprobar explícitamente otro criterio inferencial.

HLA-A aporta cuatro direcciones históricas con salida idéntica a los fallos y queda como diagnóstico separado, sin cambiar sus categorías por bloque. H2-D queda en un estrato propio. Sus inversiones temporales y el índice maestro posterior justifican muestrear segmentos y cambios antes de extrapolar. HLA-C y HLA-DR se estratifican a ambos lados de sus pausas. Los vecinos de los D se pueden usar como diagnósticos separados sin cambiar su estado a partir de la proximidad.
