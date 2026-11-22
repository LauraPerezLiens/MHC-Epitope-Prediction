# Reconstrucción NAP-CNB con evidencia simple

El constructor v2 lee las exportaciones archivadas de MHC y T-cell. Conserva cada fila positiva admitida por los filtros originales de organismo, clase y familia con su nombre original, modificación, IRIs, ensayo, método experimental, resultado y localizador de archivo y fila. Los registros se mantienen por ensayo y fila, de modo que dos entidades químicas con el mismo esqueleto conservan sus identidades.

## Referencias y ventanas

La validación acepta una anotación explícita de IEDB en la versión exacta del parent o un remapeo previo verificado con el mismo registro identificado por estructura y ensayo, las mismas referencias e intervalo originales, el mismo hash del parent y residuos exactos. Si ambas fuentes proporcionan intervalos contradictorios, el registro queda pendiente. Para proyectar desde la proteína fuente se exige una referencia fijada a una versión o cadena, coincidencia exacta de sus residuos y una correspondencia inequívoca por identidad o alineamiento de proteínas completas.

Cada par familia–parent con al menos un evento simple verificado se recorre con ventanas de 25 aa y paso 1. Las coordenadas empiezan en 1 y ambos extremos son inclusivos. Un positivo contiene por completo al menos un epítopo simple verificado. Dos ensayos válidos en la misma ventana producen una sola observación y dos vínculos de evidencia.

Una posible posición exclusivamente modificada o de química indeterminada se reserva para revisión si carece de un positivo simple en esa ventana. Para localizar estas posiciones se usa el esqueleto lineal explícito de IEDB dentro del mismo parent y se protege también el locus histórico si el fragmento usado por el clasificador coincide exactamente en el intervalo original. Esas coincidencias se usan solo para la reserva. Si falta un esqueleto o un locus histórico comprobable, el evento queda guardado para revisión sin una posición asignada. Una ventana generada independientemente en otra proteína o familia se evalúa con sus propias evidencias.

## Salidas

| Archivo | Contenido |
|---|---|
| `families/*.parquet` | Una observación por familia, referencia parent e intervalo. |
| `provenance/*.parquet` | Identificador de la ventana, intervalo e IDs de los eventos que justifican un positivo. |
| `proteins/*.parquet` | Eventos elegibles que habilitan el recorrido de cada parent en esa familia, incluidos los que justifican generar sus ventanas sin positivo local. |
| `evidence_verified/*.parquet` | Eventos simples verificados, identificadores de IEDB, datos experimentales y método de resolución. |
| `evidence_pending/*.parquet` | Eventos modificados, química indeterminada o evidencia simple pendiente, con el motivo de exclusión. |
| `holdouts/*.parquet` | Intervalos reservados sin etiqueta y sus IDs de evidencia excluida. Solo se registran para pares elegibles. |
| `references/*.parquet` | Secuencias de referencia, versiones, procedencia y hashes. |
| `global_index.parquet` | Una fila por secuencia exacta. Basta un positivo válido en cualquier familia para que la etiqueta global sea 1. |
| `summary.json` | Recuentos por familia, cobertura de evidencias y validación de intervalos, etiquetas y procedencia. |

Un 0 por familia significa que la ventana generada carece de un epítopo simple verificado completo. Los eventuales candidatos simples pendientes aparecen señalados en la procedencia.

## Ejecución posterior

Desde la raíz del repositorio, en el entorno `nap_env`:

```bash
python -m unittest -v tests.test_rebuild_iedb
python -m data_pipeline.scripts.rebuild_iedb.rebuild \
  --pilot data_pipeline/scripts/rebuild_iedb/pilot_selection.json \
  --output results/iedb_rebuild_v2_simple_pilot
python -m data_pipeline.scripts.rebuild_iedb.rebuild \
  --full --output results/iedb_rebuild_v2_simple_full
```

La CLI lee el archivo IEDB y las referencias configuradas en `--archive`, `--fasta`, `--prior` y `--old`. Consulta las referencias o entidades que falten en caché. La reanudación usa el mismo comando y directorio, con las mismas entradas. El destino v2 debe ser distinto de los originales y de cualquier ejecución v1.

## Fase 1 con estructura secundaria archivada

Pasa `--structure-dir` con los dos CSV `secondary_struct_human.csv` y
`secondary_struct_mouse.csv`. Se reutiliza el recorte C/H/E de la
predicción completa cuando coinciden organismo, URL y secuencia completa
de una referencia versionada del archivo. El identificador de predicción
es el SHA-256 de la secuencia completa, un salto de línea y su cadena
estructural completa. El formato histórico no registra una huella de
los pesos de ProteinUnet.

El Parquet de ventanas incluye `secondary_structure`,
`structure_prediction_id` y `structure_status`. Las ventanas cuyo
artefacto falta, discrepa o es ambiguo conservan sus etiquetas, con
estructura nula y motivo explícito. La columna `structure_status` de
`proteins/` permite localizar los parents afectados. El agregado global
cuenta pares distintos de secuencia primaria y recorte C/H/E verificado.

`--curated-cache` puede repetirse para recuperar resultados IEDB y FASTA de las
auditorías existentes. Las consultas que falten se almacenan en el destino
nuevo. El informe de un destino ya validado se genera con:

```bash
python -m data_pipeline.scripts.rebuild_iedb.phase1_report results/nap_cnb_v2_phase1
```
