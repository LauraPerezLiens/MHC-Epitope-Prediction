#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fragment_dataset.py — Cargador de los fragmentos con sus embeddings ProtT5.

QUE PROBLEMA RESUELVE
---------------------
Los datos quedan en tres artefactos que NO estan en el mismo orden:

  fragments_wW_ss/.../fragments_ss.parquet   3.338.349 filas (ejemplos)
  embeddings_prott5_wW/chunk_*_residues.npy  2.214.057 vectores (unicos)
  splits_wW/splits.parquet                   la particion de cada fila

Hay menos vectores que filas porque el 34 % de los fragmentos se repiten entre
familias y se embebieron una sola vez. Y estan ordenados alfabeticamente por
secuencia, no en el orden de las filas. `index.parquet` es la traduccion:
secuencia -> (chunk, fila dentro del chunk).

DOS MODOS DE FEATURES
---------------------
  `primary`            (w, 1024)  solo ProtT5
  `primary_secondary`  (w, 1027)  ProtT5 + 3 canales one-hot de C/H/E

Los tres canales son la forma barata de probar si la estructura secundaria
aporta: si 3 dimensiones no mueven nada, las 768 de SecondaryBERT es muy
improbable que lo hagan, y ese es el resultado negativo que §0.5.6 propone
publicar.

> **Las filas sin estructura secundaria se descartan SIEMPRE, tambien en el modo
> `primary`.** Son 5.246 de 3.338.349 (0,157 %). Descartarlas en los dos modos
> es lo que hace que la comparacion sea limpia: los dos brazos ven exactamente
> las mismas filas, y la unica diferencia son los 3 canales. Con
> `--permitir-sin-ss` se conservan en modo `primary`, pero entonces los brazos
> dejan de ser comparables fila a fila.

EL BARAJADO, Y POR QUE NO ES FILA A FILA
----------------------------------------
Los embeddings pesan ~100 GB por ventana en 142 ficheros, y `/data` es ZFS con
161 GB de RAM disponible: no cabe todo en cache. Barajar fila a fila obligaria a
una lectura aleatoria de 43 KB por ejemplo, repartida entre los 142 ficheros.

Pero barajar por bloques de un solo chunk tiene un problema propio que es facil
pasar por alto: **las secuencias se escribieron ordenadas alfabeticamente**, de
modo que un chunk contiene fragmentos que empiezan todos por el mismo prefijo.
Un lote sacado de un chunk estaria fuertemente correlacionado.

La solucion que se usa aqui es una **ventana de varios chunks**: se abren `M`
chunks a la vez (por omision 16, unos 13 GB), se barajan juntas todas sus filas
y se sirven lotes; luego se pasa a los siguientes `M`. Y la agrupacion de que
chunks van juntos **se rebaraja en cada epoca**, de modo que dos filas no caen
siempre en la misma ventana. Con 142 chunks y M=16 cada lote mezcla 16
vecindarios alfabeticos distintos.

Con `--mmap-aleatorio` se usa acceso aleatorio puro por memoria mapeada, que
baraja perfecto pero depende de la cache del sistema de ficheros. Esta ahi para
poder comparar las dos estrategias.

VERIFICACION
------------
`--selftest` comprueba la correspondencia vector-secuencia sin necesidad del
modelo: cada chunk trae su `chunk_*_seq.txt` con las secuencias en el orden en
que se escribieron las filas del `.npy`, asi que basta comprobar que la linea
`r` de ese fichero es exactamente la secuencia de la fila. Es la comprobacion
decisiva: si la traduccion estuviera mal, el entrenamiento aprenderia de
vectores que no corresponden a sus etiquetas, y ningun resultado lo delataria.

USO
---
    from fragment_dataset import FragmentDataset

    ds = FragmentDataset(
        fragments="data/fragments_w21_ss",
        embeddings="data/embeddings_prott5_w21",
        splits="data/splits_w21/splits.parquet",
        split="train",
        features="primary_secondary",
        excluir_contradictorios=True,
    )
    for X, y in ds.batches(batch_size=512, shuffle=True, seed=0):
        ...                      # X: (B, w, 1027) float32 ; y: (B,) float32

    # comprobacion de integridad, sin GPU:
    #   P=/home/nap/miniconda3/envs/nap_env/bin/python
    #   $P -u data_pipeline/scripts/embeddings/primary_structure/fragment_dataset.py \\
    #       --fragments data/fragments_w21_ss --embeddings data/embeddings_prott5_w21 \\
    #       --splits data/splits_w21/splits.parquet --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

