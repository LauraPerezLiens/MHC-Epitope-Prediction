# NAP-CNB · Identidad histórica y reutilización certificada en D1

Se examinaron **15.100.592 observaciones originales de D1** leyendo solo las claves SecondaryBERT y las particiones del Parquet certificado. Se contó su uso de referencias archivadas o de vectores en el índice SQLite certificado. Se reutilizaron los inventarios y las comprobaciones de integridad anteriores. [Manifiesto de D1](../../../results/nap_cnb_v2_d1_original_manifest/manifest.json) · [Inventario histórico](inventory.json)

## Alcance cuantitativo

| Partición | Observaciones con SecondaryBERT histórico certificado | Observaciones con SecondaryBERT inline certificado |
|---|---:|---:|
| TRAIN | 12.060.793 | 22.837 |
| VALIDATION | 1.504.694 | 2.864 |
| TEST | 1.506.523 | 2.881 |
| **Total** | **15.072.010 (99,8107 %)** | **28.582 (0,1893 %)** |

Estos son recuentos de observaciones D1 por almacenamiento de una sola modalidad. Los **1.819.032** códigos C/H/E únicos certificados en **549** bloques históricos se reutilizan en varias observaciones. Los **28.404** códigos inline también son certificados. Ambos conjuntos cubren SecondaryBERT en D1. El numerador histórico corresponde a estructuras archivadas, con alcance independiente de la identidad de una proteína o de una fila aumentada. [Certificación 3C](../../../results/nap_cnb_v2_secondarybert/secondarybert_report.md)

Para la equivalencia integral entre D1 y los registros BLOSUM62, las categorías **A (acreditada)**, **B (ambigua)** y **C (sin correspondencia verificable)** quedan **sin recuento ni porcentaje**. Los metadatos inspeccionados identifican causas y alcances de evidencia. La clasificación individual requeriría establecer los vínculos entre observaciones, variantes y representaciones. Una fila sin clasificación permanece indeterminada.

## Convenciones de identidad

| Nivel | Evidencia conservada | Alcance o problema |
|---|---|---|
| Proteína | La clasificación histórica numera cada `protein_url` distinta dentro de cada CSV. Los metadatos históricos de SecondaryBERT conservan la URL. En las fuentes previas a la agregación de D1 figuran `parent_url`, acceso, versión y `parent_sha256`. | `protein_group_id` es un ordinal local. Una URL es una pista de origen. Para equiparar dos referencias de proteína se necesita evidencia de la revisión de la fuente o de identidad de su contenido. |
| Secuencia | `original_seq` y `blosum_seq` figuran en los CSV. | La misma primaria de 25 aminoácidos puede aparecer en diferentes proteínas, distintas posiciones y varias familias. Familia y especie acotan el origen, con posibles repeticiones dentro de cada una. |
| Ventana | Los metadatos históricos conservan `window_start` y algunos contienen la estructura original. Las fuentes canónicas de D1 conservan posiciones y contexto. | La identidad de ventana requiere una proteína versionada y un sistema de coordenadas comprobado. Pueden existir varios ejemplos de clasificación para la misma ventana física. |
| Observación D1 | Clave exacta formada por primaria y cadena C/H/E. | Es una identidad de la vista agregada. La observación publicada puede reunir varios contextos biológicos de origen. |
| Aumento y dirección histórica | Los CSV de aumento conservan `group_id`, la primaria original y la resultante. Los índices de embeddings documentan direcciones por familia o grupo. | Una dirección de archivo describe almacenamiento. La igualdad de recuentos o la coincidencia de un ordinal deja abierta la identidad entre vistas. |

[Código de clasificación histórica](../../../data_pipeline/scripts/data_classification/epitope_classification.py) · [Construcción de las vistas](../../../data_pipeline/scripts/rebuild_iedb/dataset_views.py) · [Contrato de D1](../../../results/nap_cnb_v2_d1_original_manifest/README.md)

## Procedencia e integridad por modalidad

- **ProtT5.** Hay **14.503 bloques históricos** de 1.024 float32, con índices y metadatos `blosum_seq` por bloque. Para **22** se cotejaron los SHA-256 del contenido expandido y **14.481** quedan pendientes. Se documenta el modelo nominal. Faltan pesos, tokenizador y configuración efectivos vinculados a cada ejecución. La acreditación de los embeddings originales de D1 procede de sus propios catálogos certificados.
- **SecondaryBERT.** Hay **551 bloques históricos** de 768 float32 y configuraciones compatibles documentadas en once familias. El historial de integridad registra **21** coincidencias de SHA-256 expandido y **530** pendientes. El índice de D1 acredita su subconjunto de C/H/E exactos. Los metadatos familiares documentan vectores por grupo histórico. [Procedencia ProtT5](../../../reports/audits/prott5_audit_3a3.md) · [Verificación de integridad](../../../reports/experiments/d1_blosum_integrity_verification.md)
- **Vista mixta concatenada.** Los **14.499** NPY de 1.792 float32 tienen recibos y direcciones históricas. Quedan **14.493** hashes de contenido pendientes. La vista conserva una referencia de almacenamiento y deja abierta la procedencia individual respecto a D1. [Inventario histórico](inventory.json)

## Volumen pendiente

El manifiesto previo cuantifica en **14,13 TB** la lectura para las verificaciones de contenido pendientes del conjunto histórico. Esa cifra mide E/S de integridad. El volumen que requeriría recálculo de las representaciones históricas queda indeterminado porque falta acreditar su correspondencia y configuración por ejecución. Para **los originales de D1**, las dos modalidades están completas y el número de representaciones pendientes de cálculo es **cero**. [Verificación de integridad](../../../reports/experiments/d1_blosum_integrity_verification.md) · [Resolución certificada de originales](../../../results/nap_cnb_v2_d1_representations/manifest.json)