# Análisis comparado de los dos datasets IEDB

**Fecha:** 24 de noviembre de 2026. Recorre las **113 columnas** de ambos árboles y desglosa las informativas.

| | Histórico | Nuevo `full` |
|---|---|---|
| Origen | `data/used_data/data_raw.tar.zst` (10 nov 2026) | `data/data_raw_full_20261124` (24 nov 2026) |
| Qué alimentó | **`data_input_nn` y todo el pipeline histórico** | Nada todavía |
| Filtro cualitativo | `ilike.*Positive*` | **ninguno** |
| Filtro de organismo fuente | `ilike.*<especie>*` | **ninguno** |
| **Filas** | **1.985.260** | **3.172.128** |

---

## 0. Lo que hay que saber, en diez líneas

1. **El histórico no tenía ni un solo negativo.** Cero sobre 1.985.260 filas. El filtro `ilike.*Positive*` los excluía por construcción. El nuevo trae **655.438**, el 20,66 %.
2. **El histórico era 100 % de origen propio**, con 9 organismos que son `Homo sapiens`, `Mus musculus` y siete cepas. El nuevo tiene **2.223 organismos**.
3. **Los matices del positivo casi no existían**: `Positive-High/Low/Intermediate` sumaban el 0,68 %. Ahora son el 5,19 %, con 164.631 filas que distinguen intensidad.
4. **Los datos de célula T se multiplican por 8**, de 22.931 a 185.785 filas.
5. **La afinidad en nM pasa del 0,49 % al 7,52 %**: de 9.724 a 238.559 filas, con 94.092 negativas. Ya da para regresión.
6. **HLA-DR es el caso extremo**: 472.174 de sus 997.964 filas son negativas, casi la mitad.
7. **Las publicaciones se triplican**, de 2.874 a 8.623 PMID: baja el riesgo de fuga por estudio.
8. **La contrapartida es la trazabilidad**: `epitope__molecule_parent` cae del 99,53 % al 83,05 % de relleno, y `mhc_restriction__evidence_code` del 99,18 % al 75,01 %.
9. **En ambos, el rango 8–11 aa domina** (60,2 % y 51,4 %): la ventana de 25 aa nunca fue la unidad biológica.
10. **Ninguno de los dos es usable en bruto.** El histórico porque solo tiene positivos; el nuevo porque hay que filtrar por evidencia y por disponibilidad de proteína madre.

---

## 1. La etiqueta: positivos y negativos

