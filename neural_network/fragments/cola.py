#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cola.py — La matriz de brazos de §0.16, definida UNA vez, y su ejecucion por
olas en dos GPU.

POR QUE ESTE FICHERO EXISTE
---------------------------
La matriz de w21 se lanzo el 25 de noviembre con una cola ad hoc que no estaba
versionada y que **informaba `codigo 0` para brazos que habian terminado con un
traceback** (los dos de la ola D, que cascaron al escribir `resultado.json`).
Una cola que no ve los fallos es peor que el fallo: el registro dice que todo
fue bien. Aqui el codigo de salida de cada brazo se comprueba, se registra y
decide el codigo de salida de la cola entera.

La otra razon es que los brazos son **argumentos**, no datasets distintos
(§0.16), de modo que la matriz es una tabla y la ventana es un parametro. La
misma definicion sirve para entrenar w21, puntuar su TEST y correr w25.

LAS CINCO OLAS
--------------
  A  primary / primary_secondary, sin contradicciones   la referencia
  B  las mismas CON contradicciones                     cuanto cuestan (§0.13)
  C  primary_sbert, las dos                             SecondaryBERT por residuo
  D  sbert / secondary por separado                     ablacion por modalidad
  E  primary / primary_secondary al 50/50               el balanceo (§0.18.5)

DOS MODOS
---------
  `--modo entrenar`  entrena y elige epoca por AP de VALIDATION.
  `--modo test`      NO entrena: carga los best_*.pt que ya estan en disco y
                     puntua TEST con ellos (`--solo-test`). Es lo que hace que
                     puntuar TEST cueste minutos en lugar de repetir las ~11 h
                     de entrenamiento por brazo.

**TEST se puntua una vez y la configuracion se elige antes, en VALIDATION.**
Puntuar los diez brazos en TEST es legitimo como tabla de ablacion, pero solo
si la configuracion primaria ya estaba fijada: elegir a posteriori el mejor de
los diez en TEST seria seleccionar sobre TEST por la puerta de atras (§0.18.2).

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u neural_network/fragments/cola.py --ventana 21 --modo test
    $P -u neural_network/fragments/cola.py --ventana 25 --modo entrenar
    $P -u neural_network/fragments/cola.py --ventana 21 --modo test --olas D
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PY = "/home/nap/miniconda3/envs/nap_env/bin/python"
ENTRENA = "neural_network/fragments/train_fragments.py"

# (ola, sufijo del nombre, features, excluir contradictorios, frac_pos)
MATRIZ = [
    ("A", "primary_limpio",        "primary",           True,  None),
    ("A", "primsec_limpio",        "primary_secondary", True,  None),
    ("B", "primary_contra",        "primary",           False, None),
    ("B", "primsec_contra",        "primary_secondary", False, None),
    ("C", "primsbert_limpio",      "primary_sbert",     True,  None),
    ("C", "primsbert_contra",      "primary_sbert",     False, None),
    ("D", "sbert_limpio",          "sbert",             True,  None),
    ("D", "secondary_limpio",      "secondary",         True,  None),
    ("E", "primary_limpio_5050",   "primary",           True,  0.5),
    ("E", "primsec_limpio_5050",   "primary_secondary", True,  0.5),
]

# Los brazos sin ProtT5 no llevan scaler (one-hot es 0/1 y SecondaryBERT sale
# de un LayerNorm), y los que no usan SecondaryBERT no necesitan su tensor.
SIN_PROTT5 = {"sbert", "secondary"}
CON_SBERT = {"primary_sbert", "sbert"}


