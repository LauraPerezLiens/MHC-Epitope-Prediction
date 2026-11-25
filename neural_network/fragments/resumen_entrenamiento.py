#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resumen_entrenamiento.py — Lee los `history.jsonl` y saca tablas legibles.

`history.jsonl` tiene una linea de JSON por epoca con las metricas completas de
los cuatro modelos, incluido el desglose por familia y por especie. Es el
registro que §19 exige, pero no se puede leer a ojo. Esto lo convierte en
tablas por pantalla y en CSV.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u neural_network/fragments/resumen_entrenamiento.py \\
        results/fragments_w21_primary_limpio results/fragments_w21_primsec_limpio
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

MODELOS = ["lr_residuo", "mlp_residuo", "lr_pooled", "mlp_pooled"]


def por_epoca(d: Path) -> pd.DataFrame:
    filas = []
    p = d / "history.jsonl"
    if not p.exists():
        return pd.DataFrame()
    for linea in p.read_text().splitlines():
        if not linea.strip():
            continue
        r = json.loads(linea)
        if r.get("type") != "epoch_end":
            continue
        for k in MODELOS:
            v = r["validation"].get(k, {})
            filas.append({
                "ejecucion": d.name, "particion": "VALIDATION",
                "epoca": r["epoca"],
                "segundos": r.get("segundos"), "modelo": k,
                "perdida_train": round(r["perdida_train"].get(k, float("nan")), 6),
                "val_ap": round(v.get("ap", float("nan")), 6),
                "val_roc_auc": round(v.get("roc_auc", float("nan")), 6),
                "val_lift": round(v.get("lift_ap", float("nan")), 4),
                "val_perdida": round(v.get("log_loss", float("nan")), 6),
                "val_mcc": round(v.get("mcc", float("nan")), 6),
                "val_recall": round(v.get("recall", float("nan")), 6),
                "val_especificidad": round(v.get("specificity", float("nan")), 6),
                "val_prevalencia": round(v.get("prevalencia", float("nan")), 6),
                "n_val": v.get("n"),
            })
    return pd.DataFrame(filas)


def desglose(d: Path, por: str) -> pd.DataFrame:
    """Desglose de la ULTIMA epoca registrada, por familia o por especie."""
    p = d / "history.jsonl"
    if not p.exists():
        return pd.DataFrame()
    ultimo = None
    for linea in p.read_text().splitlines():
        if linea.strip():
            r = json.loads(linea)
            if r.get("type") == "epoch_end":
                ultimo = r
    if ultimo is None:
        return pd.DataFrame()
    filas = []
    for k in MODELOS:
        for grupo, v in ultimo["validation"].get(k, {}).get(f"por_{por}", {}).items():
            # `particion` va explicita en cada fila a proposito: estas metricas
            # son de VALIDATION y TEST esta congelado (§13.9). Sin la columna,
            # un CSV suelto dentro de dos semanas no dice de que particion es.
            filas.append({"ejecucion": d.name, "particion": "VALIDATION",
                          "epoca": ultimo["epoca"],
                          "modelo": k, por: grupo, "n_val": v.get("n"),
                          "val_prevalencia": round(v.get("prevalencia", float("nan")), 6),
                          "val_roc_auc": round(v.get("roc_auc", float("nan")), 6),
                          "val_ap": round(v.get("ap", float("nan")), 6),
                          "val_lift": round(v.get("lift_ap", float("nan")), 4)})
    return pd.DataFrame(filas)


def main() -> int:
    dirs = [Path(a) for a in sys.argv[1:]]
    if not dirs:
        print(__doc__)
        return 2
    ep = pd.concat([por_epoca(d) for d in dirs], ignore_index=True)
    if ep.empty:
        print("todavia no hay ninguna epoca cerrada")
        return 0

    for ejec, sub in ep.groupby("ejecucion"):
        print(f"\n######## {ejec} ########")
        t = sub.pivot_table(index="epoca", columns="modelo",
                            values=["val_ap", "val_roc_auc"])
        print("\nAP y ROC-AUC de VALIDATION por epoca:")
        print(t.round(4).to_string())
        print("\nmejor epoca por modelo (por AP de VALIDATION):")
        mej = sub.loc[sub.groupby("modelo").val_ap.idxmax()]
        print(mej[["modelo", "epoca", "val_ap", "val_roc_auc", "val_lift",
                   "val_mcc", "val_recall", "val_especificidad",
                   "val_prevalencia"]].to_string(index=False))

    for por in ("familia", "especie"):
        dg = pd.concat([desglose(d, por) for d in dirs], ignore_index=True)
        if dg.empty:
            continue
        print(f"\n######## desglose por {por}, ultima epoca ########")
        for ejec, sub in dg.groupby("ejecucion"):
            print(f"\n--- {ejec} ---")
            t = sub.pivot_table(index=[por, "n_val", "val_prevalencia"],
                                columns="modelo", values="val_roc_auc")
            print(t.round(4).sort_values("n_val", ascending=False).to_string())
        dg.to_csv(dirs[0].parent / f"resumen_VALIDATION_por_{por}.csv", index=False)

    ep.to_csv(dirs[0].parent / "resumen_VALIDATION_por_epoca.csv", index=False)
    print("\nTODAS estas metricas son de VALIDATION. TEST sigue congelado y solo "
          "se puntua con --test, una vez, con la configuracion ya elegida (§13.9).")
    print(f"CSV: {dirs[0].parent/'resumen_VALIDATION_por_epoca.csv'}, "
          f"{dirs[0].parent/'resumen_VALIDATION_por_familia.csv'}, "
          f"{dirs[0].parent/'resumen_VALIDATION_por_especie.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