| Tipo de resultado | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Positive` | 1.971.739 | 99,32 % | 2.352.059 | 74,15 % |
| `Positive-High` | 5.298 | 0,27 % | 56.018 | 1,77 % |
| `Positive-Intermediate` | 2.521 | 0,13 % | 46.220 | 1,46 % |
| `Positive-Low` | 5.702 | 0,29 % | 62.393 | 1,97 % |
| **`Negative`** | **0** | 0,00 % | **655.438** | 20,66 % |
| **TOTAL positivas** | **1.985.260** | 100,00 % | **2.516.690** | 79,34 % |

> El histórico tiene **0 negativos**. No es que tenga pocos: el filtro `ilike.*Positive*` los excluía por construcción. El nuevo trae **655.438**, el 20.7 % de sus filas.

---

## 2. Desglose por familia MHC

### Histórico

| Familia | Filas | `mhc` | `tcell` | Positive | Pos-High | Pos-Int | Pos-Low | **Negative** | Alelos |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| human/mhc-I/HLA-B | 594.318 | 593.273 | 1.045 | 593.458 | 305 | 197 | 358 | **0** | 125 |
| human/mhc-I/HLA-A | 532.359 | 522.162 | 10.197 | 526.863 | 1.928 | 1.086 | 2.482 | **0** | 81 |
| human/mhc-II/HLA-DR | 353.214 | 346.917 | 6.297 | 349.394 | 1.072 | 875 | 1.873 | **0** | 90 |
| human/mhc-II/HLA-DP | 162.138 | 161.793 | 345 | 162.001 | 34 | 6 | 97 | **0** | 45 |
| human/mhc-I/HLA-C | 137.151 | 136.838 | 313 | 137.037 | 55 | 7 | 52 | **0** | 33 |
| mouse/mhc-I/H2-K | 88.306 | 87.256 | 1.050 | 88.012 | 122 | 64 | 108 | **0** | 7 |
| human/mhc-II/HLA-DQ | 48.394 | 47.617 | 777 | 47.789 | 183 | 160 | 262 | **0** | 80 |
| mouse/mhc-I/H2-D | 46.036 | 45.517 | 519 | 44.512 | 1.433 | 9 | 82 | **0** | 8 |
| mouse/mhc-II/H2-IA | 22.780 | 20.679 | 2.101 | 22.200 | 144 | 96 | 340 | **0** | 12 |
| mouse/mhc-II/H2-IE | 406 | 233 | 173 | 334 | 14 | 19 | 39 | **0** | 8 |
| mouse/mhc-I/H2-L | 158 | 44 | 114 | 139 | 8 | 2 | 9 | **0** | 2 |

### Nuevo `full`

| Familia | Filas | `mhc` | `tcell` | Positive | Pos-High | Pos-Int | Pos-Low | **Negative** | Alelos |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| human/mhc-II/HLA-DR | 997.964 | 965.856 | 32.108 | 471.582 | 19.530 | 16.155 | 18.523 | **472.174** | 127 |
| human/mhc-I/HLA-A | 779.373 | 707.935 | 71.438 | 628.287 | 21.565 | 16.054 | 22.251 | **91.216** | 107 |
| human/mhc-I/HLA-B | 764.866 | 739.486 | 25.380 | 697.137 | 6.795 | 6.559 | 7.888 | **46.487** | 168 |
| human/mhc-II/HLA-DP | 174.256 | 172.031 | 2.225 | 164.827 | 761 | 1.261 | 2.535 | **4.872** | 62 |
| human/mhc-I/HLA-C | 149.713 | 146.930 | 2.783 | 145.069 | 966 | 135 | 925 | **2.618** | 44 |
| mouse/mhc-I/H2-K | 110.315 | 94.689 | 15.626 | 96.342 | 1.232 | 885 | 1.776 | **10.080** | 17 |
| human/mhc-II/HLA-DQ | 77.166 | 71.534 | 5.632 | 55.939 | 2.256 | 4.150 | 5.161 | **9.660** | 104 |
| mouse/mhc-I/H2-D | 65.714 | 50.884 | 14.830 | 51.537 | 2.124 | 361 | 1.544 | **10.148** | 12 |
| mouse/mhc-II/H2-IA | 48.234 | 35.262 | 12.972 | 38.909 | 645 | 549 | 1.449 | **6.682** | 15 |
| mouse/mhc-II/H2-IE | 2.505 | 1.202 | 1.303 | 1.338 | 99 | 67 | 228 | **773** | 9 |
| mouse/mhc-I/H2-L | 2.022 | 534 | 1.488 | 1.092 | 45 | 44 | 113 | **728** | 2 |

---

## 3. Qué columnas traen información

Relleno de las 113 columnas. Se omiten IRIs, sinónimos y comentarios.

| Columna | Histórico | Nuevo `full` |
|---|---:|---:|
| `assay__method` | 100,00 % | 100,00 % |
| `assay__qualitative_measurement` | 100,00 % | 100,00 % |
| `assay__response_measured` | 100,00 % | 100,00 % |
| `assay_id` | 100,00 % | 100,00 % |
| `epitope__name` | 100,00 % | 100,00 % |
| `epitope__object_type` | 100,00 % | 100,00 % |
| `host__name` | 100,00 % | 100,00 % |
| `mhc_restriction__class` | 100,00 % | 100,00 % |
| `mhc_restriction__name` | 100,00 % | 100,00 % |
| `reference__authors` | 100,00 % | 100,00 % |
| `reference__date` | 100,00 % | 100,00 % |
| `reference__type` | 100,00 % | 100,00 % |
| `reference__title` | 99,95 % | 99,56 % |
| `reference__journal` | 99,35 % | 92,45 % |
| `reference__pmid` | 99,35 % | 92,45 % |
| `epitope__source_organism` | 100,00 % | 84,95 % |
| `epitope__species` | 100,00 % | 84,95 % |
| `epitope__source_molecule` | 100,00 % | 84,95 % |
| `epitope__ending_position` | 99,90 % | 83,17 % |
| `epitope__starting_position` | 99,90 % | 83,17 % |
| `epitope__molecule_parent` | 99,53 % | 83,05 % |
| `epitope__reference_name` | 73,45 % | 81,47 % |
| `mhc_restriction__evidence_code` | 99,18 % | 75,01 % |
| `antigen_presenting_cell__name` | 98,83 % | 73,62 % |
| `antigen_presenting_cell__culture_condition` | 98,83 % | 73,62 % |
| `antigen_presenting_cell__source_tissue` | 98,83 % | 73,60 % |
| `in_vivo_process__process_type` | 98,02 % | 69,15 % |
| `in_vivo_process__disease` | 39,88 % | 27,09 % |
| `host__mhc_types_present` | 26,85 % | 21,70 % |
| `in_vivo_process__disease_stage` | 19,36 % | 13,96 % |
| `host__age` | 16,62 % | 12,66 % |
| `host__sex` | 17,45 % | 12,03 % |
| `reference__submission_id` | 3,06 % | 9,49 % |
| `assay__quantitative_measurement` | 0,58 % | 8,21 % |
| `assay__units` | 0,57 % | 8,01 % |
| `epitope__modifications` | 7,45 % | 6,04 % |
| `epitope__modified_residues` | 7,45 % | 6,04 % |
| `assay__number_of_subjects_tested` | 5,16 % | 5,51 % |
| `assay__response_frequency_` | 4,94 % | 5,30 % |
| `assay__measurement_inequality` | 0,28 % | 4,21 % |
| `assay__number_of_subjects_responded` | 4,82 % | 3,16 % |
| `host__geolocation` | 2,63 % | 3,11 % |
| `in_vitro_process__process_type` | 1,05 % | 2,82 % |
| `related_object__epitope_relation` | 0,00 % | 1,14 % |
| `related_object__object_type` | 0,00 % | 1,14 % |
| `related_object__name` | 0,00 % | 1,14 % |
| `related_object__source_organism` | 0,00 % | 1,13 % |
| `related_object__molecule_parent` | 0,00 % | 1,11 % |
| `related_object__species` | 0,00 % | 1,09 % |
| `related_object__source_molecule` | 0,00 % | 1,09 % |
| `related_object__ending_position` | 0,00 % | 1,08 % |
| `related_object__starting_position` | 0,00 % | 1,08 % |
| `in_vitro_process__epitope_relation` | 0,46 % | 0,63 % |
| `in_vitro_process__object_type` | 0,46 % | 0,63 % |
| `in_vitro_process__name` | 0,46 % | 0,63 % |
| `in_vitro_process__source_organism` | 0,46 % | 0,62 % |
| `in_vitro_process__species` | 0,46 % | 0,62 % |
| `in_vivo_antigen__epitope_relation` | 0,32 % | 0,27 % |
| `in_vivo_antigen__object_type` | 0,32 % | 0,27 % |
| `in_vivo_antigen__name` | 0,32 % | 0,27 % |
| `in_vivo_antigen__source_organism` | 0,29 % | 0,26 % |
| `in_vivo_antigen__species` | 0,29 % | 0,26 % |
| `in_vitro_process__reference_name` | 0,04 % | 0,19 % |
| `in_vivo_antigen__reference_name` | 0,18 % | 0,11 % |
| `assay__pdb_id` | 0,02 % | 0,04 % |
| `in_vivo_antigen__dose_schedule` | 0,03 % | 0,02 % |
| `in_vivo_antigen__route` | 0,03 % | 0,02 % |

**Vacías en ambos (9):** `in_vitro_process__ending_position`, `in_vitro_process__molecule_parent`, `in_vitro_process__source_molecule`, `in_vitro_process__starting_position`, `in_vivo_antigen__adjuvants`, `in_vivo_antigen__ending_position`, `in_vivo_antigen__molecule_parent`, `in_vivo_antigen__source_molecule`, `in_vivo_antigen__starting_position`

---

## 4. Desglose de cada columna categórica

### 4.1. El ensayo

#### `assay__method`

Qué técnica se usó. Determina **qué se está midiendo**: presentación, unión o respuesta de célula T.

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `cellular MHC/mass spectrometry` | 1.622.886 | 81,75 % | 1.863.036 | 58,73 % |
| `mass spectrometry` | 262.068 | 13,20 % | 266.654 | 8,41 % |
| `High throughput multiplexed assay` | 0 | 0,00 % | 468.553 | 14,77 % |
| `purified MHC/competitive/radioactivity` | 5.765 | 0,29 % | 137.106 | 4,32 % |
| `secreted MHC/mass spectrometry` | 60.235 | 3,03 % | 62.622 | 1,97 % |
| `purified MHC/direct/fluorescence` | 2.007 | 0,10 % | 92.092 | 2,90 % |
| `ELISPOT` | 4.006 | 0,20 % | 65.844 | 2,08 % |
| `purified MHC/competitive/fluorescence` | 3.364 | 0,17 % | 52.429 | 1,65 % |
| `multimer/tetramer` | 3.922 | 0,20 % | 34.133 | 1,08 % |
| `ICS` | 1.437 | 0,07 % | 23.450 | 0,74 % |
| `cellular MHC/direct/fluorescence` | 2.688 | 0,14 % | 15.708 | 0,50 % |
| `ELISA` | 3.602 | 0,18 % | 14.339 | 0,45 % |
| `3H-thymidine` | 2.638 | 0,13 % | 10.195 | 0,32 % |
| `cellular MHC/competitive/fluorescence` | 631 | 0,03 % | 11.162 | 0,35 % |
| `51 chromium` | 1.371 | 0,07 % | 9.688 | 0,31 % |
| `biological activity` | 1.132 | 0,06 % | 9.096 | 0,29 % |
| `purified MHC/direct/radioactivity` | 332 | 0,02 % | 7.313 | 0,23 % |
| `cytometric bead array` | 1.615 | 0,08 % | 4.101 | 0,13 % |
| `binding assay` | 711 | 0,04 % | 3.978 | 0,13 % |
| `in vitro assay` | 737 | 0,04 % | 2.927 | 0,09 % |
| `purified MHC` | 543 | 0,03 % | 2.828 | 0,09 % |
| `in vivo assay` | 582 | 0,03 % | 2.724 | 0,09 % |
| *(otros 23 valores)* | 2.988 | 0,15 % | 12.150 | 0,38 % |

**Valores distintos:** histórico 40 · nuevo 45

#### `assay__units`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `nM` | 9.724 | 0,49 % | 238.559 | 7,52 % |
| `min` | 647 | 0,03 % | 11.233 | 0,35 % |
| `angstroms` | 397 | 0,02 % | 1.619 | 0,05 % |
| `°C` | 149 | 0,01 % | 1.050 | 0,03 % |
| `1/s` | 228 | 0,01 % | 804 | 0,03 % |
| `M^-1s^-1` | 178 | 0,01 % | 652 | 0,02 % |
| `nM^-1s^-1` | 5 | 0,00 % | 34 | 0,00 % |
| `1/nM` | 0 | 0,00 % | 9 | 0,00 % |
| *(otros 2 valores)* | 0 | 0,00 % | 7 | 0,00 % |

**Valores distintos:** histórico 7 · nuevo 10

#### `assay__measurement_inequality`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `=` | 4.751 | 0,24 % | 70.080 | 2,21 % |
| `>` | 253 | 0,01 % | 60.537 | 1,91 % |
| `<` | 579 | 0,03 % | 2.405 | 0,08 % |
| `>=` | 8 | 0,00 % | 290 | 0,01 % |
| `<=` | 28 | 0,00 % | 167 | 0,01 % |

**Valores distintos:** histórico 5 · nuevo 5

#### `assay__response_measured`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `ligand presentation` | 1.945.971 | 98,02 % | 2.193.621 | 69,15 % |
| `MHC binding` | 0 | 0,00 % | 468.548 | 14,77 % |
| `qualitative binding` | 9.848 | 0,50 % | 109.173 | 3,44 % |
| `IFNg release` | 6.814 | 0,34 % | 91.390 | 2,88 % |
| `dissociation constant KD (~IC50)` | 2.008 | 0,10 % | 82.199 | 2,59 % |
| `half maximal inhibitory concentration (IC50)` | 6.098 | 0,31 % | 74.203 | 2,34 % |
| `dissociation constant KD (~EC50)` | 273 | 0,01 % | 57.647 | 1,82 % |
| `dissociation constant KD` | 999 | 0,05 % | 22.661 | 0,71 % |
| `proliferation` | 3.161 | 0,16 % | 12.342 | 0,39 % |
| `cytotoxicity` | 2.127 | 0,11 % | 12.877 | 0,41 % |
| `half life` | 647 | 0,03 % | 11.233 | 0,35 % |
| `activation` | 748 | 0,04 % | 6.908 | 0,22 % |
| *(otros 88 valores)* | 6.566 | 0,33 % | 29.326 | 0,92 % |

**Valores distintos:** histórico 84 · nuevo 100

#### `in_vitro_process__process_type`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Restimulation in vitro` | 3.260 | 0,16 % | 43.312 | 1,37 % |
| `Primary induction in vitro` | 8.425 | 0,42 % | 26.271 | 0,83 % |
| `Antigen administered in vitro` | 9.087 | 0,46 % | 19.870 | 0,63 % |

