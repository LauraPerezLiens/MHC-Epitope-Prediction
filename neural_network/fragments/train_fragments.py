#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
train_fragments.py — Regresion logistica y MLP sobre los fragmentos, por residuo
y con el control de mean pooling.

QUE ENTRENA, Y POR QUE LOS CUATRO A LA VEZ
------------------------------------------
Una sola pasada por los datos entrena **cuatro modelos**:

  `lr_residuo`    Linear(w*dim -> 1)                 lineal sobre (w, 1024)
  `mlp_residuo`   w*dim -> 512 -> 128 -> 1           la forma del MLP historico
  `lr_pooled`     Linear(dim -> 1)                   CONTROL con mean pooling
  `mlp_pooled`    dim -> 512 -> 128 -> 1             CONTROL con mean pooling

No es por ahorrar lineas: **el cuello de botella es la entrada/salida, no la
GPU**. Una epoca mueve ~107 GB de embeddings fp16 desde el disco; el paso
adelante y atras del MLP son del orden de 1,6e14 FLOP, unos pocos segundos en
una 3090. Entrenar los cuatro en la misma pasada no cuesta practicamente nada
mas y, de paso, **garantiza que los cuatro ven exactamente los mismos lotes en
el mismo orden**, lo que hace la comparacion mas estrecha de lo que seria con
cuatro ejecuciones independientes.

EL CONTROL DE MEAN POOLING ES EL QUE DA SENTIDO A TODO LO DEMAS
---------------------------------------------------------------
Sin el, «mejor que el historico» no se puede sostener: han cambiado a la vez
los datos (fragmentos centrados en lugar de ventanas deslizantes), la particion
(componentes en lugar de filas) y la representacion (por residuo en lugar de
promediada). El control promedia las `w` posiciones y deja la representacion
historica sobre los datos nuevos, de modo que **la diferencia entre
`*_residuo` y `*_pooled` aisla el efecto de no promediar**, y solo eso.

Dos avisos sobre el control, para que nadie lo lea como una reproduccion exacta
del pipeline historico:

  1. El promedio es sobre los `w` residuos y **NO incluye el token `</s>`**. El
     historico SI lo incluia (§0.11.2, `prott5_v2.py:121`), un 3,8 % del vector
     en una ventana de 25. El vector del EOS esta guardado aparte si alguna vez
     se quiere reproducir bit a bit.
  2. En el brazo `primary_secondary`, promediar los 3 canales one-hot da la
     **fraccion de C/H/E en la ventana**, que es exactamente la feature que
     §0.2 midio con regresion logistica: 0,592364 de ROC-AUC. Es un punto de
     anclaje con un numero ya publicado en el proyecto.

PROTOCOLO: LAS CUATRO COSAS QUE §0.8 ENCONTRO MAL EN EL MLP HISTORICO
---------------------------------------------------------------------
  1. **Particion por componentes**, no por fila. Viene dada en `splits.parquet`
     y esta certificada sin fuga de fragmento ni de proteina (§0.14.4).
  2. **Seleccion por VALIDATION**, nunca por TEST. El historico seleccionaba
     `BEST by TEST STAGE loss` y su rama correcta era codigo inalcanzable.
  3. **Evaluacion a prevalencia natural**, no 50/50 forzado. Un ROC-AUC a 50/50
     no es comparable ni con el 0,68 honesto ni con el 0,865 de Wert2021.
  4. **AP (average precision) ademas de ROC-AUC**, y el *lift* sobre la
     prevalencia. El script historico no importaba `average_precision_score` en
     ninguna parte, de modo que no podia producir la metrica con la que el
     proyecto compara.

**TEST solo se puntua con `--test`, y la idea es hacerlo una vez, con la
configuracion que haya ganado en VALIDATION.** Puntuar los 16 modelos de la
matriz en TEST y quedarse con el mejor seria seleccionar sobre TEST por la
puerta de atras.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    CUDA_VISIBLE_DEVICES=2 $P -u neural_network/fragments/train_fragments.py \\
        --fragments data/fragments_w21_ss --embeddings data/embeddings_prott5_w21 \\
        --splits data/splits_w21/splits.parquet \\
        --scaler data/scalers_w21/scaler_sin_contradicciones.npz \\
        --features primary --excluir-contradictorios \\
        --out results/fragments_w21_primary_limpio
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "data_pipeline/scripts/embeddings/primary_structure"))
from fragment_dataset import FragmentDataset  # noqa: E402