Q3 = "CHE"
Q3_IDX = {c: i for i, c in enumerate(Q3)}
# 255 es "letra desconocida": no coincide con ningun indice, de modo que su
# vector one-hot queda a cero sin necesidad de una rama aparte.
_LUT_Q3 = np.full(256, 255, dtype=np.uint8)
for _i, _c in enumerate(Q3):
    _LUT_Q3[ord(_c)] = _i
_ARANGE3 = np.arange(3, dtype=np.uint8)


class FragmentDataset:
    """Fragmentos de una particion, con sus embeddings y su estructura."""

    def __init__(
        self,
        fragments: str | Path,
        embeddings: str | Path,
        splits: str | Path,
        split: str = "train",
        features: str = "primary",
        excluir_contradictorios: bool = False,
        familias: list[str] | None = None,
        especies: list[str] | None = None,
        permitir_sin_ss: bool = False,
        solo_chunks_presentes: bool = False,
        verbose: bool = True,
    ) -> None:
        if features not in ("primary", "primary_secondary"):
            raise ValueError(f"features desconocido: {features!r}")
        self.features = features
        self.emb_dir = Path(embeddings)

        cols = ["familia", "especie", "clase", "fragmento", "secondary_structure",
                "label", "alelo", "accession", "pmid", "ss_status",
                "contradictorio", "ventana"]
        partes = []
        for f in sorted(Path(fragments).rglob("fragments_ss.parquet")):
            partes.append(pd.read_parquet(f, columns=cols))
        if not partes:
            raise SystemExit(f"sin fragments_ss.parquet bajo {fragments}")
        D = pd.concat(partes, ignore_index=True)
        self.w = int(D.ventana.iloc[0])
        n0 = len(D)

        sp = pd.read_parquet(splits, columns=["fragmento", "accession", "split"])
        # La particion es por (fragmento, proteina): la misma secuencia puede
        # estar en varias familias, pero por construccion siempre en la misma
        # particion, asi que la union es consistente.
        sp = sp.drop_duplicates(["fragmento", "accession"])
        D = D.merge(sp, on=["fragmento", "accession"], how="left")
        sin_split = int(D.split.isna().sum())
        if sin_split:
            raise SystemExit(f"ABORTADO: {sin_split:,} filas sin particion asignada")

        pasos = [("particion " + split, D.split == split)]
        if not permitir_sin_ss or features == "primary_secondary":
            pasos.append(("con estructura secundaria", D.ss_status == "ok"))
        if excluir_contradictorios:
            pasos.append(("sin contradiccion", ~D.contradictorio))
        if familias:
            pasos.append(("familias elegidas", D.familia.isin(familias)))
        if especies:
            pasos.append(("especies elegidas", D.especie.isin(especies)))
        for nombre, m in pasos:
            antes = len(D)
            D = D[m.reindex(D.index, fill_value=False)]
            if verbose:
                print(f"  {nombre:28s} {antes:9,} -> {len(D):9,}")
        if not len(D):
            raise SystemExit("ABORTADO: no queda ninguna fila tras los filtros")

        idx = pd.read_parquet(self.emb_dir / "index.parquet")
        D = D.merge(idx, on="fragmento", how="left")
        huerfanas = int(D.chunk.isna().sum())
        if huerfanas:
            raise SystemExit(
                f"ABORTADO: {huerfanas:,} filas cuyo fragmento no esta en los "
                f"embeddings. El index.parquet no corresponde a estos fragmentos.")
        D["chunk"] = D.chunk.astype("int32")
        D["fila"] = D.fila.astype("int32")

        self.tabla = D.reset_index(drop=True)
        self.chunks = sorted(self.tabla.chunk.unique())
        self.dtype = np.dtype(np.float32)
        self.devolver_indices = False

        # Que los embeddings de los chunks implicados existan de verdad. Sin
        # esto el fallo aparece a mitad de la primera epoca, con un
        # FileNotFoundError opaco.
        if solo_chunks_presentes:
            # Solo para validar la logica mientras la generacion esta a medias.
            hay = {c for c in self.chunks
                   if (self.emb_dir / f"chunk_{c:06d}_residues.npy").exists()}
            self.tabla = self.tabla[self.tabla.chunk.isin(hay)].reset_index(drop=True)
            self.chunks = sorted(self.tabla.chunk.unique())
            if verbose:
                print(f"  (solo chunks presentes: {len(self.chunks)} chunks, "
                      f"{len(self.tabla):,} ejemplos)")
        faltan = [c for c in self.chunks
                  if not (self.emb_dir / f"chunk_{c:06d}_residues.npy").exists()]
        if faltan:
            raise SystemExit(
                f"ABORTADO: faltan los embeddings de {len(faltan)} de "
                f"{len(self.chunks)} chunks implicados (p. ej. "
                f"{faltan[:5]}). Si la generacion sigue en marcha, espera a "
                f"que termine.")
        if verbose:
            print(f"  -> {len(self.tabla):,} ejemplos de {n0:,} | "
                  f"prevalencia {100*self.tabla.label.mean():.2f} % | "
                  f"ventana {self.w} | chunks implicados {len(self.chunks)}")

    # ---------------------------------------------------------------- utilidades
    def __len__(self) -> int:
        return len(self.tabla)

    @property
    def dim(self) -> int:
        return 1024 + (3 if self.features == "primary_secondary" else 0)

    def _onehot(self, cadenas: pd.Series, dtype=np.float32) -> np.ndarray:
        """(n, w, 3) one-hot de C/H/E. Una letra desconocida deja el vector a 0.

        Vectorizado: las cadenas se concatenan y se leen como bytes, una tabla
        de 256 entradas traduce la letra a indice y el one-hot sale por
        comparacion con difusion. La version con dos bucles de Python costaba el
        39 % del tiempo de epoca del brazo `primary_secondary` (medido: 2.789
        ej/s frente a 4.571 del brazo `primary`, con los mismos datos).
        """
        n = len(cadenas)
        bruto = "".join(cadenas.values)
        if len(bruto) != n * self.w:
            raise SystemExit(
                f"ABORTADO: alguna estructura no mide {self.w}; "
                f"{len(bruto)} caracteres para {n} filas")
        k = _LUT_Q3[np.frombuffer(bruto.encode("ascii"), dtype=np.uint8)]
        return (k.reshape(n, self.w, 1) == _ARANGE3).astype(dtype)

    def _residues(self, c: int) -> np.ndarray:
        return np.load(self.emb_dir / f"chunk_{c:06d}_residues.npy", mmap_mode="r")

    def _arma(self, sub: pd.DataFrame, X1024: np.ndarray):
        """Monta el lote. Con `dtype=float16` se sirve en la precision en la que
        esta el disco, que es la mitad de bytes a mover hasta la GPU; la
        conversion a float32 y la estandarizacion se hacen alli."""
        X = X1024.astype(self.dtype, copy=False)
        if self.features == "primary_secondary":
            X = np.concatenate(
                [X, self._onehot(sub.secondary_structure, self.dtype)], axis=2)
        y = sub.label.to_numpy(dtype=np.float32)
        if self.devolver_indices:
            return X, y, sub.index.to_numpy()
        return X, y

    # ------------------------------------------------------------------- lotes
    def batches(self, batch_size: int = 512, shuffle: bool = True,
                seed: int = 0, chunks_en_memoria: int = 16,
                mmap_aleatorio: bool = False, dtype=np.float32,
                indices: bool = False):
        """Itera lotes `(X, y)`, o `(X, y, idx)` con `indices=True`.

        X es (B, w, dim) del `dtype` pedido e y es (B,) float32. `idx` son los
        indices de `self.tabla`, para poder desglosar las metricas por familia o
        por especie sin tener que reconstruir el orden de las filas.
        """
        self.dtype = np.dtype(dtype)
        self.devolver_indices = indices
        rng = np.random.default_rng(seed)
        if mmap_aleatorio:
            yield from self._batches_mmap(batch_size, shuffle, rng)
        else:
            yield from self._batches_ventana(batch_size, shuffle, rng,
                                             chunks_en_memoria)

    def _batches_ventana(self, bs, shuffle, rng, M):
        orden = list(self.chunks)
        if shuffle:
            rng.shuffle(orden)          # rebaraja QUE chunks van juntos
        for k in range(0, len(orden), M):
            grupo = orden[k:k + M]
            sub = self.tabla[self.tabla.chunk.isin(grupo)]
            if not len(sub):
                continue
            # Se carga cada chunk del grupo una sola vez, de forma secuencial.
            cache = {c: np.asarray(self._residues(c)) for c in grupo}
            orden_filas = rng.permutation(len(sub)) if shuffle else np.arange(len(sub))
            for i in range(0, len(sub), bs):
                s = sub.iloc[orden_filas[i:i + bs]]
                X1024 = np.stack([cache[c][r] for c, r in
                                  zip(s.chunk.values, s.fila.values)])
                yield self._arma(s, X1024)
            del cache

    def _batches_mmap(self, bs, shuffle, rng):
        """Acceso por memoria mapeada: lee SOLO las filas que hacen falta.

        Es el camino correcto para evaluar. Con la ventana de chunks, puntuar
        VALIDATION —308 k filas repartidas por los 111 chunks— obliga a cargar
        los 111 chunks enteros, 93 GB, para quedarse con 2.800 filas de cada
        uno. Aqui se leen 13 GB en lugar de 93.

        Sin barajado las filas se recorren **ordenadas por (chunk, fila)**, que
        es el orden del disco: convierte 308 k lecturas dispersas en un barrido
        casi secuencial. El orden de salida deja de ser el de la tabla, y por
        eso `indices=True` existe: las metricas se reconstruyen por indice, no
        por posicion.
        """
        abiertos: dict[int, np.ndarray] = {}
        if shuffle:
            orden_filas = rng.permutation(len(self.tabla))
        else:
            orden_filas = np.lexsort((self.tabla.fila.values,
                                      self.tabla.chunk.values))
        for i in range(0, len(self.tabla), bs):
            s = self.tabla.iloc[orden_filas[i:i + bs]]
            filas = []
            for c, r in zip(s.chunk.values, s.fila.values):
                if c not in abiertos:
                    abiertos[c] = self._residues(c)
                filas.append(np.asarray(abiertos[c][r]))
            yield self._arma(s, np.stack(filas))

    # -------------------------------------------------------------- integridad
    def selftest(self, n: int = 20_000, seed: int = 0) -> bool:
        """Comprueba que el vector servido corresponde a la secuencia de la fila.

        Se apoya en `chunk_*_seq.txt`, que guarda las secuencias en el mismo
        orden que las filas del `.npy`. Si la traduccion estuviera mal, el
        entrenamiento aprenderia de vectores que no corresponden a sus
        etiquetas y ningun resultado lo delataria.
        """
        rng = np.random.default_rng(seed)
        m = min(n, len(self.tabla))
        s = self.tabla.iloc[rng.choice(len(self.tabla), m, replace=False)]
        fallos = 0
        for c, g in s.groupby("chunk"):
            seqs = (self.emb_dir / f"chunk_{int(c):06d}_seq.txt").read_text().split("\n")
            res = self._residues(int(c))
            if len(seqs) != res.shape[0]:
                print(f"  chunk {c}: {len(seqs)} secuencias y {res.shape[0]} filas",
                      file=sys.stderr)
                fallos += 1
                continue
            for r, frag in zip(g.fila.values, g.fragmento.values):
                if seqs[r] != frag:
                    fallos += 1
                    if fallos < 4:
                        print(f"  chunk {c} fila {r}: esperaba {frag} y hay {seqs[r]}",
                              file=sys.stderr)
        print(f"selftest: {m:,} filas comprobadas | fallos {fallos}")
        # Forma y finitud de un lote real.
        X, y = next(iter(self.batches(batch_size=256, shuffle=True, seed=seed,
                                      chunks_en_memoria=2)))
        ok_forma = X.shape[1:] == (self.w, self.dim)
        print(f"  lote: X {X.shape} y {y.shape} | forma esperada "
              f"({self.w}, {self.dim}): {ok_forma} | finito {np.isfinite(X).all()}")
        if self.features == "primary_secondary":
            canales = X[:, :, 1024:]
            print(f"  canales C/H/E: suma por residuo siempre 1: "
                  f"{bool((canales.sum(axis=2) == 1).all())}")
        return fallos == 0 and ok_forma


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True)
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--splits", required=True)
    ap.add_argument("--split", default="train")
    ap.add_argument("--features", choices=("primary", "primary_secondary"),
                    default="primary_secondary")
    ap.add_argument("--excluir-contradictorios", action="store_true")
    ap.add_argument("--permitir-sin-ss", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    ds = FragmentDataset(
        fragments=args.fragments, embeddings=args.embeddings, splits=args.splits,
        split=args.split, features=args.features,
        excluir_contradictorios=args.excluir_contradictorios,
        permitir_sin_ss=args.permitir_sin_ss,
    )
    if args.selftest:
        return 0 if ds.selftest() else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
