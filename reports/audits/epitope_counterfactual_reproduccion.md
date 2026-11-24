# Reproducir la auditoría contrafactual

Desde la raíz del repositorio y con el entorno `nap_env`, estos scripts reconstruyen la recuperación, el control de positivos existentes y el cálculo contrafactual. Usan los CSV y Parquet archivados de solo lectura. Los resultados y las respuestas de la API quedan en `results/epitope_counterfactual_20261118`. Las consultas se omiten cuando se dispone de la caché ya guardada.

```bash
export PYTHONPATH="$PWD"
audit=results/epitope_counterfactual_20261118/reproduction
python "$audit/epitope_counterfactual.py"
python "$audit/epitope_retry_source.py"
python "$audit/epitope_uniprot_source.py"
python "$audit/epitope_counterfactual_impact.py" baseline
python "$audit/epitope_counterfactual_finalize.py"
```

La segunda etapa puede ejecutarse de forma independiente. La etapa final necesita las otras dos. Los archivos CSV son resultados de auditoría y no sustituyen a ninguna tabla de entrenamiento.
