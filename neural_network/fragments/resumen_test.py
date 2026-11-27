#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resumen_test.py — La tabla de TEST de los brazos ya puntuados.

Deliberadamente separado de `resumen_entrenamiento.py`, que solo mira
VALIDATION. Mezclar las dos particiones en un mismo CSV es la forma mas facil
de citar dentro de seis meses un numero de TEST creyendo que era de VALIDATION,
o al contrario. Cada fila lleva su columna `particion`.

QUE IMPRIME
-----------
  1. La tabla de brazos x modelos en TEST (ROC-AUC, AP, lift).
  2. **VALIDATION frente a TEST para el mismo modelo.** Es la comprobacion que
     da sentido a haber elegido la epoca en VALIDATION: si TEST cae mucho por
     debajo, la eleccion de epoca se habia ajustado al ruido de VALIDATION.
  3. El efecto del mean pooling en TEST (`*_residuo` frente a `*_pooled`), que
     es el control de §0.18.1.
  4. Desglose por familia y por especie del modelo que se indique.

**Puntuar los diez brazos en TEST es una tabla de ablacion legitima, pero la
configuracion primaria tiene que haber quedado fijada antes, en VALIDATION.**
Elegir a posteriori el mejor de los diez segun TEST seria seleccionar sobre
TEST por la puerta de atras (§0.18.2). Esta herramienta no elige nada: informa.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P neural_network/fragments/resumen_test.py results/w21_*
    $P neural_network/fragments/resumen_test.py --modelo mlp_residuo results/w21_*
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

MODELOS = ["lr_pooled", "lr_residuo", "mlp_pooled", "mlp_residuo"]


def lee(d: Path) -> tuple[list[dict], list[dict]]:
    """Devuelve (filas agregadas, filas de desglose) de un directorio."""
    p = d / "resultado.json"
    if not p.exists():
        return [], []
    r = json.loads(p.read_text())
    if not r.get("test"):
        return [], []
    agg, des = [], []
    for k in MODELOS:
        t = r["test"].get(k)
        if not t:
            continue
        v = r.get("mejor_por_modelo", {}).get(k, {}).get("validation", {})
        agg.append({
            "ejecucion": d.name, "modelo": k, "particion": "TEST",
            "epoca_elegida_en_val": r.get("mejor_por_modelo", {})
                                     .get(k, {}).get("epoca"),
            "n_test": t.get("n"),
            "test_prevalencia": t.get("prevalencia"),
            "test_roc_auc": t.get("roc_auc"), "test_ap": t.get("ap"),
            "test_lift": t.get("lift_ap"), "test_mcc": t.get("mcc"),
            "test_recall": t.get("recall"),
            "test_especificidad": t.get("specificity"),
            "test_precision": t.get("precision"),
            "val_roc_auc": v.get("roc_auc"), "val_ap": v.get("ap"),
        })
        for por in ("familia", "especie"):
            for g, s in t.get(f"por_{por}", {}).items():
                des.append({"ejecucion": d.name, "modelo": k,
                            "particion": "TEST", "por": por, "grupo": g,
                            "n_test": s.get("n"),
                            "test_prevalencia": s.get("prevalencia"),
                            "test_roc_auc": s.get("roc_auc"),
                            "test_ap": s.get("ap"),
                            "test_lift": s.get("lift_ap")})
    return agg, des


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--modelo", default="mlp_residuo",
                    help="modelo para el desglose por familia y especie")
    args = ap.parse_args()

    dirs = [Path(d) for d in args.dirs]
    agg, des = [], []
    for d in dirs:
        a, s = lee(d)
        agg += a
        des += s
    if not agg:
        print("ningun directorio tiene TEST puntuado todavia "
              "(resultado.json sin la clave 'test')")
        return 0
    A = pd.DataFrame(agg)
    D = pd.DataFrame(des)

    print("######## TEST por brazo y modelo ########")
    for val, etiqueta in (("test_roc_auc", "ROC-AUC"), ("test_ap", "AP")):
        print(f"\n{etiqueta}:")
        print(A.pivot_table(index="ejecucion", columns="modelo", values=val)
              .reindex(columns=MODELOS).round(4).to_string())

    print("\n######## VALIDATION frente a TEST ########")
    print("Si TEST cae claramente por debajo, la epoca se eligio sobre el "
          "ruido de VALIDATION.\n")
    cmp = A.assign(d_roc=A.test_roc_auc - A.val_roc_auc,
                   d_ap=A.test_ap - A.val_ap)
    print(cmp[["ejecucion", "modelo", "epoca_elegida_en_val", "val_roc_auc",
               "test_roc_auc", "d_roc", "val_ap", "test_ap", "d_ap"]]
          .round(4).to_string(index=False))

    print("\n######## el control de mean pooling, en TEST ########")
    print("`residuo` frente a `pooled`: mismos datos, misma particion, mismo "
          "scaler y los mismos lotes, de modo que la diferencia aisla el "
          "efecto de NO promediar las w posiciones (§0.18.1).")
    roc = A.pivot_table(index="ejecucion", columns="modelo",
                        values="test_roc_auc")
    ap_ = A.pivot_table(index="ejecucion", columns="modelo", values="test_ap")
    for fam, res, pool in (("lr", "lr_residuo", "lr_pooled"),
                           ("mlp", "mlp_residuo", "mlp_pooled")):
        if res not in roc.columns or pool not in roc.columns:
            continue
        t = pd.DataFrame({
            "residuo ROC": roc[res], "pooled ROC": roc[pool],
            "d ROC": roc[res] - roc[pool],
            "residuo AP": ap_[res], "pooled AP": ap_[pool],
            "d AP": ap_[res] - ap_[pool]})
        print(f"\n{fam}:")
        print(t.round(4).to_string())

    if not D.empty:
        sub = D[D.modelo == args.modelo]
        for por in ("familia", "especie"):
            s = sub[sub["por"] == por]
            if s.empty:
                continue
            print(f"\n######## {args.modelo}: TEST por {por} ########")
            t = s.pivot_table(index=["grupo", "n_test", "test_prevalencia"],
                              columns="ejecucion", values="test_roc_auc")
            print(t.round(4).sort_index(
                level="n_test", ascending=False).to_string())

    raiz = dirs[0].parent
    A.to_csv(raiz / "resumen_TEST_agregado.csv", index=False)
    D.to_csv(raiz / "resumen_TEST_desglosado.csv", index=False)
    print(f"\nCSV: {raiz/'resumen_TEST_agregado.csv'}, "
          f"{raiz/'resumen_TEST_desglosado.csv'}")
    print("Estas metricas son de TEST, puntuado una vez con los pesos elegidos "
          "en VALIDATION. La configuracion primaria se fijo antes de mirarlas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