def comando(w: int, nombre: str, features: str, limpio: bool,
            frac_pos: float | None, modo: str) -> list[str]:
    out = f"results/w{w}_{nombre}"
    cmd = [PY, "-u", ENTRENA,
           "--fragments", f"data/fragments_w{w}_ss",
           "--embeddings", f"data/embeddings_prott5_w{w}",
           "--splits", f"data/splits_w{w}/splits.parquet",
           "--features", features, "--out", out]
    if features not in SIN_PROTT5:
        sufijo = "sin" if limpio else "con"
        cmd += ["--scaler",
                f"data/scalers_w{w}/scaler_{sufijo}_contradicciones.npz"]
    if features in CON_SBERT:
        cmd += ["--embeddings-sbert", f"data/embeddings_sbert_w{w}"]
    if limpio:
        cmd += ["--excluir-contradictorios"]
    if frac_pos is not None:
        cmd += ["--frac-pos", str(frac_pos)]
    cmd += ["--solo-test"] if modo == "test" else []
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ventana", type=int, required=True, choices=(21, 25))
    ap.add_argument("--modo", required=True, choices=("entrenar", "test"))
    ap.add_argument("--olas", default="ABCDE",
                    help="letras de las olas a correr, p. ej. AB o D")
    ap.add_argument("--gpus", default="0,1",
                    help="§0.0.4: dos como maximo, y una libre siempre")
    ap.add_argument("--log", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    w = args.ventana
    gpus = [g.strip() for g in args.gpus.split(",") if g.strip()]
    if len(gpus) > 2:
        print("ERROR: §0.0.4 limita a dos GPU", file=sys.stderr)
        return 2

    brazos = [b for b in MATRIZ if b[0] in args.olas.upper()]
    if not brazos:
        print(f"ERROR: ninguna ola coincide con {args.olas!r}", file=sys.stderr)
        return 2

    sufijo = "test" if args.modo == "test" else "train"
    log = Path(args.log or f"logs/cola_w{w}_{sufijo}.log")
    log.parent.mkdir(parents=True, exist_ok=True)

    if args.modo == "test":
        faltan = [f"results/w{w}_{b[1]}" for b in brazos
                  if not (RAIZ / f"results/w{w}_{b[1]}"
                          / "best_mlp_residuo.pt").exists()]
        if faltan:
            print("ERROR: --modo test necesita los best_*.pt ya entrenados; "
                  f"no estan en: {faltan}", file=sys.stderr)
            return 2

    def marca(texto: str) -> None:
        linea = f"[{datetime.now():%H:%M:%S}] {texto}"
        print(linea, flush=True)
        with log.open("a") as fh:
            fh.write(linea + "\n")

    marca(f"cola w{w} modo {args.modo} | olas {args.olas.upper()} | "
          f"{len(brazos)} brazos | GPU {','.join(gpus)}")

    pendientes = list(brazos)
    corriendo: dict[str, tuple] = {}          # gpu -> (nombre, Popen, fh, t0)
    resultados: list[tuple[str, int, float]] = []

    while pendientes or corriendo:
        for g in gpus:
            if g in corriendo or not pendientes:
                continue
            ola, nombre, features, limpio, frac = pendientes.pop(0)
            cmd = comando(w, nombre, features, limpio, frac, args.modo)
            if args.dry_run:
                marca(f"[seco] ola {ola} GPU {g}: {' '.join(cmd)}")
                resultados.append((f"w{w}_{nombre}", 0, 0.0))
                continue
            p_log = Path(f"logs/{sufijo}_w{w}_{nombre}.log")
            fh = p_log.open("a")
            fh.write(f"\n===== {datetime.now().isoformat()} | {' '.join(cmd)}\n")
            fh.flush()
            proc = subprocess.Popen(
                cmd, cwd=RAIZ, stdout=fh, stderr=subprocess.STDOUT,
                env={**__import__("os").environ, "CUDA_VISIBLE_DEVICES": g})
            corriendo[g] = (f"w{w}_{nombre}", proc, fh, time.time())
            marca(f"ola {ola} GPU {g} -> w{w}_{nombre} (pid {proc.pid}, "
                  f"log {p_log})")

        if not corriendo:
            continue
        time.sleep(5)
        for g, (nombre, proc, fh, t0) in list(corriendo.items()):
            rc = proc.poll()
            if rc is None:
                continue
            fh.close()
            del corriendo[g]
            mins = (time.time() - t0) / 60
            resultados.append((nombre, rc, mins))
            estado = "OK" if rc == 0 else f"FALLO codigo {rc}"
            marca(f"GPU {g} <- {nombre}: {estado} | {mins:.1f} min")

    fallos = [r for r in resultados if r[1] != 0]
    marca(f"RESUMEN: {len(resultados) - len(fallos)}/{len(resultados)} OK"
          + ("" if not fallos else
             " | FALLARON: " + ", ".join(f"{n} (codigo {c})"
                                         for n, c, _ in fallos)))
    if fallos:
        marca("COLA CON FALLOS")
        return 1
    marca(f"COLA w{w} {args.modo} COMPLETA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
