# NAP-CNB · Verificación de integridad física BLOSUM62

**Fecha de revisión** 23 de noviembre de 2026 (UTC).

Se examinaron **30.141 archivos físicos únicos** en las rutas del inventario y de la firma de dependencias. Esta fase efectuó **1.218 comprobaciones nuevas de SHA-256**, con **1.218 coincidencias** y **0 discrepancias**. Se conservaron **38 coincidencias previas** en 20 archivos. El detalle por ruta y por flujo está en el [manifiesto JSONL](d1_blosum_integrity_manifest.jsonl).

## Alcance y condiciones de lectura

Los 14.503 bloques ProtT5 familiares, 551 SecondaryBERT canónicos y 14.499 concatenados representan tres conjuntos. Las 1.128 dependencias incluyen los 551 bloques SecondaryBERT y se cuentan una sola vez en el total físico. Los once índices familiares se contabilizan aparte. Se conservaron los resultados anteriores para las comprobaciones de contenido que coincidían con el alcance de esta fase. El TAR, el bloque ProtT5 reordenado y otros archivos de control ya comprobados se describen en el informe de procedencia. [Inventario](d1_blosum_existing_inventory.md) · [Procedencia](d1_blosum_artifact_provenance.md)

Los artefactos examinados ocupan **14.140.886.677.116 B**. La estimación previa, a partir del inventario, fue de unos 14,14 TB. Una lectura completa a 55 MB/s sostendría esa carga durante unas **71,4 horas**, antes del coste de la descompresión. El sistema mostraba 20 TiB disponibles en el dataset ZFS y 329 GiB en `/tmp`. Se observó un proceso MLP (PID 3348177) con lecturas acumuladas y uso del árbol compartido. El pool presentó actividad de lectura variable, con una observación de 160 MiB/s y un pico puntual del 92,8 % de utilización en uno de los discos muestreados. El espacio libre permitía guardar el manifiesto. La contención potencial de E/S con el entrenamiento justificó acotar la lectura de payloads.

Se usó un lector secuencial con bloques de 1 MiB, prioridad baja de CPU y E/S, y un límite medio de 55 MB/s para los payloads, reducido a 30 MB/s en la pasada auxiliar. Los Zstandard seleccionados para comprobar ambos flujos se pasaron al decodificador conforme se calculaba el hash del contenedor. La salida expandida se procesó en streaming. El trabajo incluyó los contenedores de los once índices maestros, las dependencias pequeñas de hasta 2.000.000 B y los arrays de IDs globales de familia, bloques de las once familias de cada modalidad y cuatro NPY concatenados repartidos en el intervalo de IDs. En cada familia se seleccionó el bloque elegible más pequeño y una posición central por tamaño cuando había más de dos candidatos. Este muestreo cubre distintas familias y tamaños. Su selección dirigida no permite extrapolar una tasa de fallos al conjunto.

## Resultados por conjunto

Cada celda cuenta comprobaciones de un flujo físico o lógico. Las filas de dependencias se solapan con SecondaryBERT. Una coincidencia del contenedor y otra del flujo expandido son dos comprobaciones en un mismo archivo.

| Conjunto | Flujo | Referencias examinadas | Coincide ahora | Coincidía previamente | Pendiente | Discrepancia | Ausente o ilegible | Solo estructura | Sin referencia |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ProtT5 familiar | contenedor zstd | 14.503 | 21 | 1 | 14.481 | 0 | 0 | 0 | 0 |
| ProtT5 familiar | contenido expandido | 14.503 | 21 | 1 | 14.481 | 0 | 0 | 0 | 0 |
| SecondaryBERT canónico | contenedor zstd | 551 | 20 | 1 | 530 | 0 | 0 | 0 | 0 |
| SecondaryBERT canónico | contenido expandido | 551 | 20 | 1 | 530 | 0 | 0 | 0 | 0 |
| Concatenado | contenido npy | 14.499 | 4 | 2 | 14.493 | 0 | 0 | 0 | 0 |
| Dependencias de concatenación | contenedor zstd | 1.128 | 581 | 16 | 531 | 0 | 0 | 0 | 0 |
| Dependencias de concatenación | contenido expandido | 1.128 | 581 | 16 | 531 | 0 | 0 | 0 | 0 |
| Índices maestros familiares | contenedor zstd | 11 | 10 | 1 | 0 | 0 | 0 | 0 | 0 |
| Índices maestros familiares | contenido expandido | 11 | 0 | 1 | 10 | 0 | 0 | 0 | 0 |