**Valores distintos:** histórico 3 · nuevo 3

#### `in_vivo_process__process_type`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `No immunization` | 1.557.778 | 78,47 % | 1.744.180 | 54,98 % |
| `Occurrence of cancer` | 345.309 | 17,39 % | 399.097 | 12,58 % |
| `Occurrence of disease` | 20.708 | 1,04 % | 20.899 | 0,66 % |
| `Occurrence of autoimmune disease` | 15.983 | 0,81 % | 20.463 | 0,65 % |
| `Administration in vivo` | 3.811 | 0,19 % | 3.873 | 0,12 % |
| `Occurrence of infectious disease` | 2.366 | 0,12 % | 2.424 | 0,08 % |
| `Environmental exposure to endemic/ubiquitous agent without` | 0 | 0,00 % | 2.086 | 0,07 % |
| `Unknown` | 14 | 0,00 % | 553 | 0,02 % |
| `Occurrence of allergy` | 0 | 0,00 % | 25 | 0,00 % |
| `Exposure with existing immune reactivity without evidence ` | 0 | 0,00 % | 11 | 0,00 % |
| *(otros 2 valores)* | 2 | 0,00 % | 10 | 0,00 % |

**Valores distintos:** histórico 8 · nuevo 12

### 4.2. El alelo MHC

