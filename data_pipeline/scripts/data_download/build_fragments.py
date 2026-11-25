#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_fragments.py — Fragmentos de proteina de longitud fija, positivos y senuelos.

DISENO, Y DE DONDE SALE
-----------------------
Decidido por Laura el 25 nov 2026, siguiendo el metodo de Wert2021 y no el de
la linea de TFG/TFM:

  * **Positivo**: ventana de `w` aa **centrada en el epitopo**, un fragmento por
    (familia, alelo, peptido). No es ventana deslizante: la deslizante genera
    vecinas con el 96 % de solape, lo que fabrica fuga y hace que el mismo
    fragmento sea positivo y negativo segun que subpeptido se mire.
  * **Senuelo**: la proteina madre con TODOS sus epitopos conocidos recortados,
    y el resto troceado en fragmentos consecutivos **sin solape** de `w` aa.
    Emparejados por longitud por construccion, y del mismo proteoma, de modo
    que el fondo es difícil: el modelo no puede acertar por composicion global
    ni por "esta proteina es de las que tienen epitopos".

La prevalencia no se elige: emerge de la longitud de las proteinas, igual que
el 2,67 % de Wert2021.

LOS SIETE DEFECTOS DE WERT QUE AQUI SE CORRIGEN
-----------------------------------------------
Su `peptides_extraction.py` tiene fallos verificados que este script evita:

 1. **Ventanas vacias en el extremo N.** Si el centro del epitopo esta a menos
    de w/2 del inicio, su indice inicial se vuelve negativo y Python devuelve
    `''`. Aqui la ventana se **desplaza hacia dentro** (clamp) para que SIEMPRE
    mida `w` exactos, y se marca con `desplazada`.
 2. **Positivos truncados en el extremo C**, por el mismo motivo. Igual: clamp.
 3. **Off-by-one al extirpar**: su `s2[:p1] + s2[p2+1:]` se come un residuo de
    mas. Aqui el corte es exacto.
 4. **Smith-Waterman tolerante**: colocaba el epitopo en algun sitio aunque no
    estuviera literalmente en la proteina. Aqui se usan las coordenadas de IEDB
    y **se verifica** que el peptido esta de verdad ahi; si no, se busca como
    subcadena exacta; si tampoco, se descarta y se cuenta.
 5. **Deduplicacion dependiente del orden**: si una ventana salia positiva en
    una proteina y negativa en otra, ganaba la que se procesara primero. Aqui
    **gana siempre el positivo**, por tener evidencia experimental, y el numero
    de colisiones se registra.
 6. **Se salta la primera proteina** del fichero a proposito (`if index == 0`).
    Aqui no se salta ninguna.
 7. **El ultimo trozo se descarta** sin mas. Aqui tambien se descarta, pero
    porque mide menos de `w` y hay que mantener la longitud fija; se cuenta.

ADEMAS
------
  * Los epitopos que se extirpan antes de trocear son **todos los de la familia**,
    de cualquier alelo. Es conservador a proposito: en un problema
    positive-unlabeled, convertir en negativo un peptido que es epitopo de otro
    alelo de la misma familia introduciria falsos negativos.
  * Los senuelos salen **sin alelo**. Emparejar senuelo con alelo es una
    decision de modelado, no de construccion de datos: para un modelo por alelo
    se emparejan aguas abajo con el alelo que se entrene.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    # configuracion de Laura: 15 aa en clase I, 20 en clase II
    $P -u data_pipeline/scripts/data_download/build_fragments.py \\
        --clean data/data_raw_full_20261124_clean \\
        --proteins data/parent_proteins_20261125/parent_proteins.parquet \\
        --out data/fragments_15_20 --w-class-i 15 --w-class-ii 20
    # linea base historica: 25 aa para las dos
    $P -u ... --out data/fragments_25_25 --w-class-i 25 --w-class-ii 25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


CANONICAL_AA = set("ACDEFGHIKLMNPQRSTVWY")


def _git_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
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


def localizar(seq: str, pep: str, start, end) -> tuple[int, int] | None:
    """Devuelve (i, j) 0-based semiabierto donde esta `pep` dentro de `seq`.

    Primero cree a IEDB: si las coordenadas declaradas contienen exactamente el
    peptido, se usan. Si no, se busca como subcadena exacta, porque las
    coordenadas de IEDB pueden referirse a otra isoforma. Si tampoco aparece,
    devuelve None y la fila se descarta: colocar el peptido donde no esta, como
    hacia el Smith-Waterman tolerante de Wert, produce un positivo mal centrado.
    """
    try:
        i = int(float(start)) - 1          # IEDB es 1-based inclusivo
        j = int(float(end))
        if 0 <= i < j <= len(seq) and seq[i:j] == pep:
            return i, j
    except (TypeError, ValueError):
        pass
    k = seq.find(pep)
    if k >= 0:
        return k, k + len(pep)
    return None


