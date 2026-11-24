# NAP-CNB v2 · ventanas originales y estructura secundaria

Destino: `/data/nap/lperez_nn/results/nap_cnb_v2_phase1`.

| Familia | Proteínas elegibles | Ventanas generadas | Ventanas binarias | Positivos | Negativos | Holdouts | C/H/E verificada | Originales históricos | Posiciones históricas | Positivos históricos por posición |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HLA-A | 15,818 | 9,583,585 | 9,502,740 | 1,521,405 | 7,981,335 | 80,845 | 9,319,991 | 10,214,658 | 9,523,132 | 1,542,748 |
| HLA-B | 16,181 | 9,643,627 | 9,531,009 | 2,001,316 | 7,529,693 | 112,618 | 9,312,062 | 10,639,963 | 9,620,155 | 2,039,694 |
| HLA-C | 11,833 | 7,547,836 | 7,513,895 | 781,899 | 6,731,996 | 33,941 | 7,485,498 | 7,788,459 | 7,596,123 | 799,606 |
| HLA-DP | 6,695 | 4,294,875 | 4,291,091 | 238,576 | 4,052,515 | 3,784 | 4,284,889 | 5,027,325 | 4,464,776 | 243,947 |
| HLA-DQ | 3,386 | 2,116,686 | 2,114,393 | 108,805 | 2,005,588 | 2,293 | 2,102,586 | 2,389,441 | 2,194,959 | 108,383 |
| HLA-DR | 9,353 | 5,907,133 | 5,889,056 | 420,357 | 5,468,699 | 18,077 | 5,841,887 | 7,588,227 | 6,482,302 | 440,835 |
| H2-D | 4,406 | 3,080,035 | 3,072,856 | 126,584 | 2,946,272 | 7,179 | 3,057,989 | 4,244,842 | 4,185,817 | 181,137 |
| H2-K | 8,359 | 5,521,496 | 5,501,215 | 346,276 | 5,154,939 | 20,281 | 5,472,862 | 6,022,825 | 5,848,668 | 382,785 |
| H2-L | 7 | 4,819 | 4,819 | 145 | 4,674 | 0 | 4,421 | 4,448 | 4,421 | 99 |
| H2-IA | 2,448 | 1,715,746 | 1,713,218 | 47,581 | 1,665,637 | 2,528 | 1,702,399 | 1,790,731 | 1,726,584 | 50,779 |
| H2-IE | 134 | 70,821 | 70,812 | 1,585 | 69,227 | 9 | 70,360 | 52,656 | 52,373 | 1,269 |
| **Total** | 78,620 | 49,486,659 | 49,205,104 | 5,594,529 | 43,610,575 | 281,555 | 48,654,944 | 55,763,575 | 51,699,310 | 5,791,282 |

- Secuencias primarias únicas: **14,554,919**.
- Combinaciones únicas de secuencia y C/H/E verificada: **15,006,963**.
- Cobertura estructural: **98.882 %**. Las cadenas faltantes se guardan como null con su motivo.
- Ventanas binarias con evidencia simple pendiente en una posible posición: **242,038**. La procedencia identifica los candidatos y su motivo.
- Ventanas por estado estructural: {'matched': 48654944, 'missing_prediction': 81601, 'unverified_archived_reference': 468559}.
- Proteínas por familia con estado estructural: {'matched': 77513, 'missing_prediction': 245, 'unverified_archived_reference': 862}. El detalle por proteína y las ventanas afectadas están en `structure_gaps.tsv`.

## Cambios respecto al histórico

- El histórico contiene **4,064,265** filas adicionales al contar cada posición una sola vez. V2 conserva una observación por familia–proteína–inicio y enlaza todas sus evidencias.
- Holdouts totales: **281,555**. De ellos, **266,551** coincidían con un positivo histórico por posición. Los motivos e IDs están en `holdouts/` y `evidence_pending/`.
- Holdouts por combinación de motivos: {'modified_peptide_excluded': 281555}. Se excluyeron **146,848** registros de ensayo modificados como fuente de positivos.
- Salieron del conjunto binario **4,138,869** posiciones históricas. Este recuento incluye las reservas y las posiciones que el constructor ya no emite.
- Posiciones nuevas: **1,644,663**, incluidas **1,644,663** en pares familia–proteína ausentes del histórico. Cambiaron de 0 a 1 **200,456** posiciones y de 1 a 0 **100,025**.
- **134,012** registros de ensayo verificados tienen coordenadas parent distintas de las source originales. **264,512** ventanas positivas se apoyan exclusivamente en registros remapeados con desplazamiento.
- Métodos de verificación por registro de ensayo: {'exact_whole_reference_identity': 21043, 'full_reference_alignment': 33218, 'iedb_explicit_parent_reference': 1687249, 'verified_prior_coordinate_audit': 26697}. Los cambios por posición pueden combinar remapeos y exclusiones de evidencia.

## Archivos

- `families/` contiene una ventana por posición, su etiqueta familiar y el recorte C/H/E cuando se verificó.
- `global_index.parquet` asigna etiqueta global 1 a cada secuencia con al menos una observación positiva entre las familias incluidas.
- `references/`, `proteins/`, `provenance/`, `evidence_verified/`, `evidence_pending/` y `holdouts/` documentan las decisiones.

Tamaño lógico de datos y metadatos permanentes del destino, incluidos los checkpoints y la caché de referencias: **2,001,337,497 bytes**.
