#!/usr/bin/env python3
"""Descarga certificada de IEDB para NAP-CNB.

Sustituye a build_iedb_dataset.py. Tres diferencias de fondo, todas
justificadas por los hallazgos de la verificacion del 24 nov 2026
(CLAUDE.md, seccion 0.6.3):

1. PAGINACION KEYSET sobre assay_id (order=assay_id.asc + assay_id=gt.N).
   El script antiguo usaba `offset` SIN `order`, que en PostgREST no
   garantiza orden estable entre paginas. De hecho no danio los datos
   (hallazgo A bis: 0 duplicados, 1 fila perdida), pero es fragil por
   diseno y no debe repetirse.

2. LOS NEGATIVOS NO SE EXCLUYEN POR DEFECTO. El script antiguo imponia
   `assay__qualitative_measurement = ilike.*Positive*`, de modo que el
   pipeline NUNCA vio un ensayo negativo de IEDB y sus "negativos" eran
   ventanas sin anotacion (tarea positive-unlabeled). Wert2021, en
   cambio, construia negativos explicitos. Ahora se descarga el valor
   cualitativo tal cual y el filtrado se decide en el procesado.

3. EL FILTRO DE ORGANISMO FUENTE ES EXPLICITO. El script antiguo imponia
   `epitope__source_organism = ilike.*<especie>*`, que restringe a
   epitopos de origen propio y excluye los derivados de patogeno. Es la
   causa de que solo compartamos el 56 % de los positivos H-2Kb de
   Wert2021 (hallazgo D). Ahora es una eleccion de perfil, documentada.

Perfiles (--profile, obligatorio):

  legacy  Filtros IDENTICOS a build_iedb_dataset.py: solo *Positive*,
          solo epitopos de la propia especie. Reproduce el universo de
          D1. Usar para verificar procedencia, no para datos nuevos.

  full    Sin filtro cualitativo y sin filtro de organismo fuente.
          Superconjunto: incluye negativos experimentales y epitopos de
          patogeno. Es el universo de Wert2021 y el necesario para E0.
          Mucho mas grande; vigilar disco.

El alelo (`mhc_restriction__name`) se conserva literal en la salida. La
familia solo se usa para enumerar las consultas, NO como etiqueta de
entrenamiento: el pipeline antiguo colapsaba 276 alelos en 11 familias
(hallazgo F) y eso es el primer problema de diseno del modelo.

Manifiesto: IEDB no publica endpoint de release, asi que la procedencia
se certifica con una HUELLA DE CONTENIDO por consulta (numero de filas,
max/min assay_id, sha256 del CSV) mas la fecha UTC, los parametros
exactos y el commit de git. Reanudable: las consultas ya presentes en el
manifiesto con huella valida se omiten.

Uso:
    python build_iedb_dataset_v2.py --profile full --out DIR
    python build_iedb_dataset_v2.py --profile legacy --out DIR --only mouse/mhc-I/H2-K
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ENDPOINTS = {
    "mhc": "https://query-api.iedb.org/mhc_export",
    "tcell": "https://query-api.iedb.org/tcell_export",
}

# (especie, carpeta de clase, numero de clase IEDB, familias)
FAMILIES = [
    ("mouse", "mhc-I", "I", ["H2-K", "H2-D", "H2-L"]),
    ("mouse", "mhc-II", "II", ["H2-IA", "H2-IE"]),
    ("human", "mhc-I", "I", ["HLA-A", "HLA-B", "HLA-C"]),
    ("human", "mhc-II", "II", ["HLA-DR", "HLA-DQ", "HLA-DP"]),
]

HOST_NAME = {"mouse": "Mus musculus", "human": "Homo sapiens"}

PAGE_LIMIT = 10000
REQUEST_TIMEOUT = 600

log = logging.getLogger("iedb")


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def build_params(profile: str, species: str, class_num: str, family: str) -> dict:
    """Parametros de consulta. Documenta que impone cada filtro."""
    params = {
        # Excluye epitopos discontinuos y no-peptidos (grupos quimicos,
        # acidos sulfonicos...). Se conserva en los dos perfiles.
        "epitope__object_type": "eq.Linear peptide",
        "mhc_restriction__class": "eq.%s" % class_num,
        # Especie del HOSPEDADOR del ensayo.
        "host__name": "ilike.*%s*" % HOST_NAME[species],
        # Coincidencia por SUBCADENA: solo enumera, no etiqueta.
        "mhc_restriction__name": "ilike.*%s*" % family,
    }
    if profile == "legacy":
        # Solo ensayos positivos: admite Positive, -High, -Intermediate,
        # -Low sin distinguirlos. Deja fuera TODO negativo experimental.
        params["assay__qualitative_measurement"] = "ilike.*Positive*"
        # Solo epitopos de origen propio: excluye los de patogeno.
        params["epitope__source_organism"] = "ilike.*%s*" % HOST_NAME[species]
    return params


def fetch_all(session: requests.Session, url: str, params: dict) -> list[dict]:
    """Paginacion keyset sobre assay_id, que es unico y ordenable.

    Frente a offset: cada pagina pide `assay_id > ultimo visto`, asi que
    el conjunto resultante no depende de que el servidor mantenga un
    orden estable entre peticiones.
    """
    rows: list[dict] = []
    last_id = None
    page = 0
    while True:
        query = dict(params)
        query["limit"] = PAGE_LIMIT
        query["order"] = "assay_id.asc"
        if last_id is not None:
            query["assay_id"] = "gt.%d" % last_id

        started = time.time()
        response = session.get(url, params=query, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        batch = response.json()
        log.info("  page=%d n=%d %.1fs", page, len(batch), time.time() - started)

        if not batch:
            break
        rows.extend(batch)

        batch_max = max(row["assay_id"] for row in batch)
        if batch_max == last_id:
            # Defensa: sin avance de clave, cortar antes de bucle infinito.
            log.warning("  assay_id no avanza (%s); corto", batch_max)
            break
        last_id = batch_max
        page += 1
        if len(batch) < PAGE_LIMIT:
            break
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    """Escribe union de claves ordenada, para cabecera estable entre ejecuciones."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(rows: list[dict], path: Path) -> dict:
    """Huella de contenido: sustituto de la release de IEDB, que no se publica."""
    ids = [row["assay_id"] for row in rows if row.get("assay_id") is not None]
    return {
        "n_rows": len(rows),
        "min_assay_id": min(ids) if ids else None,
        "max_assay_id": max(ids) if ids else None,
        "n_distinct_assay_id": len(set(ids)),
        "n_distinct_alleles": len({row.get("mhc_restriction__name") for row in rows}),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def load_manifest(path: Path, profile: str) -> dict:
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("profile") != profile:
            raise SystemExit(
                "El manifiesto de %s es del perfil %r y se ha pedido %r. "
                "Usa otro --out para no mezclar universos de datos."
                % (path, manifest.get("profile"), profile)
            )
        return manifest
    return {
        "profile": profile,
        "script": Path(__file__).name,
        "git_commit": git_commit(),
        "pagination": "keyset on assay_id.asc",
        "page_limit": PAGE_LIMIT,
        "iedb_release": "no lo publica la API; ver fingerprint por consulta",
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "queries": {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, choices=["legacy", "full"],
                        help="legacy = filtros de build_iedb_dataset.py; "
                             "full = sin filtro cualitativo ni de organismo fuente")
    parser.add_argument("--out", required=True, type=Path, help="directorio de salida")
    parser.add_argument("--only", action="append", default=None,
                        metavar="especie/clase/familia",
                        help="limitar a estas familias (repetible)")
    parser.add_argument("--exports", default="mhc,tcell",
                        help="exports a descargar, separados por coma")
    parser.add_argument("--force", action="store_true",
                        help="re-descargar aunque el manifiesto ya la tenga")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s: %(message)s")

    exports = [e.strip() for e in args.exports.split(",") if e.strip()]
    for export in exports:
        if export not in ENDPOINTS:
            raise SystemExit("export desconocido: %r" % export)

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    manifest = load_manifest(manifest_path, args.profile)

    session = make_session()
    planned = [
        (species, class_dir, class_num, family)
        for species, class_dir, class_num, families in FAMILIES
        for family in families
    ]
    if args.only:
        wanted = set(args.only)
        planned = [p for p in planned
                   if "%s/%s/%s" % (p[0], p[1], p[3]) in wanted]
        if not planned:
            raise SystemExit("--only no coincide con ninguna familia conocida")

    for species, class_dir, class_num, family in planned:
        key = "%s/%s/%s" % (species, class_dir, family)
        target_dir = args.out / species / class_dir / family
        target_dir.mkdir(parents=True, exist_ok=True)
        entry = manifest["queries"].setdefault(key, {})

        for export in exports:
            csv_path = target_dir / ("%s_export_full.csv" % export)
            done = entry.get(export)
            if done and not args.force and csv_path.exists():
                log.info("=== %s %s: ya en el manifiesto (n=%s), omito",
                         key, export, done.get("fingerprint", {}).get("n_rows"))
                continue

            params = build_params(args.profile, species, class_num, family)
            log.info("=== %s %s (profile=%s) ===", key, export, args.profile)
            rows = fetch_all(session, ENDPOINTS[export], params)
            write_csv(rows, csv_path)
            entry[export] = {
                "endpoint": ENDPOINTS[export],
                "params": params,
                "file": str(csv_path.relative_to(args.out)),
                "downloaded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "fingerprint": fingerprint(rows, csv_path),
            }
            log.info("  -> %s n=%d sha256=%s", csv_path.name, len(rows),
                     entry[export]["fingerprint"]["sha256"][:16])
            # Escritura incremental: reanudable por inspeccion del manifiesto.
            manifest["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    log.info("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