def ventana_centrada(n: int, i: int, j: int, w: int) -> tuple[int, int] | None:
    """Ventana de EXACTAMENTE `w` aa centrada en [i, j), ajustada a [0, n).

    Si la proteina es mas corta que `w`, devuelve None: no hay forma de dar una
    ventana de longitud fija, y truncar o rellenar introduciria un artefacto.
    """
    if n < w:
        return None
    centro = (i + j) // 2
    a = centro - w // 2
    a = max(0, min(a, n - w))             # clamp: desplaza hacia dentro
    return a, a + w


def trocear(seq: str, ocupados: list[tuple[int, int]], w: int) -> tuple[list[str], int]:
    """Trocea lo que queda de `seq` tras quitar `ocupados`, en trozos de `w`.

    `ocupados` son intervalos 0-based semiabiertos. Se fusionan los solapados,
    se recorren los huecos y cada hueco se parte en trozos consecutivos sin
    solape. Devuelve los trozos y cuantas colas se descartaron por medir < w.
    """
    if not ocupados:
        huecos = [(0, len(seq))]
    else:
        fus: list[list[int]] = []
        for a, b in sorted(ocupados):
            if fus and a <= fus[-1][1]:
                fus[-1][1] = max(fus[-1][1], b)
            else:
                fus.append([a, b])
        huecos, cur = [], 0
        for a, b in fus:
            if a > cur:
                huecos.append((cur, a))
            cur = max(cur, b)
        if cur < len(seq):
            huecos.append((cur, len(seq)))
    trozos, colas = [], 0
    for a, b in huecos:
        seg = seq[a:b]
        for k in range(0, len(seg) - len(seg) % w, w):
            trozos.append(seg[k:k + w])
        if len(seg) % w:
            colas += 1
    return trozos, colas