#### `mhc_restriction__class`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `I` | 1.398.328 | 70,44 % | 1.872.003 | 59,01 % |
| `II` | 586.932 | 29,56 % | 1.300.125 | 40,99 % |

**Valores distintos:** histórico 2 · nuevo 2

#### `mhc_restriction__evidence_code`

**Cómo se atribuyó el alelo.** `Single allele present` es atribución directa; `prediction` significa que lo puso un modelo, no un experimento.

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Statistically inferred by motif or alleles present` | 774.835 | 39,03 % | 900.541 | 28,39 % |
| `Single allele present` | 516.977 | 26,04 % | 580.625 | 18,30 % |
| `Elution with MHC specific antibody` | 194.545 | 9,80 % | 204.109 | 6,43 % |
| `Elution with MHC specific antibody - LB3.1` | 73.009 | 3,68 % | 117.391 | 3,70 % |
| `Elution with MHC specific antibody - B7/21` | 87.016 | 4,38 % | 87.093 | 2,75 % |
| `Elution with MHC specific antibody - BB7.2` | 76.930 | 3,88 % | 82.737 | 2,61 % |
| `Elution with MHC specific antibody - W6/32` | 64.275 | 3,24 % | 65.402 | 2,06 % |
| `Elution with MHC specific antibody - L243` | 39.774 | 2,00 % | 47.523 | 1,50 % |
| `Elution with MHC specific antibody - Y-3` | 30.237 | 1,52 % | 30.407 | 0,96 % |
| `Elution with MHC specific antibody - B22-249.R1` | 25.734 | 1,30 % | 25.773 | 0,81 % |
| `Cited reference` | 7.660 | 0,39 % | 40.347 | 1,27 % |
| `Elution with MHC specific antibody - SF1-1.1.1` | 22.225 | 1,12 % | 22.256 | 0,70 % |
| `MHC binding assay` | 6.537 | 0,33 % | 31.437 | 0,99 % |
| `MHC binding prediction` | 1.980 | 0,10 % | 35.672 | 1,12 % |
| *(otros 20 valores)* | 47.168 | 2,38 % | 108.093 | 3,41 % |

**Valores distintos:** histórico 28 · nuevo 34

#### `mhc_restriction__name`

Los 25 alelos más frecuentes.

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `HLA-A*02:01` | 202.021 | 10,18 % | 285.941 | 9,01 % |
| `HLA-DR` | 137.548 | 6,93 % | 190.636 | 6,01 % |
| `HLA-B*07:02` | 51.813 | 2,61 % | 82.688 | 2,61 % |
| `HLA-DRB1*15:01` | 17.094 | 0,86 % | 103.759 | 3,27 % |
| `H2-Kb` | 52.328 | 2,64 % | 66.238 | 2,09 % |
| `HLA-A*01:01` | 51.378 | 2,59 % | 64.439 | 2,03 % |
| `HLA-A*11:01` | 44.534 | 2,24 % | 60.489 | 1,91 % |
| `H2-Db` | 44.583 | 2,25 % | 57.533 | 1,81 % |
| `HLA-B*27:05` | 45.680 | 2,30 % | 52.921 | 1,67 % |
| `HLA-A*24:02` | 38.342 | 1,93 % | 52.468 | 1,65 % |
| `HLA-DRB1*03:01` | 6.684 | 0,34 % | 82.626 | 2,60 % |
| `HLA-B*57:01` | 40.665 | 2,05 % | 46.794 | 1,48 % |
| `HLA-B*15:01` | 38.722 | 1,95 % | 46.564 | 1,47 % |
| `HLA-A*03:01` | 24.091 | 1,21 % | 54.347 | 1,71 % |
| `HLA-DRB1*13:01` | 3.474 | 0,17 % | 74.625 | 2,35 % |
| `HLA-DRB1*13:02` | 1.101 | 0,06 % | 74.009 | 2,33 % |
| `HLA-B*40:01` | 33.671 | 1,70 % | 41.376 | 1,30 % |
| `HLA-B*15:02` | 36.312 | 1,83 % | 37.988 | 1,20 % |
| `HLA-B*44:02` | 32.232 | 1,62 % | 39.052 | 1,23 % |
| `HLA-DRB1*01:03` | 176 | 0,01 % | 70.120 | 2,21 % |
| `HLA-DRB1*15:02` | 48 | 0,00 % | 70.205 | 2,21 % |
| `HLA-B*40:02` | 31.689 | 1,60 % | 33.618 | 1,06 % |
| `HLA-DRB1*07:01` | 22.975 | 1,16 % | 42.289 | 1,33 % |
| `HLA-B*08:01` | 13.677 | 0,69 % | 45.965 | 1,45 % |
| `H2-Kd` | 24.793 | 1,25 % | 31.094 | 0,98 % |
| *(otros 642 valores)* | 989.629 | 49,85 % | 1.364.344 | 43,01 % |

**Valores distintos:** histórico 491 · nuevo 667

### 4.3. El epítopo

#### `epitope__object_type`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Linear peptide` | 1.985.260 | 100,00 % | 3.172.128 | 100,00 % |

