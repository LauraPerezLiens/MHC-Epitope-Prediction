# Auditoría de código NAP-CNB

Inicio en `ml_model_comparison`, commit `49c343b`, con árbol limpio. El análisis automatizado abarcó 144 archivos, con 47.121 líneas, y enumeró 510.113 rutas ignoradas. La revisión semántica exhaustiva sigue abierta. Se corrigió un fallo reproducible del lector histórico y se añadió una ruta de navegación para los contratos vigentes.

- [Inventario del snapshot](file_inventory.csv) y [cobertura de revisión](coverage.md)
- [Hallazgos y evidencia](findings.md)
- [Arquitectura](../../docs/README.md)
- [Registro de cambios](refactoring_changes.md), [validación](validation.md) y [pendientes](pending.md)

La MLP histórica estaba activa como PID 3348177 y siguió registrando progresos durante la auditoría. Usa las matrices concatenadas históricas, su scaler y el directorio de recuperación de su propia corrida. La LR histórica permaneció detenida. En la captura inicial había 80 CPU lógicas, 169 GiB de RAM disponible, unos 20 TiB libres en el filesystem de datos y 532 MiB de GPU ocupados por la MLP. La inspección de rutas ignoradas se limitó a los nombres.
