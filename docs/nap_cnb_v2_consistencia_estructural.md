# Consistencia estructural de los seis casos de SecondaryBERT

**Resultado.** Se encontraron 0 inconsistencias en 15 apariciones y 12 loci. Las 11 comparaciones con SecondaryBERT distinto tienen exactamente un estado C/H/E distinto. Las 4 comparaciones con la misma entrada y la misma configuración registrada tienen vectores idénticos, con diferencia máxima absoluta de 0. Las métricas proceden del cotejo previo de vectores originales. Esta comprobación no ejecutó inferencias.

## Proteínas y predicciones

Los FASTA archivados permiten comprobar versión UniProt `SV`, longitud y SHA-256 de la secuencia completa. El CSV histórico de ProteinUnet guarda URL, secuencia completa y C/H/E completa. No guarda un ID de ejecución ni la huella de los pesos del predictor. Cuando se localiza el miembro original, su identidad y el hash del C/H/E completo identifican el **artefacto observado**. La huella del modelo SecondaryBERT identifica el codificador posterior.

| Accession | SV | aa | SHA-256 de secuencia | SHA-256 del C/H/E completo |
|---|---:|---:|---|---|
| A0A075B5T2 | 7 | 118 | `05afdeb57d590574b7ea4d393886c716b09a14adca03368b0dba9bb6a8d4de18` | Pendiente de localizar el miembro original |
| A0A075B5T3 | 1 | 119 | `0872dca76fa2990290c0c8f73800e6e3acedd119aea2e86480185535d49176bc` | Pendiente de localizar el miembro original |
| A0A075B6P5 | 1 | 120 | `cec9eb101aaf5c8fa53369da5c72ed99a53361dfb0a26f583e57bd58efd63d5d` | `dc27304879dd8192f4e26dbe4e6b5a7be0f8084bc0c9bcdb432e5be482cf997f` |
| A0A087WW87 | 2 | 121 | `0478b6eb4cfdc191384caf50b9dfaba0fb6e0e94ec23939db251cf178f04381d` | `693053fef4d39ccb59e6930ec3c64dac6237dc9d23595d2ba8813bb594612e83` |

Miembros de predicción verificados y sus huellas de archivo:

- `data_intermediate/secondary_struct_human.csv` · `c54f16a4d9c143d143341ae8fab4eb9cda7d176996bff093b350db6ca13684ce`

El recorte directo de la predicción completa se comprobó en 5 apariciones. La secuencia primaria y su posición se verificaron contra el FASTA en las 15. Ninguna ventana primaria coincide con su recorte desplazado ±1. Los metadatos originales de SecondaryBERT marcan `ss_status=ok` y su `secondary_structure` es idéntica a `clean_ss` en las 15. Para el agrupamiento por locus, se usó el hash de predicción completa cuando estaba disponible y se dejó pendiente el identificador del artefacto en los demás casos.

## Las 15 apariciones

Las coordenadas son 1-based inclusivas. La dirección SecondaryBERT usa `source_dataset_id:group_id:fila`, con fila 0-based dentro de `chunks/chunk_000000_X_ss.npy` de la familia indicada. El manifiesto de chunks y el índice de grupos permiten resolver la ruta física.

| Ventana primaria | Parent | Intervalo | C/H/E | Familia | Dirección |
|---|---|---|---|---|---|
| `GVQSEVKLEESGGGLVQPGGSMKLS` | A0A075B5T2 | 16–40 | `CCCCEEEEEECCCCEECCCCCEEEE` | H2-IA | `9:558:557` |
| `GVQSEVKLEESGGGLVQPGGSMKLS` | A0A075B5T3 | 16–40 | `CCCCEEEEECCCCCEECCCCCEEEE` | H2-IA | `9:652:651` |
| `KGVQSEVKLEESGGGLVQPGGSMKL` | A0A075B5T2 | 15–39 | `CCCCCEEEEEECCCCEECCCCCEEE` | H2-IA | `9:557:556` |
| `KGVQSEVKLEESGGGLVQPGGSMKL` | A0A075B5T3 | 15–39 | `CCCCCEEEEECCCCCEECCCCCEEE` | H2-IA | `9:651:650` |
| `LKGVQSEVKLEESGGGLVQPGGSMK` | A0A075B5T2 | 14–38 | `ECCCCCEEEEEECCCCEECCCCCEE` | H2-IA | `9:556:555` |
| `LKGVQSEVKLEESGGGLVQPGGSMK` | A0A075B5T3 | 14–38 | `ECCCCCEEEEECCCCCEECCCCCEE` | H2-IA | `9:650:649` |
| `LLKGVQSEVKLEESGGGLVQPGGSM` | A0A075B5T2 | 13–37 | `EECCCCCEEEEEECCCCEECCCCCE` | H2-IA | `9:555:554` |
| `LLKGVQSEVKLEESGGGLVQPGGSM` | A0A075B5T3 | 13–37 | `EECCCCCEEEEECCCCCEECCCCCE` | H2-IA | `9:649:648` |
| `RASGVPDRFSGSGSGTDFTLKISRV` | A0A075B6P5 | 79–103 | `CCCCCCCCCCCCCCCCEEEEEEEEE` | HLA-C | `2:330:329` |
| `RASGVPDRFSGSGSGTDFTLKISRV` | A0A075B6P5 | 79–103 | `CCCCCCCCCCCCCCCCEEEEEEEEE` | HLA-DP | `3:678:677` |
| `RASGVPDRFSGSGSGTDFTLKISRV` | A0A075B6P5 | 79–103 | `CCCCCCCCCCCCCCCCEEEEEEEEE` | HLA-DQ | `4:409:408` |
| `RASGVPDRFSGSGSGTDFTLKISRV` | A0A087WW87 | 80–104 | `ECCCCCCCCCCCCCCCEEEEEEEEE` | HLA-DQ | `4:788:787` |
| `RASGVPDRFSGSGSGTDFTLKISRV` | A0A087WW87 | 80–104 | `ECCCCCCCCCCCCCCCEEEEEEEEE` | HLA-DQ | `4:789:788` |
| `VQSEVKLEESGGGLVQPGGSMKLSC` | A0A075B5T2 | 17–41 | `CCCEEEEEECCCCEECCCCCEEEEE` | H2-IA | `9:559:558` |
| `VQSEVKLEESGGGLVQPGGSMKLSC` | A0A075B5T3 | 17–41 | `CCCEEEEECCCCCEECCCCCEEEEE` | H2-IA | `9:653:652` |

