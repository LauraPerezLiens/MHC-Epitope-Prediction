# Pseudosecuencias de MHC

## Qué es una pseudosecuencia y por qué 34 residuos

Las **posiciones polimórficas del MHC situadas a menos de 4,0 Å de un átomo pesado
del péptido unido**, con la cadena lateral orientada hacia él, identificadas sobre
estructuras cristalográficas representativas. Incluye algunas posiciones que
contactan a través de moléculas de agua (118 y 158).

No codifica «el alelo» sino **la química del bolsillo que ve el péptido**. Eso es lo
que permite que NetMHCpan sea *pan-específico*: un alelo ausente del entrenamiento
queda interpolado por similitud de surco en lugar de quedar sin predicción.

| | Longitud | Composición |
|---|---:|---|
| NetMHCpan (clase I) | 34 aa | cadena α del MHC-I |
| NetMHCIIpan (clase II) | 34 aa | **15 de la cadena α + 19 de la β** |

En clase II el detalle importa: en **HLA-DR** el polimorfismo está casi todo en la
cadena β, mientras que en **HLA-DP y HLA-DQ ambas cadenas son polimórficas**. Por eso
la pseudosecuencia de clase II necesita las dos cadenas y por eso DQ/DP son más
difíciles: hay que emparejar α y β, y IEDB no siempre anota las dos.

## Lo que hay aquí

### `pseudosequences.netmhcpan.34aa.csv` — clase I

13.007 alelos, formato `allele,pseudosequence`. Vocabulario **sin separadores**:
`HLA-A0201` (no `HLA-A*02:01`) y `H-2-Kb` (no `H2-Kb`). La conversión desde los
nombres de IEDB está implementada en `normalize_allele()` de
`data_pipeline/scripts/data_processing/build_peptide_table.py`.

Cobertura medida el 24 nov 2026 sobre la re-descarga de IEDB: **190 de 276 alelos,
que son el 95,70 % de las filas**. Lo no cubierto son casi todos serotipos de baja
resolución (`HLA-A2`, `HLA-B27`…), no alelos.

Censo por prefijo: HLA-B 4.866, HLA-A 3.739, HLA-C 3.234, Mamu (macaco) 509,
BoLA (bovino) 262, SLA (cerdo) 123, Patr (chimpancé) 210, HLA-G 16, H-2 (ratón) 22,
HLA-E 4, más entradas de perro y caballo.

> ⚠️ **Procedencia no documentada.** Este fichero apareció en el repositorio el
> 24 nov 2026 sin README ni manifiesto. Procede presumiblemente del paquete
> autónomo de NetMHCpan, pero **no consta la versión ni cómo se obtuvo**, y no hay
> ningún paquete de NetMHC instalado en este servidor. Dado que §0.5.7 exige
> comparar contra NetMHCpan para publicar, **conviene certificar su origen y
> versión antes de apoyar resultados en él.**

### Clase II — NO ESTÁ

Verificado: **cero entradas** de HLA-DR/DQ/DP y de H2-IA/IE. Las cuatro familias de
clase II salen con `con_pseudosecuencia_pct = 0,0 %`, así que la prioridad §0.5.3
(alelo en la entrada) está a la espera en clase II **por falta de este fichero, no
por un obstáculo conceptual**.

Dos vías para conseguirlo, por orden de coste:

1. **Paquete autónomo de NetMHCIIpan 4.3 de DTU.** La tabla viene dentro de
   `data.Linux.tar.gz`. El acceso es por **solicitud de licencia académica**:
   formulario de descarga para usuarios académicos, o contacto con
   `health-software@dtu.dk`. **Es una gestión que tiene que hacer Laura con su
   correo institucional**, no automatizable. Resolvería a la vez el problema de las
   pseudosecuencias y el del benchmark de §0.5.7, porque el mismo paquete da el
   predictor de referencia.
2. **Derivarla de los alineamientos de IPD-IMGT/HLA**, aplicando el criterio de
   4,0 Å sobre estructuras de clase II para fijar las 15 + 19 posiciones. Es
   reproducible y sin licencia, pero exige elegir estructuras de referencia y
   validar que las posiciones coinciden con las de Karosiene et al.; cualquier
   desviación invalidaría la comparación directa con NetMHCIIpan.

## Fuentes

- Criterio de 4,0 Å y construcción de la pseudosecuencia de clase I:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC3925504
- NetMHCpan original (pan-específico más allá del humano):
  https://pubmed.ncbi.nlm.nih.gov/19002680/
- Pseudosecuencia de clase II, 15 α + 19 β, método de Karosiene et al.:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6002223
- NetMHCIIpan-4.3, descarga y datos:
  https://services.healthtech.dtu.dk/services/NetMHCIIpan-4.3/