**Valores distintos:** histórico 1 · nuevo 1

#### `epitope__source_organism`

**El origen del péptido.** Aquí es donde los dos datasets divergen por completo.

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Homo sapiens` | 1.827.574 | 92,06 % | 2.034.135 | 64,13 % |
| `Mus musculus` | 152.060 | 7,66 % | 164.751 | 5,19 % |
| `Severe acute respiratory syndrome coronavirus 2` | 0 | 0,00 % | 59.833 | 1,89 % |
| `unidentified` | 0 | 0,00 % | 43.808 | 1,38 % |
| `Vaccinia virus WR` | 0 | 0,00 % | 40.843 | 1,29 % |
| `Orthopoxvirus vaccinia` | 0 | 0,00 % | 23.275 | 0,73 % |
| `Phleum pratense` | 0 | 0,00 % | 17.569 | 0,55 % |
| `Yellow fever virus` | 0 | 0,00 % | 17.108 | 0,54 % |
| `Mycobacterium tuberculosis` | 0 | 0,00 % | 12.438 | 0,39 % |
| `Mus musculus C57BL/6` | 5.006 | 0,25 % | 5.012 | 0,16 % |
| `SARS coronavirus Tor2` | 0 | 0,00 % | 9.008 | 0,28 % |
| `Zaire ebolavirus` | 0 | 0,00 % | 7.483 | 0,24 % |
| `Influenza A virus` | 0 | 0,00 % | 5.488 | 0,17 % |
| `SARS-CoV1` | 0 | 0,00 % | 5.047 | 0,16 % |
| `Hepatitis B virus` | 0 | 0,00 % | 4.893 | 0,15 % |
| `Lymphocytic choriomeningitis virus (strain Armstrong)` | 0 | 0,00 % | 4.662 | 0,15 % |
| `human gammaherpesvirus 4` | 0 | 0,00 % | 4.520 | 0,14 % |
| `Giardia lamblia ATCC 50803` | 0 | 0,00 % | 4.471 | 0,14 % |
| `Mycobacterium tuberculosis H37Rv` | 0 | 0,00 % | 4.076 | 0,13 % |
| `Orthohepacivirus hominis` | 0 | 0,00 % | 4.039 | 0,13 % |
| `dengue virus type 3` | 0 | 0,00 % | 3.875 | 0,12 % |
| `Human betaherpesvirus 5` | 0 | 0,00 % | 3.831 | 0,12 % |
| `Plasmodium falciparum` | 0 | 0,00 % | 3.769 | 0,12 % |
| `Vaccinia virus Copenhagen` | 0 | 0,00 % | 3.660 | 0,12 % |
| `Francisella tularensis subsp. holarctica LVS` | 0 | 0,00 % | 3.208 | 0,10 % |
| *(otros 2198 valores)* | 620 | 0,03 % | 204.010 | 6,43 % |

**Valores distintos:** histórico 9 · nuevo 2223

#### `epitope__species`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Homo sapiens` | 1.827.574 | 92,06 % | 2.034.135 | 64,13 % |
| `Mus musculus` | 157.682 | 7,94 % | 170.389 | 5,37 % |
| `Orthopoxvirus vaccinia` | 0 | 0,00 % | 68.374 | 2,16 % |
| `Severe acute respiratory syndrome coronavirus 2` | 0 | 0,00 % | 65.464 | 2,06 % |
| `unidentified` | 0 | 0,00 % | 43.808 | 1,38 % |
| `Dengue virus` | 0 | 0,00 % | 20.175 | 0,64 % |
| `Yellow fever virus` | 0 | 0,00 % | 19.480 | 0,61 % |
| `Mycobacterium tuberculosis` | 0 | 0,00 % | 19.374 | 0,61 % |
| `Influenza A virus` | 0 | 0,00 % | 18.391 | 0,58 % |
| `Phleum pratense` | 0 | 0,00 % | 17.569 | 0,55 % |
| `SARS-CoV1` | 0 | 0,00 % | 14.138 | 0,45 % |
| `Orthohepacivirus hominis` | 0 | 0,00 % | 9.639 | 0,30 % |
| `Mammarenavirus choriomeningitidis` | 0 | 0,00 % | 8.643 | 0,27 % |
| `Orthoebolavirus zairense` | 0 | 0,00 % | 7.758 | 0,24 % |
| *(otros 941 valores)* | 4 | 0,00 % | 177.475 | 5,59 % |

**Valores distintos:** histórico 3 · nuevo 955

