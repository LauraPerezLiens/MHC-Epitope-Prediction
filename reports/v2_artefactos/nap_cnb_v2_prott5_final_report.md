# NAP-CNB v2 · generación completa ProtT5

**Estado validado.** Se confirmaron **14,530,324 embeddings** para todas las primarias únicas de la selección definitiva. Cubren las **49.123.503 ventanas** mediante la clave de primaria exacta.

| Métrica | Resultado |
|---|---:|
| Inicio (Madrid) | 2026-11-19T13:41:26.456721+01:00 |
| Fin de validaciones (Madrid) | 2026-11-19T20:48:22.808435+01:00 |
| Tiempo total con comprobaciones | 7.116 h |
| Tiempo de generación y su verificación interna | 7.054 h |
| Ritmo medio de generación | 572.17 secuencias/s |
| GPU | RTX 3090 física 2 |
| Shards | 146 |
| Lotes SQLite confirmados | 56,814 |
| Archivo NPY total | 59,516,225,792 bytes |
| Almacén total | 59,523,387,389 bytes |
| VRAM pico asignada | 2.76 GiB |
| RAM residente pico | 4.03 GiB |

Checkpoint Rostlab ProtT5 `94a6abc029ae13029317b140b7424e012bf8dfbf`, lote 256, inferencia FP16, media FP32 y salida float32 de dimensión 1.024. La configuración del piloto coincide con el almacén completo. La revisión, hashes, entorno, inventario y código están fijados en el manifiesto.

La verificación de reapertura confirmó forma, tipo, finitud y digest vinculado a claves para todas las filas, con **cero inferencias nuevas**. El inventario de la selección pasó recuento, unicidad y verificación de SHA-256 sin colisiones observadas. Los 146 shards están presentes y los lotes confirmados cubren todas las filas esperadas. El registro original contiene el detalle de recursos y errores.

[Manifiesto](final/manifest.json) · [SQLite](final/progress.sqlite) · [Log de ejecución](full_run.log) · [Piloto histórico](pilot_report.md)
