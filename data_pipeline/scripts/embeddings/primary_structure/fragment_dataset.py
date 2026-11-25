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

MODOS DE FEATURES
-----------------
  `primary`            (w, 1024)  solo ProtT5
  `primary_secondary`  (w, 1027)  ProtT5 + 3 canales one-hot de C/H/E
  `primary_sbert`      (w, 1792)  ProtT5 + SecondaryBERT por residuo
  `sbert`              (w,  768)  solo SecondaryBERT
  `secondary`          (w,    3)  solo el one-hot de C/H/E

El orden de concatenacion —ProtT5, one-hot, SecondaryBERT— es un contrato: el
scaler estandariza las primeras 1024 columnas y deja el resto, asi que
cambiarlo desalinearia las estadisticas.

Los tres canales one-hot son la forma barata de probar si la estructura
secundaria aporta. **Y los brazos con SecondaryBERT son los que cierran la
pregunta**, porque al one-hot se le puede objetar que 3 canales sobre 21.507
features se ahogan: `w x 768` = 16.128 features iguala el peso de las dos
modalidades en la entrada. Lo que NO hacen es aportar informacion nueva: la
entrada de SecondaryBERT es exactamente la cadena de C/H/E, que el one-hot ya
codifica sin perdida, de modo que lo que se mide es si una recodificacion
preentrenada ayuda. Es el resultado negativo que §0.5.6 propone publicar, y asi
queda medido por los dos lados.

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
import os
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

# Modalidades de entrada: (usa ProtT5, usa one-hot C/H/E, usa SecondaryBERT).
# La dimension por residuo se deduce de aqui, no se escribe a mano.
MODALIDADES = {
    "primary":           (True,  False, False),
    "primary_secondary": (True,  True,  False),
    "primary_sbert":     (True,  False, True),
    "sbert":             (False, False, True),
    "secondary":         (False, True,  False),
}
DIM_PROTT5, DIM_SBERT = 1024, 768