#### `epitope__modifications`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Oxidation` | 103.927 | 5,23 % | 129.974 | 4,10 % |
| `Deamidation|DEAM` | 12.173 | 0,61 % | 18.303 | 0,58 % |
| `Methylation|METH` | 11.036 | 0,56 % | 11.266 | 0,36 % |
| `Cysteinylation` | 7.016 | 0,35 % | 9.642 | 0,30 % |
| `Phosphorylation|PHOS` | 3.343 | 0,17 % | 4.057 | 0,13 % |
| `Pyrrolidone carboxylic acid|PYRE` | 3.124 | 0,16 % | 3.555 | 0,11 % |
| `Multiple modifications` | 1.590 | 0,08 % | 3.475 | 0,11 % |
| `Acetylation|ACET` | 935 | 0,05 % | 2.847 | 0,09 % |
| `Citrullination|CITR` | 1.139 | 0,06 % | 1.946 | 0,06 % |
| `Side chain modification` | 1.171 | 0,06 % | 1.514 | 0,05 % |
| *(otros 35 valores)* | 2.531 | 0,13 % | 5.085 | 0,16 % |

**Valores distintos:** histórico 34 · nuevo 45

### 4.4. El hospedador y el contexto

#### `host__name`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Homo sapiens (human)` | 1.827.460 | 92,05 % | 2.942.493 | 92,76 % |
| `Mus musculus C57BL/6` | 94.779 | 4,77 % | 122.900 | 3,87 % |
| `Mus musculus (mouse)` | 49.002 | 2,47 % | 69.034 | 2,18 % |
| `Mus musculus NOD` | 8.863 | 0,45 % | 11.924 | 0,38 % |
| `Mus musculus BALB/c` | 326 | 0,02 % | 11.779 | 0,37 % |
| `Mus musculus FVB/J` | 1.433 | 0,07 % | 1.436 | 0,05 % |
| `Mus musculus C57BL/6N` | 550 | 0,03 % | 596 | 0,02 % |
| `Mus musculus C3H/He` | 39 | 0,00 % | 862 | 0,03 % |
| `Homo sapiens Caucasian` | 97 | 0,00 % | 745 | 0,02 % |
| `Mus musculus C57BL/6 X BALB/c` | 149 | 0,01 % | 654 | 0,02 % |
| `Mus musculus SJL` | 111 | 0,01 % | 670 | 0,02 % |
| `Mus musculus C57BL/6 TAP null` | 295 | 0,01 % | 295 | 0,01 % |
| `Mus musculus NOD/Lt` | 136 | 0,01 % | 398 | 0,01 % |
| `Mus musculus A/J` | 137 | 0,01 % | 363 | 0,01 % |
| *(otros 286 valores)* | 1.883 | 0,09 % | 7.979 | 0,25 % |

**Valores distintos:** histórico 134 · nuevo 300

#### `host__mhc_types_present`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `HLA-A*02:01;HLA-B*40:01;HLA-B*44:02;HLA-C*03:04;HLA-C*05:0` | 50.015 | 2,52 % | 53.010 | 1,67 % |
| `HLA-A*02:01; HLA-A*11:01; HLA-B*15:01; HLA-B*35:01; HLA-C*` | 46.267 | 2,33 % | 46.267 | 1,46 % |
| `HLA-A*02:05; HLA-A*11:01; HLA-B*40:02; HLA-B*58:01; HLA-C*` | 35.871 | 1,81 % | 35.871 | 1,13 % |
| `HLA-A*01:01; HLA-A*69:01; HLA-B*37:01; HLA-B*49:01; HLA-C*` | 26.534 | 1,34 % | 26.534 | 0,84 % |
| `HLA-A*03:01; HLA-A*68:02; HLA-B*07:02; HLA-B*14:02; HLA-C*` | 25.173 | 1,27 % | 25.173 | 0,79 % |
| `HLA-A*24:02; HLA-A*30:01; HLA-B*13:02; HLA-B*35:08; HLA-C*` | 24.822 | 1,25 % | 24.822 | 0,78 % |
| `HLA-A*01:01; HLA-A*02:01; HLA-B*08:01; HLA-B*44:02; HLA-C*` | 24.761 | 1,25 % | 24.761 | 0,78 % |
| `HLA-A*02:01; HLA-A*68:02; HLA-B*14:02; HLA-B*27:05; HLA-C*` | 24.133 | 1,22 % | 24.133 | 0,76 % |
| *(otros 403 valores)* | 275.414 | 13,87 % | 427.862 | 13,49 % |

**Valores distintos:** histórico 303 · nuevo 411

#### `host__sex`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `F` | 273.930 | 13,80 % | 296.351 | 9,34 % |
| `M` | 72.549 | 3,65 % | 85.176 | 2,69 % |

**Valores distintos:** histórico 2 · nuevo 2

#### `antigen_presenting_cell__name`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `B cell` | 558.799 | 28,15 % | 579.737 | 18,28 % |
| `cell found in tissue` | 384.026 | 19,34 % | 385.978 | 12,17 % |
| `HMy2.C1R cell (B cell)` | 267.343 | 13,47 % | 343.970 | 10,84 % |
| `lymphoblast` | 89.516 | 4,51 % | 95.485 | 3,01 % |
| `splenocyte` | 80.355 | 4,05 % | 100.923 | 3,18 % |
| `K-562 cell (myeloid cell)` | 70.085 | 3,53 % | 70.905 | 2,24 % |
| `PBMC` | 22.559 | 1,14 % | 97.131 | 3,06 % |
| `LM-MEL-44 cell (melanocyte)` | 50.015 | 2,52 % | 53.010 | 1,67 % |
| `thymocyte` | 41.099 | 2,07 % | 41.102 | 1,30 % |
| `hepatocyte` | 38.938 | 1,96 % | 39.095 | 1,23 % |
| `dendritic cell` | 27.874 | 1,40 % | 47.411 | 1,49 % |
| `THP-1 cell (monocyte)` | 34.458 | 1,74 % | 38.709 | 1,22 % |
| *(otros 261 valores)* | 297.024 | 14,96 % | 441.949 | 13,93 % |

