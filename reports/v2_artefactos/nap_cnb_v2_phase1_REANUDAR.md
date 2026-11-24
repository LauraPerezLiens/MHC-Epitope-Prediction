# Fase 1 pausada antes del apagado

La salida es parcial. Solo debe considerarse completa tras generar un `summary.json` validado y pasar la reconciliación global. Los JSON en `checkpoints/` indican qué escrituras de familia terminaron y se pueden reutilizar. Las validaciones globales y por familia se completan al reanudar.

Desde la raíz del repositorio:

```bash
conda activate nap_env
python -u -m data_pipeline.scripts.rebuild_iedb.rebuild \
  --full --output results/nap_cnb_v2_phase1 \
  --structure-dir results/nap_cnb_v2_phase1_structure \
  --curated-cache results/iedb_rebuild_v1_pilot_20261118/reference_cache \
  --curated-cache results/iedb_pending_evidence_20261118/cache \
  --curated-cache results/iedb_modified_audit_20261118/cache \
  >> results/nap_cnb_v2_phase1/run.log 2>&1
python -m data_pipeline.scripts.rebuild_iedb.phase1_report results/nap_cnb_v2_phase1
```

La revisión automática rechazó una recuperación que habría convertido fallos de red en falta de referencia y relanzado varios escritores en paralelo. Reanudar desde un solo proceso y mantener los errores transitorios explícitos.

## Recuperación completada el 19 de noviembre de 2026

Las once familias y el índice global se validaron. Los resultados están en [summary.json](summary.json) y [phase1_report.md](phase1_report.md). El registro de ejecución conserva el fallo de consulta, la reparación y los recuentos finales. Las bases SQLite de trabajo se retiraron tras verificar el Parquet y el informe.
