# Sensibilidad de Primary a un cambio de aminoácido

Prueba del 17 de noviembre de 2026. Se utilizaron embeddings ProtT5 existentes;
no se regeneraron embeddings ni se modificaron datasets, splits o scaler.

## Muestra

- 110 grupos: 10 por cada una de las 11 familias, en un chunk original aleatorio por familia; semilla 42.
- 2.750 pares original–variante: las 25 sustituciones conservadoras BLOSUM62 por grupo.
- Referencia: 495 pares de originales de grupos distintos de la misma familia y chunk, excluyendo secuencias iguales. Difieren en 19–25 posiciones (mediana 24); 155 pares pertenecen a la misma proteína. No representan necesariamente proteínas diferentes.

## Resultados

| Medida, mediana | Un aminoácido cambiado | Grupos distintos |
|---|---:|---:|
| Similitud coseno del vector original | 0,988318 | 0,433430 |
| Distancia L2 relativa a la norma del primer vector | 15,47 % | 107,88 % |
| Distancia L2 después del scaler del MLP | 6,5997 | 44,2879 |
| RMS de la diferencia después del scaler | 0,2062 | 1,3840 |

La distancia mediana después del scaler es aproximadamente 6,7 veces menor
para las sustituciones que para la referencia de grupos distintos. No hubo
ningún vector original–variante exactamente idéntico en los 2.750 pares.

El 90 % central de las distancias relativas original–variante está entre
7,46 % y 50,56 %. La similitud coseno mínima fue 0,24634: algunas sustituciones
produjeron desplazamientos grandes, pese a ser conservadoras según BLOSUM62.
La distancia relativa es `norm(variante-original)/norm(original)`; no es el
porcentaje de componentes modificadas ni el cambio de probabilidad del MLP.

## Interpretación y límites

En esta muestra las variantes suelen conservar embeddings próximos al original,
pero el efecto depende de la secuencia y la sustitución. Repartir variantes de
un grupo entre train y test permite evaluar ejemplos próximos a los de train;
no equivale a evaluar grupos nuevos. Esta prueba no cuantifica por sí sola
cuánto cambia la accuracy ni valida que las variantes conserven su etiqueta.

Las identidades/posiciones de las variantes se reconstruyeron usando el generador
BLOSUM62 conservado. Se verificaron el orden de 26 filas, grupo, proteína,
etiqueta y SHA-256 de los archivos descomprimidos. No se contrastaron las cadenas
mutantes leyendo independientemente el CSV aumentado archivado. Es un estudio
descriptivo de una muestra por familia, con pares dependientes, no una estimación
para todas las mutaciones posibles ni una predicción del efecto biológico.

## Archivos

- `mutation_pairs.csv`: cada sustitución, secuencias, proteína, grupos, posición y distancias.
- `reference_pairs.csv`: pares de referencia e información de proteína/secuencia.
- `summary.json`: cuantiles globales y resultados por familia.
- `comparison.png`: comparación gráfica; las cajas omiten los puntos atípicos.
- Script reproducible: `data_pipeline/scripts/measure_primary_mutations.py`.