**Valores distintos:** histórico 187 · nuevo 273

#### `antigen_presenting_cell__source_tissue`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `blood` | 780.099 | 39,29 % | 1.033.214 | 32,57 % |
| `lymphoid` | 317.805 | 16,01 % | 332.885 | 10,49 % |
| `lung` | 121.139 | 6,10 % | 129.492 | 4,08 % |
| `spleen` | 86.035 | 4,33 % | 114.283 | 3,60 % |
| `lymph node` | 84.853 | 4,27 % | 92.981 | 2,93 % |
| `bone marrow` | 71.683 | 3,61 % | 80.908 | 2,55 % |
| `liver` | 62.718 | 3,16 % | 63.122 | 1,99 % |
| `thymus` | 48.245 | 2,43 % | 48.292 | 1,52 % |
| `brain` | 45.186 | 2,28 % | 47.086 | 1,48 % |
| `central nervous system (CNS)` | 18.510 | 0,93 % | 52.199 | 1,65 % |
| *(otros 44 valores)* | 325.792 | 16,41 % | 340.117 | 10,72 % |

**Valores distintos:** histórico 51 · nuevo 54

#### `in_vivo_process__disease`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `healthy` | 407.411 | 20,52 % | 416.337 | 13,12 % |
| `melanoma` | 75.545 | 3,81 % | 83.805 | 2,64 % |
| `glioblastoma` | 52.977 | 2,67 % | 88.856 | 2,80 % |
| `pleural cancer` | 60.712 | 3,06 % | 61.096 | 1,93 % |
| `acute monocytic leukemia` | 18.869 | 0,95 % | 38.585 | 1,22 % |
| `acute myeloid leukemia` | 28.692 | 1,45 % | 13.220 | 0,42 % |
| `pleural disease` | 14.683 | 0,74 % | 14.871 | 0,47 % |
| `chronic myeloid leukemia` | 13.181 | 0,66 % | 13.204 | 0,42 % |
| `cervical cancer` | 11.636 | 0,59 % | 11.636 | 0,37 % |
| `acute lymphoblastic leukemia` | 10.957 | 0,55 % | 11.056 | 0,35 % |
| `non-Hodgkin lymphoma` | 9.800 | 0,49 % | 11.543 | 0,36 % |
| `bone osteosarcoma` | 10.323 | 0,52 % | 10.323 | 0,33 % |
| `experimental colon cancer` | 6.188 | 0,31 % | 6.244 | 0,20 % |
| `respiratory system disease` | 5.947 | 0,30 % | 5.950 | 0,19 % |
| *(otros 102 valores)* | 64.856 | 3,27 % | 72.522 | 2,29 % |

**Valores distintos:** histórico 93 · nuevo 114

#### `in_vivo_antigen__route`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `intraperitoneal` | 532 | 0,03 % | 532 | 0,02 % |
| `intravenous` | 0 | 0,00 % | 22 | 0,00 % |
| `subcutaneous` | 0 | 0,00 % | 15 | 0,00 % |
| `intradermal` | 0 | 0,00 % | 8 | 0,00 % |

**Valores distintos:** histórico 1 · nuevo 4

### 4.5. La referencia bibliográfica

#### `reference__type`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `Literature` | 1.559.349 | 78,55 % | 2.505.926 | 79,00 % |
| `Live` | 365.152 | 18,39 % | 365.152 | 11,51 % |
| `Submission` | 12.931 | 0,65 % | 239.540 | 7,55 % |
| `Dual` | 47.828 | 2,41 % | 61.510 | 1,94 % |

**Valores distintos:** histórico 4 · nuevo 4

#### `reference__journal`

| Valor | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| `J Immunother Cancer` | 441.108 | 22,22 % | 444.403 | 14,01 % |
| `Front Immunol` | 129.665 | 6,53 % | 569.676 | 17,96 % |
| `Mol Cell Proteomics` | 212.590 | 10,71 % | 256.783 | 8,09 % |
| `Nat Biotechnol` | 218.508 | 11,01 % | 223.402 | 7,04 % |
| `J Immunol` | 131.307 | 6,61 % | 177.524 | 5,60 % |
| `Proteomics` | 127.834 | 6,44 % | 132.336 | 4,17 % |
| `J Clin Invest` | 99.052 | 4,99 % | 102.828 | 3,24 % |
| `Nat Commun` | 60.263 | 3,04 % | 125.557 | 3,96 % |
| `Cancer Immunol Res` | 73.699 | 3,71 % | 85.708 | 2,70 % |
| `Sci Immunol` | 39.206 | 1,97 % | 57.231 | 1,80 % |
| `JCI Insight` | 35.677 | 1,80 % | 36.268 | 1,14 % |
| `Sci Data` | 34.498 | 1,74 % | 34.498 | 1,09 % |
| *(otros 649 valores)* | 368.922 | 18,58 % | 686.374 | 21,64 % |

**Valores distintos:** histórico 358 · nuevo 661

---

## 5. Cardinalidades

| Qué | Histórico | Nuevo `full` | Cambio |
|---|---:|---:|---:|
| Péptidos únicos | 747.885 | 1.060.070 | ×1,42 |
| Alelos distintos | 491 | 667 | ×1,36 |
| Proteínas madre únicas | 21.616 | 27.236 | ×1,26 |
| Moléculas fuente únicas | 75.813 | 86.932 | ×1,15 |
| Publicaciones (PMID) | 2.874 | 8.623 | ×3,00 |
| Ensayos únicos | 1.985.260 | 3.172.128 | ×1,60 |