DIM_PROTT5 = 1024


def _git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------- modelos
def construye_modelos(nn, dim_plano: int, dim_pool: int, dropout: float):
    def mlp(d):
        return nn.Sequential(
            nn.Linear(d, 512), nn.LayerNorm(512), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(512, 128), nn.LayerNorm(128), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(128, 1))
    return {
        "lr_residuo": nn.Linear(dim_plano, 1),
        "mlp_residuo": mlp(dim_plano),
        "lr_pooled": nn.Linear(dim_pool, 1),
        "mlp_pooled": mlp(dim_pool),
    }


# -------------------------------------------------------------------- metricas
def metricas(y: np.ndarray, logit: np.ndarray) -> dict:
    from sklearn.metrics import (average_precision_score, confusion_matrix,
                                 log_loss, matthews_corrcoef, roc_auc_score)
    p = 1.0 / (1.0 + np.exp(-logit.astype(np.float64)))
    prev = float(y.mean())
    out = {"n": int(len(y)), "prevalencia": prev}
    if 0.0 < prev < 1.0:
        out["roc_auc"] = float(roc_auc_score(y, p))
        ap = float(average_precision_score(y, p))
        out["ap"] = ap
        out["lift_ap"] = ap / prev
        out["log_loss"] = float(log_loss(y, np.clip(p, 1e-7, 1 - 1e-7)))
        pred = (p >= 0.5).astype(np.int8)
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        out.update(
            accuracy=float((tp + tn) / len(y)),
            precision=float(tp / (tp + fp)) if tp + fp else 0.0,
            recall=float(tp / (tp + fn)) if tp + fn else 0.0,
            specificity=float(tn / (tn + fp)) if tn + fp else 0.0,
            mcc=float(matthews_corrcoef(y, pred)),
            tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp))
    return out


def desglose(tabla: pd.DataFrame, idx: np.ndarray, y: np.ndarray,
             logit: np.ndarray, por: str) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score
    p = 1.0 / (1.0 + np.exp(-logit.astype(np.float64)))
    g = pd.DataFrame({"k": tabla[por].to_numpy()[idx], "y": y, "p": p})
    out = {}
    for k, sub in g.groupby("k", observed=True):
        prev = float(sub.y.mean())
        d = {"n": int(len(sub)), "prevalencia": prev}
        if 0.0 < prev < 1.0:
            d["roc_auc"] = float(roc_auc_score(sub.y, sub.p))
            d["ap"] = float(average_precision_score(sub.y, sub.p))
            d["lift_ap"] = d["ap"] / prev
        out[str(k)] = d
    return out