Los cinco casos H2-IA tienen la misma posición en dos proteínas de ratón con secuencias completas distintas. En `RASGVPDRFSGSGSGTDFTLKISRV` cambian tanto la proteína humana como el inicio, 79 frente a 80. Las tres apariciones de A0A075B6P5 en HLA-C, HLA-DP y HLA-DQ coinciden exactamente entre sí. Las dos de A0A087WW87 en HLA-DQ también coinciden exactamente. Las diferencias de vectores están acompañadas por un cambio real en la entrada C/H/E. La comparación observacional no separa el efecto del contexto proteico del efecto de la posición en el caso humano.

Los cuatro almacenes registran la misma huella SecondaryBERT `7714351fc71dd4c3b929d9835d00bdb7d4869e982b9fb32054e4bf9c3846b72d`, el mapa `C=5,H=6,E=7`, la media de los 25 tokens biológicos, salida float32, lote 4.096 y dos procesos. CUDA permite autocast FP16; los vectores ya almacenados con la misma entrada de esta muestra coinciden exactamente sin elegir una tolerancia.

## Recorte y alineación

- ProteinUnet aplica one-hot y padding a proteínas de hasta 1.024 aa. Las más largas se procesan con solape de 200 aa y se recomponen por posición antes de decidir C/H/E. El CSV conserva la secuencia y una letra estructural por residuo. [Predicción y formato](../data_pipeline/scripts/secondary_structure_prediction/predict_secondary_structure.py#L195)
- El recorte aplica `i = window_start - 1` y `[i:i+25]` a ambas secuencias. Comprueba longitud, rango y coincidencia exacta con los 25 aa esperados. No se observó desplazamiento. El lookup histórico indexa por URL normalizada y la última fila puede sustituir a otra con esa URL. Una coincidencia local de 25 aa permite que ese problema pase inadvertido si cambian los flancos. [Recorte](../data_pipeline/scripts/secondary_structure_prediction/add_secondary_structure.py#L73)
- El barajado conserva dataset, chunk y fila de origen y aplica un offset al grupo. La concatenación toma ProtT5 por fila y SecondaryBERT por grupo global y verifica ambas porciones del archivo escrito. La auditoría anterior verificó 41 originales barajados sin diferencias en ninguna modalidad. Es una comprobación muestral separada del cotejo de estos seis casos en origen. [Barajado](../data_pipeline/scripts/data_shuffling/reorder_chunks.py#L93) · [Concatenación](../data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py#L424) · [Muestra barajada](../reports/audits/exact_embeddings_sample.md)

## Claves para v2

- **ProtT5.** 25 aa originales exactos y huella de pesos, tokenizer, limpieza, pooling y precisión. Registrar el contexto de entrada como una sola ventana de 25 aa.
- **Procedencia estructural.** `(SHA256 de secuencia completa, inicio 1-based, ID del artefacto de predicción)`. Incluir el hash del C/H/E completo y, para ejecuciones futuras, la huella del predictor, su código y parámetros. Rechazar claves con secuencia o recorte contradictorios. Conservar el accession y su versión como procedencia.
- **SecondaryBERT.** Validar primero la procedencia, los 25 aa y el recorte. Para compartir un vector, usar los 25 estados C/H/E exactos y la huella de pesos, tokenizer, mapa de tokens, pooling y política numérica. Conservar la dirección del bloque y fila originales. Ante discrepancias entre vectores de entradas idénticas, comprobar la configuración y preservar las representaciones separadas mientras no se explique la diferencia.

No hay correcciones de datos indicadas para estos seis casos. El cambio recomendado es exigir esas claves al reutilizar embeddings y registrar una identidad reproducible de las predicciones futuras. Metadatos de las 15 apariciones (`../results/embedding_representation_cases_20261118/observations.csv`, artefacto retirado) · Comparaciones numéricas originales (`../results/embedding_representation_cases_20261118/pairwise.csv`, artefacto retirado)