---

## 6. Longitud del péptido

| Longitud | Histórico | % | Nuevo `full` | % |
|---|---:|---:|---:|---:|
| 2 aa | 2 | 0,00 % | 5 | 0,00 % |
| 3 aa | 2 | 0,00 % | 4 | 0,00 % |
| 4 aa | 10 | 0,00 % | 27 | 0,00 % |
| 5 aa | 54 | 0,00 % | 195 | 0,01 % |
| 6 aa | 355 | 0,02 % | 463 | 0,01 % |
| 7 aa | 8.027 | 0,40 % | 9.522 | 0,30 % |
| **8 aa** | 105.109 | 5,29 % | 132.229 | 4,17 % |
| **9 aa** | 752.789 | 37,92 % | 1.042.928 | 32,88 % |
| **10 aa** | 212.635 | 10,71 % | 303.054 | 9,55 % |
| **11 aa** | 124.398 | 6,27 % | 151.200 | 4,77 % |
| 12 aa | 63.250 | 3,19 % | 76.332 | 2,41 % |
| 13 aa | 69.699 | 3,51 % | 511.428 | 16,12 % |
| 14 aa | 92.891 | 4,68 % | 107.979 | 3,40 % |
| 15 aa | 113.882 | 5,74 % | 275.249 | 8,68 % |
| 16 aa | 100.593 | 5,07 % | 117.774 | 3,71 % |
| 17 aa | 76.030 | 3,83 % | 92.523 | 2,92 % |
| 18 aa | 87.617 | 4,41 % | 104.881 | 3,31 % |
| 19 aa | 37.384 | 1,88 % | 45.027 | 1,42 % |
| 20 aa | 39.129 | 1,97 % | 63.552 | 2,00 % |
| 21 aa | 22.281 | 1,12 % | 29.118 | 0,92 % |
| 22 aa | 15.765 | 0,79 % | 19.817 | 0,62 % |
| 23 aa | 10.684 | 0,54 % | 14.375 | 0,45 % |
| 24 aa | 10.262 | 0,52 % | 13.858 | 0,44 % |
| 25 aa | 9.083 | 0,46 % | 12.380 | 0,39 % |
| 26 aa | 6.768 | 0,34 % | 9.439 | 0,30 % |
| 27 aa | 5.614 | 0,28 % | 7.826 | 0,25 % |
| 28 aa | 4.601 | 0,23 % | 6.103 | 0,19 % |
| 29 aa | 3.585 | 0,18 % | 5.107 | 0,16 % |
| 30 aa | 2.853 | 0,14 % | 4.320 | 0,14 % |
| > 30 aa | 9.908 | 0,50 % | 15.413 | 0,49 % |

**Rango canónico de MHC-I (8–11 aa):** histórico 60.2 % · nuevo 51.4 %

---

## 7. Afinidad cuantitativa

| | Histórico | Nuevo `full` |
|---|---:|---:|
| Filas con medida en nM | 9.724 | **238.559** |
| % del total | 0,49 % | 7,52 % |

**Reparto por etiqueta de las filas con nM:**

| Etiqueta | Histórico | Nuevo `full` |
|---|---:|---:|
| `Negative` | 0 | 94.092 |
| `Positive-Low` | 2.572 | 48.042 |
| `Positive-High` | 2.334 | 45.653 |
| `Positive-Intermediate` | 1.979 | 41.098 |
| `Positive` | 2.839 | 9.674 |

**Histórico** — mediana 636,0 nM, p25 84,8, p75 4009,0, mín 0,00, máx 1347000, n=9,721

**Nuevo** — mediana 2767,0 nM, p25 156,0, p75 20000,0, mín 0,00, máx 6000000000, n=238,202

---

## 8. Qué hacer con esto

**Filtros obligatorios antes de entrenar con el nuevo:**

1. **Excluir `mhc_restriction__evidence_code` = `MHC binding prediction`.** Son filas cuyo alelo lo asignó un modelo: entrenar sobre ellas es circular. En el nuevo son 35.672 frente a 1.980 del histórico.
2. **Decidir qué hacer con el 25,01 % sin código de evidencia.** No es ruido necesariamente, pero tampoco es atribución verificada.
3. **Separar por `assay__method`.** Presentación, unión e inmunogenicidad son tres objetivos distintos y el dataset los mezcla en una etiqueta binaria.
4. **Para construir ventanas, exigir `epitope__molecule_parent`.** El 16,95 % del nuevo no lo tiene y esas filas no se pueden mapear a una proteína.

**Oportunidades que el histórico no permitía:**

| Vía | Por qué ahora sí |
|---|---|
| **Negativos reales para calibrar** | 655.438 medidas negativas. El carácter positive-unlabeled era en parte autoimpuesto |
| **Regresión de afinidad** | 238.559 filas en nM, repartidas por intensidad. Es lo que predicen NetMHCpan y MHCflurry en modo BA |
| **Modelo de inmunogenicidad** | 185.785 filas de ensayos de célula T |
| **Clase II en serio** | HLA-DR pasa de 353.214 a 997.964 filas, con casi la mitad negativas |
| **Alelo como entrada** | 667 alelos distintos frente a 491 |

> **Y una advertencia sobre la comparación con Wert2021.** Su modelo H-2Kb se entrenó sobre todos los epítopos H-2Kb de IEDB, dominados por los de patógeno. El histórico nuestro los excluía por completo, así que **la comparación con su 0,865 nunca fue homogénea**. Con el nuevo dataset sí puede serlo, filtrando el universo que corresponda.

---

*Generado con `data_pipeline/scripts/data_processing/analisis_datasets.py`. Los perfiles crudos en JSON están en `reports/audits/perfil_dataset_*_20261124.json`.*