- **Referencias de integridad.** 0 archivos carecen de toda huella utilizable y 0 carecen de al menos una huella esperada. La referencia independiente de la lectura actual es el SHA-256 registrado en el recibo separado. El recibo aporta un valor de comparación histórico, sin autenticación externa de su publicación.
- **Ausencia y legibilidad.** 0 rutas físicas esperadas resultaron ausentes o inaccesibles al consultar sus metadatos. Hubo 0 archivos marcados como ausentes o ilegibles en al menos un flujo. La legibilidad completa de los archivos pendientes queda por verificar.
- **Recibos.** 0 problemas de lectura o coherencia del recibo y 0 discrepancias de tamaño del archivo físico respecto a su recibo. Los once índices y las 1.128 dependencias se identifican por la copia `.zst` y el lateral `.archive.json`. El cotejo de la ruta plana con la archivada procede de la revisión anterior.
- **Volumen.** Se leyeron **11.754.984.920 B** de payload de 616 archivos y **41.512.095 B** de recibos. El decodificador produjo **13.029.026.928 B** para verificar el contenido expandido. Ese último volumen corresponde a datos procesados en memoria en streaming. La cifra de lectura de payload excluye pequeños archivos de control usados para enumerar dependencias y representa bytes entregados al lector, con independencia de la caché.
- **Tiempo.** **3 min 49 s** de ejecución acumulada para la comprobación y escritura del manifiesto. La carga de recibos y metadatos tomó **0 min 13 s**. La lectura de payloads y el cierre del manifiesto tomaron **3 min 35 s**.

## Comprobaciones pendientes y reanudación

Quedan **44.527 flujos con referencia pendientes** en 29.515 archivos. Una pasada que cubriera sus archivos tocaría **14.129.501.541.344 B** contando una sola vez cada ruta. De las 1.128 dependencias, 597 tienen ambos SHA-256 cotejados y 531 quedan pendientes en ambos flujos. Estas últimas son 530 bloques SecondaryBERT canónicos y el índice maestro mixto de 26.080.827.296 B. Los contenedores de los índices maestros familiares se comprobaron contra el digest comprimido. Salvo H2-L, cuyo flujo expandido ya fue verificado, queda pendiente cotejar también sus bytes descomprimidos.

El manifiesto contiene una línea por ruta relativa al repositorio. Cada comprobación tiene el alcance, `sha256_referencia`, tamaño esperado y estado. Los cómputos nuevos incluyen el hash observado y los bytes procesados. `coincide_previo` remite a la evidencia del informe anterior. El tamaño y los metadatos de identidad de archivo permiten detectar cambios antes de reusar un resultado. Para continuar, seleccionar los flujos con `estado == "pendiente"` y agruparlos por ruta. Para `contenedor_zstd` y `contenido_npy`, aplicar SHA-256 a los bytes del archivo. Para `contenido_expandido`, calcularlo sobre la salida de Zstandard y comprobar su código de salida. Cotejar longitud y digest y actualizar únicamente las comprobaciones pendientes. Si faltara una referencia o el archivo cambiara, registrar la incidencia y conservar la evidencia anterior.

## Conclusión

Las verificaciones reproducidas acreditan la identidad física de los bytes cotejados respecto a sus recibos. La verificación integral del corpus sigue pendiente por el volumen de lectura y el uso compartido del almacenamiento. Los tamaños y cabeceras cotejados documentan la conservación estructural de los NPY concatenados. Para los contenedores comprimidos pendientes queda la evidencia de tamaño y recibo. La correspondencia variante–embedding y la cobertura respecto a D1 quedan indeterminadas.
