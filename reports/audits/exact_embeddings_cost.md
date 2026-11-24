# Coste y optimización de la auditoría exacta de embeddings

## Implementación actual

- Lee las observaciones originales por lotes Parquet. Mantiene un bloque de ProtT5 y otro de SecondaryBERT por fuente activa. Usa un archivo mapeado a disco para los vectores originales de toda la auditoría.
- Calcula un SHA-256 por modalidad y observación. SQLite ordena primero por hash de modalidad en todo el corpus. Las clases se asignan comprobando los valores exactos de cada candidato con los de su representante. Un hash coincidente puede terminar en varias clases.
- Agrupa por secuencia después de verificar las clases de modalidad. La clave final combina secuencia original, clase ProtT5, clase SecondaryBERT y etiqueta global. Una consulta separada agrupa por ambas modalidades sin la secuencia para detectar vectores idénticos con etiquetas diferentes.
- Lee el índice barajado por chunks, conserva solo las direcciones originales y coteja ambas modalidades frente a los vectores originales. La fase mezcla lecturas en orden barajado con accesos dispersos al archivo de vectores y búsquedas SQLite por fila.

La implementación no depende de `group_id` para establecer igualdad de dos observaciones. Las distancias del informe de casos se usan únicamente para describir diferencias.

## Presupuesto del código actual

| Concepto | Base de la estimación |
|---|---|
| Archivos de embeddings originales a leer | 14.503 bloques ProtT5 con 3,589 TB comprimidos y 1.102 bloques SecondaryBERT con 0,131 TB comprimidos. |
| Datos originales a descomprimir | Aproximadamente 6,11 TB de valores float32. ProtT5 contiene 26 registros por observación y el original ocupa uno de ellos. |
| Índice barajado | 26,08 GB comprimidos y 1.449.852.950 direcciones por examinar. Después se cotejan 55.763.575 originales. |
| Temporales de vectores | 372,26 GiB de valores float32 y 0,83 GiB de asignaciones de modalidad. Estos tamaños se derivan de la forma de los archivos con NumPy. |
| Espacio libre recomendado | 500–600 GiB para vectores, SQLite, índices, ordenaciones y margen. La cifra de SQLite requiere verificación en un piloto mayor. |
| RAM | 1,9 GiB de RSS pico en la muestra. Reservar al menos 8 GiB de RAM disponible para bloques y cachés, con margen adicional para la caché del sistema. El archivo mapeado puede aumentar los residentes de forma transitoria. |
| Tiempo | La muestra tardó 103 s, con 11 bloques Primarios y 12 chunks del índice barajado. Escalar ese tiempo por el número de bloques Primarios arroja unas 38 h como orden de magnitud, sin medir el coste completo de los índices y accesos aleatorios. Presupuestar 2–4 días en condiciones comparables. En disco mecánico bajo carga puede ser más. |

Como comprobación de sensibilidad, leer y descomprimir 6,11 TB a un rendimiento efectivo de 50, 100 o 200 MB/s tomaría 34, 17 o 8,5 horas respectivamente. Esos cálculos excluyen la validación posterior, la agrupación y el barajado.

## Optimizaciones propuestas

1. **Ordenar metadatos compactos antes de materializar vectores.** Representar la secuencia por un ID derivado de coincidencia exacta y escribir IDs, procedencia y hashes en registros binarios o Parquet por partición. Las dos huellas SHA-256 ocupan unos 3,32 GiB para las 55,8 millones de filas. Con IDs y direcciones, el núcleo sería del orden de 5–7 GiB antes de índices. El índice global existente aporta los recuentos de secuencia sin recalcular embeddings.
2. **Separar candidatos por tarea.** Particionar por ID de secuencia para deduplicación. Usar una segunda agrupación compacta de candidatos por el par de hashes de modalidad, independiente de la secuencia, para detectar posibles conflictos de etiqueta. En ambas rutas, programar los candidatos por archivo/bloque original y cotejar los valores exactos de los dos vectores antes de confirmar igualdad. Conservar clases separadas ante colisiones. Medir el disco pico en el piloto, ya que un volumen alto de candidatos puede obligar a releer bloques o mantener más vectores temporales.
3. **Compactar las direcciones después del barajado.** Filtrar los originales en una sola lectura del CSV y guardar un mapa compacto por bloque. Evaluar direcciones ordenadas y cotejos vectorizados. Los hashes distintos pueden descartar igualdad sin comparación adicional. Los hashes iguales conservan el cotejo valor por valor. Agrupar por bloque para evitar consultas SQLite y accesos dispersos por observación.
4. **Solapar y limitar la decodificación.** Probar 2–4 lectores de archivos originales con una cola acotada. Leer cada bloque de origen una vez por fase, extraer los originales y calcular hashes por lotes de trabajo. Medir MB/s descomprimidos, coste por grupo candidato, RSS, tamaño de temporales y tiempo de cotejo en SSD antes de elegir la concurrencia.
5. **Medir por fase en un piloto estratificado.** Incluir bloques de todas las familias, varios puntos del archivo barajado y secuencias repetidas en proteínas diferentes. Comparar los IDs de representante, los conflictos de etiqueta y la igualdad después del barajado con la implementación actual. Un diseño por particiones puede reducir temporales si acepta una segunda lectura agrupada. La ganancia de tiempo y el pico de disco dependen de ese intercambio y todavía no están medidos.

La auditoría completa y las optimizaciones propuestas quedan pendientes de ejecución e implementación respectivamente. Se conserva el criterio de secuencia, dos vectores y etiqueta exactamente iguales.