class LectorNpy:
    """Lee filas de un `.npy` con `pread()`, no con `mmap`.

    **En ZFS, `mmap` es el camino malo.** Los datos viven en el ARC —aqui 160 GB
    de los 376 de la maquina— y `mmap` obliga a ZFS a copiarlos ADEMAS a la
    cache de pagina del kernel: se paga memoria dos veces y cada fallo de
    pagina mueve 4 KB. Una fila de 21x1024 fp16 son 43 KB, es decir 11 fallos
    por fila y 22.528 por lote de 2.048. Con `pread()` la copia sale del ARC de
    una vez, en bloques del tamano que se pida, sin duplicar en cache.

    Medido sobre este servidor, con el ARC caliente y los dos entrenamientos
    compitiendo: **1,53 GB/s con `pread` frente a 0,90 con `mmap`**, y mucho mas
    estable (1,44-1,67 frente a 0,45-1,61). El resultado es **bit a bit
    identico**, comprobado.

    Las filas pedidas se ordenan y las consecutivas se agrupan en una sola
    lectura, de modo que pedir el 70 % de un chunk sale en pocas llamadas en
    lugar de 14.000. El orden de salida es el PEDIDO, no el ordenado.
    """

    def __init__(self, ruta: Path) -> None:
        with open(ruta, "rb") as fh:
            v = np.lib.format.read_magic(fh)
            if v == (1, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(fh)
            elif v == (2, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_2_0(fh)
            else:
                raise SystemExit(f"ABORTADO: version de .npy {v} en {ruta}")
            self.off = fh.tell()
        if fortran:
            raise SystemExit(f"ABORTADO: {ruta} esta en orden Fortran")
        self.shape, self.dtype = shape, dtype
        self.fila_bytes = int(np.prod(shape[1:])) * dtype.itemsize
        self.fd = os.open(str(ruta), os.O_RDONLY)

    def __getitem__(self, filas) -> np.ndarray:
        filas = np.asarray(filas, dtype=np.int64)
        out = np.empty((len(filas),) + tuple(self.shape[1:]), dtype=self.dtype)
        plano = out.reshape(len(filas), -1).view(np.uint8)
        orden = np.argsort(filas, kind="stable")
        f = filas[orden]
        cortes = np.flatnonzero(np.diff(f) != 1) + 1
        i = 0
        for tramo in np.split(f, cortes):
            n = len(tramo)
            esperado = n * self.fila_bytes
            b = os.pread(self.fd, esperado,
                         self.off + int(tramo[0]) * self.fila_bytes)
            if len(b) != esperado:
                raise SystemExit(
                    f"ABORTADO: lectura corta, {len(b)} de {esperado} bytes "
                    f"en la fila {int(tramo[0])}")
            plano[orden[i:i + n]] = np.frombuffer(
                b, dtype=np.uint8).reshape(n, self.fila_bytes)
            i += n
        return out

    def close(self) -> None:
        if getattr(self, "fd", None) is not None:
            os.close(self.fd)
            self.fd = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


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
        embeddings_sbert: str | Path | None = None,
        sbert_precargado: np.ndarray | None = None,
        verbose: bool = True,
    ) -> None:
        if features not in MODALIDADES:
            raise ValueError(f"features desconocido: {features!r}; "
                             f"hay {sorted(MODALIDADES)}")
        self.features = features
        self.usa_prott5, self.usa_onehot, self.usa_sbert = MODALIDADES[features]
        if self.usa_sbert and embeddings_sbert is None:
            raise ValueError(f"features={features!r} necesita embeddings_sbert")
        self.emb_dir = Path(embeddings)
        self.sbert_dir = Path(embeddings_sbert) if embeddings_sbert else None

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
        if not permitir_sin_ss or self.usa_onehot or self.usa_sbert:
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

        if self.usa_prott5:
            idx = pd.read_parquet(self.emb_dir / "index.parquet")
            D = D.merge(idx, on="fragmento", how="left")
            huerfanas = int(D.chunk.isna().sum())
            if huerfanas:
                raise SystemExit(
                    f"ABORTADO: {huerfanas:,} filas cuyo fragmento no esta en los "
                    f"embeddings. El index.parquet no corresponde a estos "
                    f"fragmentos.")
            D["chunk"] = D.chunk.astype("int32")
            D["fila"] = D.fila.astype("int32")

        self.tabla = D.reset_index(drop=True)
        self.chunks = sorted(self.tabla.chunk.unique()) if self.usa_prott5 else []
        self.dtype = np.dtype(np.float32)
        self.devolver_indices = False
        self.sbert = None

        # Que los embeddings de los chunks implicados existan de verdad. Sin
        # esto el fallo aparece a mitad de la primera epoca, con un
        # FileNotFoundError opaco.
        if solo_chunks_presentes and self.usa_prott5:
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

        if self.usa_sbert:
            self._carga_sbert(verbose, sbert_precargado)
        self._arrays(verbose)
        if verbose:
            print(f"  -> {len(self.tabla):,} ejemplos de {n0:,} | "
                  f"prevalencia {100*self.tabla.label.mean():.2f} % | "
                  f"ventana {self.w} | chunks implicados {len(self.chunks)}")

    def _arrays(self, verbose: bool) -> None:
        """Pasa a numpy lo que usa el bucle caliente y suelta el resto.

        `tabla.iloc[idx]` sobre 2,5 M filas con columnas de objeto no es gratis,
        y se hace una vez por lote. Aqui se extraen de una vez los vectores que
        el bucle necesita —etiqueta, chunk, fila, fila de SecondaryBERT y los
        indices Q3— y la tabla se queda solo para las metricas por familia, que
        se resuelven por indice y fuera del bucle.

        Los indices Q3 se precalculan como `(N, w)` uint8: son 52 MB para 2,5 M
        filas y ahorran concatenar las cadenas en cada lote. Ademas, enviar
        `(B, w)` uint8 a la GPU en lugar de `(B, w, 3)` fp16 es 6 veces menos
        que mover, y el one-hot se construye alli.
        """
        self._label = self.tabla.label.to_numpy(dtype=np.float32)
        self._chunk = (self.tabla.chunk.to_numpy(dtype=np.int32)
                       if self.usa_prott5 else None)
        self._fila = (self.tabla.fila.to_numpy(dtype=np.int32)
                      if self.usa_prott5 else None)
        self._fsb = (self.tabla.fila_sbert.to_numpy(dtype=np.int64)
                     if self.usa_sbert else None)
        self._q3 = None
        if self.usa_onehot:
            bruto = "".join(self.tabla.secondary_structure.values)
            self._q3 = _LUT_Q3[np.frombuffer(bruto.encode("ascii"),
                                             dtype=np.uint8)
                               ].reshape(len(self.tabla), self.w).copy()
        # Columnas que ya no hacen falta. `fragmento` y `secondary_structure` se
        # conservan porque el selftest comprueba con ellas la correspondencia
        # vector-secuencia, que es la verificacion que no se puede perder.
        sobran = [c for c in ("alelo", "ss_status", "contradictorio", "ventana",
                              "split", "pmid") if c in self.tabla.columns]
        self.tabla = self.tabla.drop(columns=sobran)
        for c in ("familia", "especie", "clase"):
            if c in self.tabla.columns:
                self.tabla[c] = self.tabla[c].astype("category")
        if verbose:
            mb = self.tabla.memory_usage(deep=True).sum() / 1e6
            print(f"  tabla en memoria {mb:,.0f} MB "
                  f"(se han soltado {len(sobran)} columnas)")

    # ------------------------------------------------------------ SecondaryBERT
    def _carga_sbert(self, verbose: bool,
                     precargado: np.ndarray | None = None) -> None:
        """Carga TODO SecondaryBERT en RAM y guarda la fila de cada ejemplo.

        Caben de sobra y eso simplifica el resto: los embeddings estan
        deduplicados por **cadena Q3**, no por fragmento —257.691 cadenas unicas
        para 2.210.409 fragmentos en w21, el 11,7 %—, asi que son 8,3 GB en w21
        y 16,6 en w25. Con el tensor entero en memoria no hay que coordinar dos
        particiones de chunks distintas: la del indice de ProtT5 y la de este.
        """
        idx = pd.read_parquet(self.sbert_dir / "index.parquet")
        tam = int(idx.fila.max()) + 1 if len(idx) else 0
        # Fila global = chunk * tamano_de_chunk + fila. El tamano se deduce del
        # propio indice para no tener que pasarlo como parametro.
        self._sbert_tam = tam
        idx["fila_sbert"] = (idx.chunk.astype("int64") * tam
                             + idx.fila.astype("int64"))
        D = self.tabla.merge(idx[["secondary_structure", "fila_sbert"]],
                             on="secondary_structure", how="left")
        huerfanas = int(D.fila_sbert.isna().sum())
        if huerfanas:
            raise SystemExit(
                f"ABORTADO: {huerfanas:,} filas cuya cadena Q3 no esta en los "
                f"embeddings de SecondaryBERT. El index.parquet no corresponde "
                f"a estos fragmentos.")
        self.tabla = D
        self.tabla["fila_sbert"] = self.tabla.fila_sbert.astype("int64")

        if precargado is not None:
            # El tensor se comparte entre TRAIN, VALIDATION y TEST del mismo
            # proceso: son los MISMOS vectores, indexados por cadena Q3, y una
            # copia por particion triplicaria la memoria sin ganar nada.
            self.sbert = precargado
        else:
            partes = []
            for f in sorted(self.sbert_dir.glob("chunk_*_residues.npy")):
                partes.append(np.load(f))
            if not partes:
                raise SystemExit(f"sin chunk_*_residues.npy en {self.sbert_dir}")
            self.sbert = np.concatenate(partes, axis=0)
            del partes
        if self.sbert.shape[1] != self.w or self.sbert.shape[2] != DIM_SBERT:
            raise SystemExit(
                f"ABORTADO: SecondaryBERT tiene forma {self.sbert.shape}, se "
                f"esperaba (N, {self.w}, {DIM_SBERT})")
        tope = int(self.tabla.fila_sbert.max())
        if tope >= self.sbert.shape[0]:
            raise SystemExit(
                f"ABORTADO: el indice apunta a la fila {tope:,} y solo hay "
                f"{self.sbert.shape[0]:,} vectores de SecondaryBERT")
        if verbose:
            print(f"  SecondaryBERT en RAM: {self.sbert.shape} "
                  f"{self.sbert.dtype} = {self.sbert.nbytes/1e9:.1f} GB | "
                  f"cadenas Q3 distintas en esta particion "
                  f"{self.tabla.fila_sbert.nunique():,}")

    # ---------------------------------------------------------------- utilidades
    def __len__(self) -> int:
        return len(self.tabla)

    @property
    def dim(self) -> int:
        return (DIM_PROTT5 * self.usa_prott5 + 3 * self.usa_onehot
                + DIM_SBERT * self.usa_sbert)

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

    def _residues(self, c: int) -> LectorNpy:
        return LectorNpy(self.emb_dir / f"chunk_{c:06d}_residues.npy")

    def _arma(self, idx: np.ndarray, mm: dict | None = None) -> dict:
        """Monta el lote y lo entrega POR PIEZAS, sin concatenar en CPU.

        Devuelve un diccionario con `prott5` (B, w, 1024) fp16, `q3` (B, w)
        uint8 y `sbert` (B, w, 768) fp16, segun la modalidad, mas `y` y, si se
        pidio, `idx`.

        **Concatenar en CPU era el cuello de botella.** Juntar ProtT5 con
        SecondaryBERT en un `(B, w, 1792)` son 154 MB de memcpy por lote, y con
        el one-hot 88 MB, puro trabajo de CPU que no aporta nada: la GPU
        concatena eso en microsegundos. El `q3` viaja como indice uint8 —43 KB
        por lote en lugar de 258 KB— y el one-hot se construye en la GPU.

        El orden de concatenacion que el entrenamiento debe respetar es
        **ProtT5, one-hot, SecondaryBERT**, y es un contrato: el scaler
        estandariza las primeras 1024 columnas y deja el resto.
        """
        lote: dict = {"y": self._label[idx]}
        if self.usa_prott5:
            n = len(idx)
            pt = np.empty((n, self.w, DIM_PROTT5), dtype=np.float16)
            ch, fi = self._chunk[idx], self._fila[idx]
            for c in np.unique(ch):
                m = np.flatnonzero(ch == c)
                # `LectorNpy` ya ordena internamente y agrupa las filas
                # consecutivas en una sola lectura, devolviendolas en el orden
                # pedido, asi que aqui no hay que reordenar nada.
                pt[m] = mm[int(c)][fi[m]]
            lote["prott5"] = pt
        if self.usa_onehot:
            lote["q3"] = self._q3[idx]
        if self.usa_sbert:
            lote["sbert"] = self.sbert[self._fsb[idx]]
        if self.devolver_indices:
            lote["idx"] = idx
        return lote

    # ------------------------------------------------------------------- lotes
    def batches(self, batch_size: int = 512, shuffle: bool = True,
                seed: int = 0, chunks_en_memoria: int = 16,
                mmap_aleatorio: bool = False, indices: bool = False,
                frac_pos: float | None = None):
        """Itera lotes como **diccionario de piezas**, no como un tensor unico.

        Claves posibles: `prott5` (B, w, 1024) fp16, `q3` (B, w) uint8, `sbert`
        (B, w, 768) fp16, `y` (B,) float32 y, con `indices=True`, `idx` con los
        indices de `self.tabla` para desglosar las metricas por familia.

        Se entrega por piezas a proposito: concatenarlas en CPU son 154 MB de
        memcpy por lote en el brazo con SecondaryBERT, trabajo que la GPU hace
        en microsegundos. Todo viaja en la precision en la que esta el disco.

        `frac_pos` fuerza la fraccion de positivos de cada lote submuestreando
        la clase sobrante, al estilo del `BalancedSequence` de Wert2021. **Solo
        vale para TRAIN**: aplicarlo a VALIDATION o TEST es el defecto 3 de
        §0.8, que hacia incomparables las metricas. Aqui se niega a aplicarse
        con `mmap_aleatorio`, que es el camino de evaluacion.
        """
        self.devolver_indices = indices
        if frac_pos is not None:
            if not 0.0 < frac_pos < 1.0:
                raise ValueError(f"frac_pos fuera de (0, 1): {frac_pos}")
            if mmap_aleatorio:
                raise ValueError(
                    "frac_pos con mmap_aleatorio: ese es el camino de "
                    "evaluacion y debe conservar la prevalencia natural (§0.8)")
        rng = np.random.default_rng(seed)
        if not self.usa_prott5:
            # Sin ProtT5 no hay nada en disco que recorrer: SecondaryBERT y el
            # one-hot estan en RAM. Barajar fila a fila es gratis, y recorrer
            # los 93 GB de ProtT5 para no usarlos seria absurdo.
            yield from self._batches_ram(batch_size, shuffle, rng, frac_pos)
        elif mmap_aleatorio:
            yield from self._batches_mmap(batch_size, shuffle, rng)
        else:
            yield from self._batches_ventana(batch_size, shuffle, rng,
                                             chunks_en_memoria, frac_pos)

    def _lotes_equilibrados(self, sel, bs, rng, frac_pos):
        """Troceado de `sel` en lotes con `frac_pos` de positivos exactos.

        Submuestrea la clase sobrante, como el `BalancedSequence` de Wert2021:
        no repite ejemplos, de modo que la epoca ve todos los de la clase
        minoritaria y solo una parte de la otra, distinta en cada epoca porque
        los dos grupos se barajan antes. Con prevalencia 30,43 % y 50/50, una
        epoca usa 1,52 M de los 2,49 M de TRAIN.
        """
        et = self._label[sel]
        pos, neg = sel[et == 1], sel[et == 0]
        rng.shuffle(pos)
        rng.shuffle(neg)
        npos = max(int(round(bs * frac_pos)), 1)
        nneg = max(bs - npos, 1)
        for i in range(min(len(pos) // npos, len(neg) // nneg)):
            yield np.concatenate([pos[i * npos:(i + 1) * npos],
                                  neg[i * nneg:(i + 1) * nneg]])

    def _batches_ram(self, bs, shuffle, rng, frac_pos=None):
        """Todo en memoria: barajado perfecto fila a fila, sin tocar el disco."""
        orden = (rng.permutation(len(self._label)) if shuffle
                 else np.arange(len(self._label)))
        if frac_pos is not None:
            for idx in self._lotes_equilibrados(orden, bs, rng, frac_pos):
                yield self._arma(idx)
            return
        for i in range(0, len(orden), bs):
            yield self._arma(orden[i:i + bs])

    def _batches_ventana(self, bs, shuffle, rng, M, frac_pos=None):
        """Ventana de M chunks, leidos por memoria mapeada y SIN copiarlos.

        La version anterior hacia `np.asarray(memmap)` de los 16 chunks del
        grupo: 13,8 GB de copia privada por proceso, que con dos entrenamientos
        a la vez son 27,6 GB que el sistema no puede compartir. Leyendo del
        memmap, las paginas viven en la **cache de pagina**, que SI es comun a
        los dos procesos —leen los mismos ficheros— y es desalojable si hace
        falta. La RAM privada baja a la del lote.
        """
        orden = list(self.chunks)
        if shuffle:
            rng.shuffle(orden)          # rebaraja QUE chunks van juntos
        for k in range(0, len(orden), M):
            grupo = orden[k:k + M]
            sel = np.flatnonzero(np.isin(self._chunk, grupo))
            if not len(sel):
                continue
            mm = {c: self._residues(c) for c in grupo}
            try:
                if frac_pos is not None:
                    # El equilibrado es DENTRO de la ventana de chunks, no
                    # global: cada lote sigue saliendo de los mismos 16
                    # vecindarios, de modo que no deshace el barajado de
                    # §0.15.2.
                    for idx in self._lotes_equilibrados(sel, bs, rng, frac_pos):
                        yield self._arma(idx, mm)
                else:
                    if shuffle:
                        rng.shuffle(sel)
                    for i in range(0, len(sel), bs):
                        yield self._arma(sel[i:i + bs], mm)
            finally:
                for lector in mm.values():
                    lector.close()
                mm.clear()

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
        mm = {int(c): self._residues(int(c)) for c in self.chunks}
        try:
            if shuffle:
                orden_filas = rng.permutation(len(self._label))
            else:
                orden_filas = np.lexsort((self._fila, self._chunk))
            for i in range(0, len(orden_filas), bs):
                yield self._arma(orden_filas[i:i + bs], mm)
        finally:
            for lector in mm.values():
                lector.close()

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
        if self.usa_prott5:
            for c, g in s.groupby("chunk"):
                seqs = (self.emb_dir / f"chunk_{int(c):06d}_seq.txt"
                        ).read_text().split("\n")
                res = self._residues(int(c))
                nfilas = res.shape[0]
                res.close()
                if len(seqs) != nfilas:
                    print(f"  chunk {c}: {len(seqs)} secuencias y "
                          f"{nfilas} filas", file=sys.stderr)
                    fallos += 1
                    continue
                for r, frag in zip(g.fila.values, g.fragmento.values):
                    if seqs[r] != frag:
                        fallos += 1
                        if fallos < 4:
                            print(f"  chunk {c} fila {r}: esperaba {frag} y "
                                  f"hay {seqs[r]}", file=sys.stderr)
            print(f"selftest ProtT5: {m:,} filas comprobadas | fallos {fallos}")

        if self.usa_sbert:
            # Misma comprobacion para SecondaryBERT, pero la clave es la CADENA
            # Q3 y la fila es global, asi que hay que deshacer el chunk.
            fsb = 0
            cache: dict[int, list[str]] = {}
            for fila_g, q3 in zip(s.fila_sbert.values, s.secondary_structure.values):
                c, r = divmod(int(fila_g), self._sbert_tam)
                if c not in cache:
                    cache[c] = (self.sbert_dir / f"chunk_{c:06d}_seq.txt"
                                ).read_text().split("\n")
                if cache[c][r] != q3:
                    fsb += 1
                    if fsb < 4:
                        print(f"  sbert chunk {c} fila {r}: esperaba {q3} y "
                              f"hay {cache[c][r]}", file=sys.stderr)
            print(f"selftest SecondaryBERT: {m:,} filas comprobadas | fallos {fsb}")
            fallos += fsb

        # Forma y finitud de un lote real, pieza a pieza.
        lote = next(iter(self.batches(batch_size=256, shuffle=True, seed=seed,
                                      chunks_en_memoria=2)))
        dim_vista = 0
        ok = True
        for k, esperada in (("prott5", DIM_PROTT5), ("sbert", DIM_SBERT)):
            if k in lote:
                v = lote[k]
                bien = v.shape[1:] == (self.w, esperada) and np.isfinite(v).all()
                ok &= bool(bien)
                dim_vista += esperada
                print(f"  {k:7s} {v.shape} {v.dtype} | esperada "
                      f"({self.w}, {esperada}) y finito: {bien}")
        if "q3" in lote:
            v = lote["q3"]
            # 255 es "letra desconocida"; no deberia haber ninguna aqui porque
            # las filas sin estructura ya se han filtrado.
            bien = v.shape[1:] == (self.w,) and not (v == 255).any()
            ok &= bool(bien)
            dim_vista += 3
            print(f"  q3      {v.shape} {v.dtype} | esperada ({self.w},) y "
                  f"sin letras desconocidas: {bien}")
        ok &= dim_vista == self.dim
        print(f"  dimension total {dim_vista} | declarada {self.dim}: "
              f"{dim_vista == self.dim} | y {lote['y'].shape}")
        return fallos == 0 and ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True)
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--splits", required=True)
    ap.add_argument("--split", default="train")
    ap.add_argument("--embeddings-sbert",
                    help="directorio de SecondaryBERT por residuo; obligatorio "
                         "para --features primary_sbert y sbert")
    ap.add_argument("--features", choices=tuple(sorted(MODALIDADES)),
                    default="primary_secondary")
    ap.add_argument("--excluir-contradictorios", action="store_true")
    ap.add_argument("--permitir-sin-ss", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    ds = FragmentDataset(
        fragments=args.fragments, embeddings=args.embeddings, splits=args.splits,
        split=args.split, features=args.features,
        embeddings_sbert=args.embeddings_sbert,
        excluir_contradictorios=args.excluir_contradictorios,
        permitir_sin_ss=args.permitir_sin_ss,
    )
    if args.selftest:
        return 0 if ds.selftest() else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