# ------------------------------------------------------------------ principal
def main() -> int:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--fragments", required=True)
    ap_.add_argument("--embeddings", required=True)
    ap_.add_argument("--splits", required=True)
    ap_.add_argument("--scaler", required=True, type=Path)
    ap_.add_argument("--out", required=True, type=Path)
    ap_.add_argument("--features", choices=("primary", "primary_secondary"),
                     default="primary")
    ap_.add_argument("--excluir-contradictorios", action="store_true")
    ap_.add_argument("--epochs", type=int, default=12)
    ap_.add_argument("--batch", type=int, default=2048)
    ap_.add_argument("--lr", type=float, default=1e-3)
    ap_.add_argument("--weight-decay", type=float, default=0.01)
    ap_.add_argument("--dropout", type=float, default=0.30)
    ap_.add_argument("--paciencia", type=int, default=3)
    ap_.add_argument("--seed", type=int, default=42)
    ap_.add_argument("--chunks-en-memoria", type=int, default=16)
    ap_.add_argument("--max-lotes", type=int, default=0,
                     help="solo para pruebas de humo; 0 = la epoca completa")
    ap_.add_argument("--test", action="store_true",
                     help="puntuar TEST. Hacerlo UNA vez, con la configuracion "
                          "ganadora en VALIDATION (§13.9)")
    args = ap_.parse_args()

    import torch
    from torch import nn

    if not torch.cuda.is_available():
        print("ERROR: sin CUDA", file=sys.stderr)
        return 2
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    dev = torch.device("cuda")
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"GPU: {torch.cuda.get_device_name(0)} "
          f"(CUDA_VISIBLE_DEVICES fija cual es)", flush=True)

    # --- scaler, ajustado en TRAIN y congelado ---
    sc = np.load(args.scaler)
    media = torch.tensor(sc["mean_canal"], dtype=torch.float32, device=dev)
    desv = torch.tensor(sc["std_canal"], dtype=torch.float32, device=dev)
    # Estandarizar el promedio equivale a promediar lo estandarizado y
    # reescalar por std_canal/std_pool: promediar w valores correlacionados
    # encoge la desviacion, y sin corregirlo el brazo pooled entraria con
    # features de std ~0,31 frente a 1.
    factor_pool = torch.tensor(sc["std_canal"] / sc["std_pool"],
                               dtype=torch.float32, device=dev)
    print(f"scaler: {args.scaler.name} | std media {float(desv.mean()):.4f} | "
          f"correccion de pooling mediana {float(factor_pool.median()):.4f}",
          flush=True)

    # --- datos ---
    comun = dict(fragments=args.fragments, embeddings=args.embeddings,
                 splits=args.splits, features=args.features,
                 excluir_contradictorios=args.excluir_contradictorios)
    print("TRAIN:", flush=True)
    tr = FragmentDataset(split="train", **comun)
    print("VALIDATION:", flush=True)
    va = FragmentDataset(split="val", **comun)
    te = None
    if args.test:
        print("TEST:", flush=True)
        te = FragmentDataset(split="test", **comun)
    w, dim = tr.w, tr.dim
    dim_plano = w * dim

    modelos = construye_modelos(nn, dim_plano, dim, args.dropout)
    modelos = {k: m.to(dev) for k, m in modelos.items()}
    opt = {k: torch.optim.AdamW(m.parameters(), lr=args.lr,
                                weight_decay=args.weight_decay)
           for k, m in modelos.items()}
    perdida = nn.BCEWithLogitsLoss()
    for k, m in modelos.items():
        print(f"  {k:14s} {sum(p.numel() for p in m.parameters()):>12,} parametros",
              flush=True)

    def prepara(Xb):
        """fp16 del disco -> float32 estandarizado; vista plana y promediada."""
        X = Xb.to(dev, non_blocking=True).float()
        X[:, :, :DIM_PROTT5] = (X[:, :, :DIM_PROTT5] - media) / desv
        plano = X.reshape(X.shape[0], -1)
        pool = X.mean(dim=1)
        pool[:, :DIM_PROTT5] = pool[:, :DIM_PROTT5] * factor_pool
        return {"lr_residuo": plano, "mlp_residuo": plano,
                "lr_pooled": pool, "mlp_pooled": pool}

    @torch.no_grad()
    def evalua(ds, nombre):
        for m in modelos.values():
            m.eval()
        ys, idxs = [], []
        logits = {k: [] for k in modelos}
        for Xb, yb, ib in ds.batches(batch_size=args.batch, shuffle=False,
                                     chunks_en_memoria=args.chunks_en_memoria,
                                     dtype=np.float16, indices=True):
            ent = prepara(torch.from_numpy(Xb))
            for k, m in modelos.items():
                logits[k].append(m(ent[k]).squeeze(1).float().cpu().numpy())
            ys.append(yb)
            idxs.append(ib)
        y = np.concatenate(ys)
        idx = np.concatenate(idxs)
        res = {}
        for k in modelos:
            lg = np.concatenate(logits[k])
            res[k] = metricas(y, lg)
            res[k]["por_familia"] = desglose(ds.tabla, idx, y, lg, "familia")
            res[k]["por_especie"] = desglose(ds.tabla, idx, y, lg, "especie")
        print(f"  [{nombre}] " + " | ".join(
            f"{k} AP {res[k].get('ap', float('nan')):.4f} "
            f"ROC {res[k].get('roc_auc', float('nan')):.4f}" for k in modelos),
            flush=True)
        return res

    hist = (args.out / "history.jsonl").open("a")
    mejor = {k: {"ap": -1.0, "epoca": None} for k in modelos}
    sin_mejora = 0
    t0 = time.time()

    for ep in range(1, args.epochs + 1):
        for m in modelos.values():
            m.train()
        acum = {k: 0.0 for k in modelos}
        nlotes = 0
        t_ep = time.time()
        for Xb, yb in tr.batches(batch_size=args.batch, shuffle=True,
                                 seed=args.seed + ep,
                                 chunks_en_memoria=args.chunks_en_memoria,
                                 dtype=np.float16):
            ent = prepara(torch.from_numpy(Xb))
            yt = torch.from_numpy(yb).to(dev, non_blocking=True)
            for k, m in modelos.items():
                opt[k].zero_grad(set_to_none=True)
                l = perdida(m(ent[k]).squeeze(1), yt)
                l.backward()
                opt[k].step()
                acum[k] += float(l.detach())
            nlotes += 1
            if nlotes % 200 == 0:
                vel = nlotes * args.batch / (time.time() - t_ep)
                print(f"  epoca {ep} lote {nlotes:,} | {vel:,.0f} ej/s | "
                      + " ".join(f"{k} {acum[k]/nlotes:.4f}" for k in modelos),
                      flush=True)
            if args.max_lotes and nlotes >= args.max_lotes:
                break

        tren = {k: acum[k] / max(nlotes, 1) for k in modelos}
        print(f"epoca {ep} | {nlotes:,} lotes | {time.time()-t_ep:.0f} s | "
              f"perdida TRAIN " + " ".join(f"{k} {v:.4f}" for k, v in tren.items()),
              flush=True)
        val = evalua(va, f"VAL epoca {ep}")
        hist.write(json.dumps({"type": "epoch_end", "epoca": ep,
                               "segundos": round(time.time() - t_ep, 1),
                               "perdida_train": tren, "validation": val}) + "\n")
        hist.flush()

        avanza = False
        for k in modelos:
            if val[k].get("ap", -1) > mejor[k]["ap"]:
                mejor[k] = {"ap": val[k]["ap"], "epoca": ep, "validation": val[k]}
                torch.save(modelos[k].state_dict(), args.out / f"best_{k}.pt")
                avanza = True
        sin_mejora = 0 if avanza else sin_mejora + 1
        if sin_mejora >= args.paciencia:
            print(f"parada temprana: {sin_mejora} epocas sin mejorar el AP de "
                  f"VALIDATION en ningun modelo", flush=True)
            break

    print("\n=== mejor epoca por modelo, elegida en VALIDATION ===")
    for k, v in mejor.items():
        m = v.get("validation", {})
        print(f"  {k:14s} epoca {v['epoca']} | AP {v['ap']:.6f} | "
              f"ROC-AUC {m.get('roc_auc', float('nan')):.6f} | "
              f"lift {m.get('lift_ap', float('nan')):.3f}")

    res_test = None
    if te is not None:
        print("\nTEST (una sola vez, con los pesos elegidos en VALIDATION):")
        import torch as _t
        for k, m in modelos.items():
            m.load_state_dict(_t.load(args.out / f"best_{k}.pt"))
        res_test = evalua(te, "TEST")

    man = {
        "generado_por": "neural_network/fragments/train_fragments.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(),
        "argumentos": {k: (str(v) if isinstance(v, Path) else v)
                       for k, v in vars(args).items()},
        "sha256_scaler": _sha256(args.scaler),
        "ventana": int(w), "dim_entrada": int(dim), "dim_plano": int(dim_plano),
        "filas": {"train": len(tr), "val": len(va),
                  "test": (len(te) if te is not None else None)},
        "prevalencia": {"train": float(tr.tabla.label.mean()),
                        "val": float(va.tabla.label.mean()),
                        "test": (float(te.tabla.label.mean())
                                 if te is not None else None)},
        "parametros": {k: sum(p.numel() for p in m.parameters())
                       for k, m in modelos.items()},
        "metrica_de_seleccion": "average precision en VALIDATION",
        "protocolo": ("particion por componentes proteina-fragmento; seleccion "
                      "por VALIDATION; evaluacion a prevalencia natural; AP y "
                      "lift reportados ademas de ROC-AUC"),
        "mean_pooling_control": ("promedio sobre los w residuos, SIN el token "
                                 "</s>, que el pipeline historico SI incluia"),
        "mejor_por_modelo": mejor,
        "test": res_test,
        "segundos_totales": round(time.time() - t0, 1),
    }
    (args.out / "resultado.json").write_text(json.dumps(man, indent=2,
                                                        ensure_ascii=False))
    hist.close()
    print(f"\nSalida: {args.out}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