def una_familia(df: pd.DataFrame, prot: dict[str, str], w: int,
                familia: str, especie: str, clase: str) -> tuple[pd.DataFrame, dict]:
    """Construye positivos y senuelos de una familia."""
    acc = df["epitope__molecule_parent_iri"].map(
        lambda s: s.rsplit("/", 1)[-1] if isinstance(s, str) else None)
    df = df.assign(acc_base=acc)

    # Un positivo por (alelo, peptido): las filas repiten la misma medida.
    uni = df.drop_duplicates(["mhc_restriction__name", "epitope__name", "acc_base"])

    pos, ocupados = [], {}
    st = {"sin_proteina": 0, "no_localizado": 0, "proteina_corta": 0,
          "epitopo_mas_largo_que_la_ventana": 0, "fragmento_no_canonico": 0,
          "desplazadas": 0}
    for r in uni.itertuples(index=False):
        seq = prot.get(r.acc_base)
        if not seq:
            st["sin_proteina"] += 1
            continue
        loc = localizar(seq, r.epitope__name,
                        r.epitope__starting_position, r.epitope__ending_position)
        if loc is None:
            st["no_localizado"] += 1
            continue
        i, j = loc
        # El epitopo se extirpa para los senuelos aunque no genere positivo:
        # si no cabe en la ventana sigue siendo un epitopo conocido y no puede
        # aparecer como senuelo.
        ocupados.setdefault(r.acc_base, []).append((i, j))
        # Un epitopo mas largo que la ventana no cabe: la ventana centrada solo
        # contendria un trozo de el, y ese fragmento NO es el epitopo. Fuera.
        if j - i > w:
            st["epitopo_mas_largo_que_la_ventana"] += 1
            continue
        v = ventana_centrada(len(seq), i, j, w)
        if v is None:
            st["proteina_corta"] += 1
            continue
        a, b = v
        # La proteina de UniProt puede traer X, U, B o Z, que el filtro de
        # peptido canonico no veia porque actuaba sobre el epitopo, no sobre
        # el fragmento. Un fragmento con un residuo ambiguo no es utilizable.
        if not set(seq[a:b]) <= CANONICAL_AA:
            st["fragmento_no_canonico"] += 1
            continue
        centro_ideal = (i + j) // 2 - w // 2
        if a != centro_ideal:
            st["desplazadas"] += 1
        pos.append({
            "fragmento": seq[a:b], "label": 1,
            "epitopo": r.epitope__name, "alelo": r.mhc_restriction__name,
            "accession": r.acc_base,
            "frag_inicio": a + 1, "frag_fin": b,
            "epitopo_inicio": i + 1, "epitopo_fin": j,
            "epitopo_offset": i - a, "epitopo_long": j - i,
            "desplazada": a != centro_ideal,
            "pmid": r.reference__pmid, "metodo": r.assay__method,
        })

    # Senuelos: la proteina sin sus epitopos conocidos, troceada sin solape.
    neg, colas = [], 0
    for a_cc, seq in prot.items():
        if a_cc not in ocupados:
            continue                       # solo proteinas que aportan epitopos
        trozos, c = trocear(seq, ocupados[a_cc], w)
        colas += c
        antes = len(trozos)
        trozos = [t for t in trozos if set(t) <= CANONICAL_AA]
        st["fragmento_no_canonico"] += antes - len(trozos)
        for t in trozos:
            neg.append({"fragmento": t, "label": 0, "epitopo": None, "alelo": None,
                        "accession": a_cc, "frag_inicio": None, "frag_fin": None,
                        "epitopo_inicio": None, "epitopo_fin": None,
                        "epitopo_offset": None, "epitopo_long": None,
                        "desplazada": False, "pmid": None, "metodo": None})

    P = pd.DataFrame(pos)
    Nn = pd.DataFrame(neg)
    # Un senuelo repetido es una sola observacion.
    n_neg_brutos = len(Nn)
    if len(Nn):
        Nn = Nn.drop_duplicates("fragmento")
    # Colision positivo/senuelo: gana el positivo, por tener evidencia.
    colisiones = 0
    if len(P) and len(Nn):
        secuencias_pos = set(P.fragmento)
        m = Nn.fragmento.isin(secuencias_pos)
        colisiones = int(m.sum())
        Nn = Nn[~m]

    out = pd.concat([P, Nn], ignore_index=True) if len(P) or len(Nn) else pd.DataFrame()
    if len(out):
        out.insert(0, "clase", clase)
        out.insert(0, "familia", familia)
        out.insert(0, "especie", especie)
        out["ventana"] = w

    n_pos, n_neg = len(P), len(Nn)
    st.update({
        "ventana": w, "positivos": n_pos, "senuelos": n_neg,
        "senuelos_antes_de_dedup": n_neg_brutos,
        "senuelos_duplicados_retirados": n_neg_brutos - len(Nn) - colisiones,
        "colisiones_positivo_senuelo": colisiones,
        "colas_menores_que_w_descartadas": colas,
        "proteinas_usadas": len(ocupados),
        "prevalencia_pct": round(100.0 * n_pos / (n_pos + n_neg), 4) if n_pos + n_neg else 0.0,
    })
    return out, st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True, type=Path)
    ap.add_argument("--proteins", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--w-class-i", type=int, required=True,
                    help="ventana para MHC clase I, en aa")
    ap.add_argument("--w-class-ii", type=int, required=True,
                    help="ventana para MHC clase II, en aa")
    ap.add_argument("--only", action="append", default=None,
                    help="limita a una familia, p. ej. mouse/mhc-I/H2-K")
    ap.add_argument("--format", choices=("parquet", "csv", "both"), default="both")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[3]
    args.out.mkdir(parents=True, exist_ok=True)

    pt = pd.read_parquet(args.proteins)
    prot_all = dict(zip(pt.accession, pt.secuencia))
    print(f"proteinas disponibles: {len(prot_all):,}")

    man = {
        "generado_por": "data_pipeline/scripts/data_download/build_fragments.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "dataset_limpio": str(args.clean),
        "proteinas": str(args.proteins),
        "ventana_clase_I": args.w_class_i,
        "ventana_clase_II": args.w_class_ii,
        "diseno": ("positivo = ventana centrada en el epitopo; senuelo = proteina madre "
                   "con sus epitopos conocidos recortados, troceada sin solape. "
                   "Prevalencia emergente, no elegida."),
        "familias": {},
    }
    tot_p = tot_n = 0
    for f in sorted(args.clean.rglob("mhc_export_full_slim.parquet")):
        rel = f.relative_to(args.clean).parent
        if args.only and str(rel) not in args.only:
            continue
        especie, clase_dir, familia = rel.parts[0], rel.parts[1], rel.parts[2]
        clase = "I" if clase_dir == "mhc-I" else "II"
        w = args.w_class_i if clase == "I" else args.w_class_ii

        df = pd.read_parquet(f)
        print(f"[{familia:8s} clase {clase:2s} w={w:2d}] {len(df):8,} filas -> ",
              end="", flush=True)
        out, st = una_familia(df, prot_all, w, familia, especie, clase)
        man["familias"][str(rel)] = st

        d = args.out / rel
        d.mkdir(parents=True, exist_ok=True)
        salidas = {}
        if len(out):
            if args.format in ("parquet", "both"):
                p = d / "fragments.parquet"
                out.to_parquet(p, index=False, compression="zstd")
                salidas[str(p)] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
            if args.format in ("csv", "both"):
                p = d / "fragments.csv"
                out.to_csv(p, index=False)
                salidas[str(p)] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
        st["salidas"] = salidas
        tot_p += st["positivos"]
        tot_n += st["senuelos"]
        print(f"{st['positivos']:7,} pos + {st['senuelos']:8,} neg "
              f"= {st['positivos']+st['senuelos']:8,}  prev {st['prevalencia_pct']:5.2f} %"
              f"  (desplazadas {st['desplazadas']:,}, no localizados {st['no_localizado']:,})")

        (args.out / "manifest.json").write_text(
            json.dumps(man, indent=2, ensure_ascii=False))

    man["total_positivos"] = tot_p
    man["total_senuelos"] = tot_n
    man["prevalencia_global_pct"] = (
        round(100.0 * tot_p / (tot_p + tot_n), 4) if tot_p + tot_n else 0.0)
    (args.out / "manifest.json").write_text(
        json.dumps(man, indent=2, ensure_ascii=False))
    print(f"\nTOTAL {tot_p:,} positivos + {tot_n:,} senuelos = {tot_p+tot_n:,}"
          f"  prevalencia {man['prevalencia_global_pct']:.2f} %")
    print(f"Manifiesto: {args.out/'manifest.json'}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
