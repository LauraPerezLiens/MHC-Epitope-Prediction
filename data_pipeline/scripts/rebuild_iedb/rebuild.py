"""Rebuild IEDB evidence and 25-aa family windows in a new versioned destination."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import csv
from dataclasses import asdict, dataclass
from functools import cached_property, lru_cache
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tarfile
from threading import Lock, local
import time
import warnings

from Bio.Align import PairwiseAligner
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from data_pipeline.scripts.rebuild_iedb.structures import STRUCTURE_FIELDS, StructureArchive, packed_structure
from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, ROOT, output_lock, write_json


DEFAULT_INPUT = ROOT / "results/source_audits_inputs_20261118/data_intermediate"
DEFAULT_PRIOR = ROOT / "results/epitope_counterfactual_20261118"
ARCHIVE = ROOT / "data/used_data/data_raw.tar.zst"
PILOT = Path(__file__).with_name("pilot_selection.json")
QUALITATIVE = {"positive", "positivelow", "positiveintermediate", "positivemedium", "positivehigh"}
SPECIES = {"human": "homo sapiens", "mouse": "mus musculus"}
FAMILY_META = {family: (organism, mhc) for organism, mhc, family in FAMILIES}
AA = re.compile(r"[A-Z]+")
PLAIN_PEPTIDE = re.compile(r"[ACDEFGHIKLMNOPQRSTUVWY]+")
ACC = re.compile(r"[A-Za-z0-9_.-]+")
UNIPROT = re.compile(r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[0-9]+)?")
STRUCTURE_ID = re.compile(r"(?:/epitope/|^IEDB_EPITOPE:)(\d+)$")
ASSAY_ID = re.compile(r"(?:/assay/|^IEDB_ASSAY:)(\d+)$")
FIELDS = ("epitope__name", "epitope__modifications", "epitope__starting_position", "epitope__ending_position",
          "epitope__source_molecule_iri", "epitope__molecule_parent_iri", "epitope__epitope_iri", "epitope__iri",
          "assay_id__iedb_iri", "assay__iri", "assay__method/technique", "assay__measurement",
          "assay__qualitative_measurement", "mhc_restriction__name", "reference__iedb_iri", "reference__pmid")

def normalize_url(value):
    return re.sub(r"^https?://", "", value.strip()).rstrip("/")


def accession(url):
    part = normalize_url(url).rsplit("/", 1)[-1]
    return part if ACC.fullmatch(part) else ""


def eligible(row, organism, mhc, family):
    qualitative = re.sub(r"[^a-z]", "", row.get("assay__qualitative_measurement", "").lower())
    name = row.get("mhc_restriction__name", "").upper().replace("H-2-", "H2-")
    suffix = (r"(?:[A-Z][0-9]*)?" if organism == "mouse" else
              r"(?:[AB][0-9]+)?" if mhc == "mhc-II" else r"(?:W?[0-9]+)?")
    family_token = r"(?<![A-Z0-9])" + re.escape(family) + suffix + r"(?![A-Z0-9])"
    return (
        qualitative in QUALITATIVE
        and row.get("epitope__object_type", "").casefold() == "linear peptide"
        and all(SPECIES[organism] in row.get(key, "").casefold()
                for key in ("host__name", "epitope__source_organism"))
        and row.get("mhc_restriction__class", "").strip() == mhc.removeprefix("mhc-")
        and re.search(family_token, name) is not None
    )


def extract(archive, output, selection):
    stage = output / "raw"
    stage.mkdir(exist_ok=True)
    stats = {}
    csv.field_size_limit(16 * 1024 * 1024)
    with subprocess.Popen(["zstd", "-qdc", str(archive)], stdout=subprocess.PIPE) as proc:
        with tarfile.open(fileobj=proc.stdout, mode="r|", bufsize=1024 * 1024) as tar:
            for member in tar:
                path = Path(member.name)
                if not member.isfile() or path.name not in {"mhc_export_full.csv", "tcell_export_full.csv"}:
                    continue
                family = path.parent.name
                if family not in selection:
                    continue
                organism, mhc = FAMILY_META[family]
                assert path.parts == ("data_raw", organism, mhc, family, path.name)
                target = stage / f"{family}_{path.stem}.jsonl.gz"
                check = target.with_suffix(".json")
                if target.is_file() and check.is_file():
                    stats[target.name] = json.loads(check.read_text())
                    continue
                counts = Counter()
                partial = target.with_suffix(".partial")
                with tar.extractfile(member) as raw, gzip.open(partial, "wt") as sink:
                    reader = csv.DictReader(line.decode("utf-8") for line in raw)
                    for i, row in enumerate(reader):
                        parent = normalize_url(row.get("epitope__molecule_parent_iri", ""))
                        if selection[family] is not None and parent not in selection[family]:
                            continue
                        counts["in_parent_scope"] += 1
                        if not eligible(row, organism, mhc, family):
                            counts["filtered"] += 1
                            continue
                        event = {k: row.get(k, "") for k in FIELDS}
                        event.update(family=family, organism=organism, mhc_class=mhc,
                                     parent_url=parent, source_url=normalize_url(row.get("epitope__source_molecule_iri", "")),
                                     assay_type=path.name.split("_")[0], source_file=str(path), source_row_index=i)
                        sink.write(json.dumps(event) + "\n")
                        counts["included"] += 1
                partial.replace(target)
                write_json(check, dict(counts))
                stats[target.name] = dict(counts)
                print("EXTRACT", target.name, dict(counts), flush=True)
        while proc.stdout.read(1024 * 1024):
            pass
        if proc.wait():
            raise RuntimeError("Failed to decompress original IEDB archive")
    for family in selection:
        if not all(f"{family}_{typ}_export_full.jsonl.gz" in stats for typ in ("mhc", "tcell")):
            raise ValueError(f"Missing archived export for {family}")
    return stats


@dataclass(frozen=True)
class Reference:
    accession: str
    version: str
    sequence: str
    provider: str
    header: str

    @cached_property
    def sha256(self):
        return hashlib.sha256(self.sequence.encode()).hexdigest()


def fasta_records(text):
    for record in text.split(">")[1:]:
        header, *parts = record.splitlines()
        if not parts:
            continue
        ident = header.split()[0]
        identifiers = ident.split("|")
        if len(identifiers) >= 3 and identifiers[0] == "pdb":
            acc = f"{identifiers[1]}_{identifiers[2]}"
        else:
            acc = identifiers[1] if len(identifiers) >= 3 else ident
        version = re.search(r"\.(\d+)$", acc) or re.search(r"\bSV=(\d+)", header)
        seq = "".join(part.strip() for part in parts).upper()
        if AA.fullmatch(seq):
            yield Reference(acc, version[1] if version else "", seq, "", header)


def load_archived(path):
    archived = defaultdict(set)
    for organism in SPECIES:
        with (path / f"{organism}_parent_protein_fasta.csv").open(newline="") as f:
            for row in csv.DictReader(f):
                if row["id_full"] != row["resolved_id"]:
                    continue
                for ref in fasta_records(row["fasta"]):
                    archived[organism, normalize_url(row["protein_url"])].add(
                        Reference(row["resolved_id"], ref.version, ref.sequence, "archived_parent_fasta", ref.header))
    return {key: next(iter(refs)) for key, refs in archived.items() if len({(r.sequence, r.version) for r in refs}) == 1}


class Registry:
    def __init__(self, output, fasta_dir, prior):
        self.output = output
        self.archived = load_archived(fasta_dir)
        self.cache = output / "reference_cache"
        self.cache.mkdir(exist_ok=True)
        self.connections = local()
        self.reference_lock = Lock()
        self.prior_loci = defaultdict(list)
        self.cached = {}
        self.iedb = {}
        self.iedb_by_sequence = defaultdict(list)
        self.sequence_queried = set()
        if prior:
            for p in (prior / "source_batches").glob("*.fasta"):
                self.add_fasta(p.read_text(), "NCBI_versioned_cache")
            path = prior / "source_uniprot_sequences.json"
            if path.is_file():
                for acc, seq in json.loads(path.read_text()).items():
                    self.cached[acc] = Reference(acc, acc.rsplit(".", 1)[-1], seq, "UniProt_versioned_cache", "")
            path = prior / "iedb_records.json"
            if path.is_file():
                self.iedb = json.loads(path.read_text())
            path = prior / "event_resolution.csv"
            if path.is_file():
                with path.open(newline="") as stream:
                    for row in csv.DictReader(stream):
                        if row["confidence"] != "verified" or row["exact_residues"] != "True":
                            continue
                        key = (row["family"], normalize_url(row["source"]), normalize_url(row["parent"]),
                               row["epitope"], row["original_start"], row["original_end"])
                        self.prior_loci[key].append(row)

    def import_curated_caches(self, paths):
        for directory in paths:
            for path in sorted(directory.glob("*.fasta")):
                self.add_fasta(path.read_text(), "archived_reference_cache")
            for path in sorted(directory.glob("*.json")):
                records = json.loads(path.read_text())
                for record in records if isinstance(records, list) else ():
                    if isinstance(record, dict) and record.get("structure_id"):
                        key = str(record["structure_id"])
                        self.iedb[key] = {**self.iedb.get(key, {}), **record}
        for record in self.iedb.values():
            if record.get("linear_sequence"):
                self.iedb_by_sequence[record["linear_sequence"]].append(record)

    def request(self, url, params, extension, acceptable_missing=()):
        key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        path = self.cache / f"{key}.{extension}"
        if path.is_file():
            return path.read_text()
        if not hasattr(self.connections, "http"):
            self.connections.http = requests.Session()
        for attempt in range(4):
            try:
                r = self.connections.http.get(url, params=params, timeout=25)
                if r.status_code in acceptable_missing:
                    return ""
                r.raise_for_status()
                text = r.text
                tmp = path.with_suffix(".partial")
                tmp.write_text(text)
                tmp.replace(path)
                return text
            except requests.RequestException:
                if attempt == 3:
                    return None
                time.sleep(1 + attempt)
        return None

    def add_fasta(self, text, provider):
        with self.reference_lock:
            for item in fasta_records(text):
                current = Reference(item.accession, item.version, item.sequence, provider, item.header)
                old = self.cached.get(item.accession)
                if old is None or old.sequence == current.sequence:
                    self.cached[item.accession] = current
                else:
                    self.cached[item.accession] = Reference(item.accession, "", "", "conflicting_sequence", "")

    def prepare(self, events):
        need_ncbi, need_uniprot, ids, sequences = set(), set(), set(), set()
        for e in events:
            for url in (e["source_url"], e["parent_url"]):
                acc = accession(url)
                if not acc or (e["organism"], url) in self.archived or acc in self.cached:
                    continue
                if "uniprot.org/" in url and "." not in acc:
                    need_uniprot.add(acc)
                else:
                    need_ncbi.add(acc)
            epi_id, _ = identifiers(e)
            if epi_id and "e_modification" not in self.iedb.get(epi_id, {}):
                ids.add(epi_id)
            if not epi_id and AA.fullmatch(e["epitope__name"].strip().upper()):
                sequences.add(e["epitope__name"].strip().upper())
        print("REFERENCE LOOKUPS", len(need_ncbi), len(need_uniprot), "accessions", flush=True)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for fetch, keys in ((self.fetch_ncbi, need_ncbi), (self.fetch_uniprot, need_uniprot)):
                for _ in pool.map(fetch, batched(sorted(keys), 35)):
                    pass
        def load_batch(item):
            field, batch = item
            payload = self.request("https://query-api.iedb.org/epitope_search", {
                field: "in.(" + ",".join(batch) + ")",
                "select": "structure_id,linear_sequence,e_modification,curated_source_antigens,tcell_ids,elution_ids,iedb_assay_ids",
            }, "json")
            if not payload:
                raise RuntimeError(f"IEDB lookup failed for {field}; restart to reuse the download cache.")
            return field, batch, json.loads(payload)

        queries = [(field, batch) for field, keys in (
            ("structure_id", ids), ("linear_sequence", sequences - self.sequence_queried)
        ) for batch in batched(sorted(keys), 70)]
        print("IEDB LOOKUPS", len(queries), "batches", flush=True)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i, (field, batch, records) in enumerate(pool.map(load_batch, queries), 1):
                for record in records:
                    key = str(record["structure_id"])
                    self.iedb[key] = {**self.iedb.get(key, {}), **record}
                    if field == "linear_sequence" or record.get("linear_sequence") in sequences:
                        self.iedb_by_sequence[record.get("linear_sequence")].append(self.iedb[key])
                if field == "linear_sequence":
                    self.sequence_queried.update(batch)
                if i % 250 == 0:
                    print("IEDB LOOKUP PROGRESS", i, len(queries), flush=True)
        # The UniProt search endpoint reports sequence versions for canonical accessions.
        # An alternative-isoform FASTA is keyed only by its isoform ID, so fetching it
        # cannot populate the exact versioned key requested here.
        versioned = {acc.rsplit(".", 1)[0] for acc in need_ncbi
                     if acc not in self.cached and "." in acc and UNIPROT.fullmatch(acc.rsplit(".", 1)[0])}
        canonical = sorted(acc for acc in versioned if "-" not in acc)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in pool.map(self.fetch_uniprot, batched(canonical, 35)):
                pass
        print("REFERENCES", len(need_ncbi), len(need_uniprot), "IEDB identifiers", len(ids), flush=True)

    def fetch_ncbi(self, batch):
        text = self.request("https://www.ncbi.nlm.nih.gov/sviewer/viewer.fcgi",
                            {"db": "protein", "id": ",".join(batch), "report": "fasta", "retmode": "text"},
                            "fasta", (400, 404))
        if text and text.startswith(">"):
            self.add_fasta(text, "NCBI_public_fasta")
        elif len(batch) > 1 and text == "":
            middle = len(batch) // 2
            self.fetch_ncbi(batch[:middle])
            self.fetch_ncbi(batch[middle:])
        elif text is None:
            raise RuntimeError("NCBI lookup did not complete; restart to reuse the download cache.")

    def fetch_uniprot(self, batch):
        # Exact isoform accessions are retained as downloads, never replaced by the base accession.
        valid = [a for a in batch if UNIPROT.fullmatch(a)]
        canonical = [a for a in valid if "-" not in a]
        for acc in (a for a in valid if "-" in a):
            text = self.request(f"https://rest.uniprot.org/uniprotkb/{acc}.fasta", {}, "fasta", (404,))
            if text is None:
                raise RuntimeError("UniProt isoform lookup did not complete; rerun to resume.")
            if text:
                self.add_fasta(text, "UniProt_public_fasta")
        if not canonical:
            return
        text = self.request("https://rest.uniprot.org/uniprotkb/search", {
            "query": "(" + " OR ".join(f"accession:{acc}" for acc in canonical) + ")",
            "format": "tsv", "fields": "accession,sequence_version,sequence", "size": 100,
        }, "tsv", (400, 404))
        if text == "":
            if len(canonical) > 1:
                mid = len(canonical) // 2
                self.fetch_uniprot(canonical[:mid])
                self.fetch_uniprot(canonical[mid:])
            else:
                print("UNIPROT REFERENCE UNAVAILABLE", canonical[0], flush=True)
            return
        if text is None:
            raise RuntimeError("UniProt lookup did not complete; rerun to resume.")
        import io
        for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
            acc, ver, seq = r["Entry"], r["Sequence version"], r["Sequence"]
            if acc in canonical and ver and AA.fullmatch(seq):
                for name in (acc, f"{acc}.{ver}"):
                    self.cached.setdefault(name, Reference(name, ver, seq, "UniProt_public_exact_version", ""))

    def ref(self, organism, url):
        ref = self.archived.get((organism, url)) or self.cached.get(accession(url))
        return ref if ref and ref.sequence else None

    def curated(self, event, peptide):
        epi, assay = identifiers(event)
        if epi:
            record = self.iedb.get(epi)
            return [record] if record else []
        if not assay:
            return []
        return list({str(r["structure_id"]): r for r in self.iedb_by_sequence[peptide] if any(
            str(value) == assay for col in ("tcell_ids", "elution_ids", "iedb_assay_ids")
            for value in (r.get(col) or []))}.values())


def batched(values, size):
    for i in range(0, len(values), size):
        yield values[i:i+size]


def identifiers(event):
    def lookup(regex, keys):
        for key in keys:
            match = regex.search(event.get(key, ""))
            if match:
                return match[1]
        return ""
    return (lookup(STRUCTURE_ID, ("epitope__epitope_iri", "epitope__iri")),
            lookup(ASSAY_ID, ("assay_id__iedb_iri", "assay__iri")))


def source_witness(record, source):
    acc = record.get("accession", "")
    if "." in source.accession:
        return acc == source.accession
    if source.version and acc == f"{source.accession}.{source.version}":
        return True
    return acc == source.accession and source.provider.endswith("cache") and "_" in acc


def parent_witness(record, parent):
    acc = record.get("accession", "")
    iri = record.get("iri", "")
    if parent.version and parent.provider.startswith(("UniProt", "archived")):
        if iri == f"UNIPROT:{parent.accession.split('.')[0]}.{parent.version}":
            return True
    versioned = (parent.accession if re.search(r"\.\d+$", parent.accession)
                 else f"{parent.accession}.{parent.version}" if parent.version else "")
    return bool(versioned and acc == versioned)


def exact_at(sequence, peptide, start, end):
    return 1 <= start <= end <= len(sequence) and sequence[start - 1:end] == peptide


@lru_cache(maxsize=64)
def full_alignment(source, parent):
    if len(source) * len(parent) > 15_000_000:
        return None
    aligner = PairwiseAligner(match_score=2, mismatch_score=-3, open_gap_score=-9, extend_gap_score=-0.5)
    alignments = list(itertools.islice(aligner.align(source, parent), 65))
    if len(alignments) == 65:
        return None
    blocks = []
    for alignment in alignments:
        aligned = alignment.aligned
        lengths = sum(int(y - x) for x, y in aligned[0])
        matches = sum(sum(a == b for a, b in zip(source[x:y], parent[u:v]))
                      for (x, y), (u, v) in zip(*aligned))
        if not lengths or lengths / min(len(source), len(parent)) < 0.8 or matches / lengths < 0.8:
            return None
        blocks.append(aligned)
    return blocks


def project_interval(source, parent, start, end, peptide):
    if not exact_at(source, peptide, start, end):
        return None
    blocks = full_alignment(source, parent)
    if not blocks:
        return None
    positions = set()
    for alignment in blocks:
        segment = next(((int(u + start - x), int(u + end - x))
                        for (x, y), (u, v) in zip(*alignment) if x <= start - 1 and end <= y), None)
        positions.add(segment)
    if len(positions) == 1 and None not in positions:
        pos = next(iter(positions))
        if exact_at(parent, peptide, *pos):
            return pos
    return None


def verify_event(event, registry):
    source = registry.ref(event["organism"], event["source_url"])
    parent = registry.ref(event["organism"], event["parent_url"])
    original_name = event["epitope__name"].strip()
    peptide = original_name.upper()
    epi_id, assay_id = identifiers(event)
    records = registry.curated(event, peptide)
    recovered_structure = sorted({str(r["structure_id"]) for r in records})
    curated_modified = any(r.get("e_modification") for r in records)
    chemistry = ("modified" if event["epitope__modifications"].strip() or curated_modified else
                 "simple" if PLAIN_PEPTIDE.fullmatch(original_name) else "uncertain")
    backbones = {r.get("linear_sequence") or "" for r in records}
    backbones = sorted(seq for seq in backbones if AA.fullmatch(seq))
    result = dict(event_id=f"{event['source_file']}:{event['source_row_index']}", **event,
                  epitope=peptide, chemistry=chemistry, iedb_backbones=backbones,
                  iedb_modifications=json.dumps({str(r["structure_id"]): r["e_modification"]
                                                 for r in records if "e_modification" in r}, sort_keys=True),
                  structure_id=epi_id or "|".join(recovered_structure), assay_id=assay_id,
                  source_accession=source.accession if source else accession(event["source_url"]),
                  source_version=source.version if source else "", source_sha256=source.sha256 if source else "",
                  source_provider=source.provider if source else "",
                  parent_accession=parent.accession if parent else accession(event["parent_url"]),
                  parent_version=parent.version if parent else "", parent_sha256=parent.sha256 if parent else "",
                  parent_provider=parent.provider if parent else "",
                  source_start=None, source_end=None, parent_start=None, parent_end=None,
                  source_exact=False, parent_exact=False, method="", status="pending", reason="")
    if chemistry != "simple":
        return dict(result, reason="modified_peptide_excluded" if chemistry == "modified" else "unresolved_peptide_identity")
    if not epi_id and len(recovered_structure) > 1:
        return dict(result, reason="ambiguous_assay_epitope_link")
    if records and backbones != [peptide]:
        return dict(result, reason="iedb_linear_sequence_mismatch")
    if not assay_id or (not epi_id and not recovered_structure):
        return dict(result, reason="assay_or_epitope_identifier_unlinked")
    try:
        start, end = (int(event[f"epitope__{side}_position"]) for side in ("starting", "ending"))
    except ValueError:
        start = end = None
    result.update(source_start=start, source_end=end)
    if not parent:
        return dict(result, reason="parent_reference_unavailable")
    result["source_exact"] = bool(source and start is not None and exact_at(source.sequence, peptide, start, end))
    records_sources = [a for r in records for a in (r.get("curated_source_antigens") or [])]
    loci = {(a["starting_position"], a["ending_position"]) for a in records_sources
            if parent_witness(a, parent) and isinstance(a.get("starting_position"), int)
            and isinstance(a.get("ending_position"), int)
            and exact_at(parent.sequence, peptide, a["starting_position"], a["ending_position"])}
    key = (event["family"], event["source_url"], event["parent_url"], peptide,
           str(start), str(end))
    prior_positions = set()
    for row in registry.prior_loci.get(key, ()):
        interval = int(row["corrected_start"]), int(row["corrected_end"])
        if (result["structure_id"] in row["ids"].split("|") and assay_id in row["assays"].split("|")
                and row["parent_sequence_sha256"] == parent.sha256
                and exact_at(parent.sequence, peptide, *interval)):
            prior_positions.add(interval)
    if len(loci | prior_positions) > 1:
        return dict(result, reason="conflicting_parent_loci")
    if loci:
        pos, method = next(iter(loci)), "iedb_explicit_parent_reference"
    elif prior_positions:
        pos, method = next(iter(prior_positions)), "verified_prior_coordinate_audit"
    else:
        if start is None:
            return dict(result, reason="source_coordinates_missing_or_invalid")
        if not source:
            return dict(result, reason="source_reference_unavailable")
        if not result["source_exact"]:
            return dict(result, reason="source_interval_mismatch")
        # Unversioned sources require an exact version witness or a pinned chain.
        raw_accession = accession(event["source_url"])
        explicitly_versioned = "." in raw_accession and raw_accession == source.accession
        pinned_chain = bool(re.fullmatch(r"[0-9][A-Za-z0-9]{3}_[A-Za-z0-9]+", raw_accession)
                            and source.accession.upper() == raw_accession.upper())
        if not (explicitly_versioned or pinned_chain or any(
            source_witness(a, source) and (a.get("starting_position"), a.get("ending_position")) == (start, end)
            for a in records_sources
        )):
            return dict(result, reason="source_version_unpinned")
        if source.sequence == parent.sequence:
            pos, method = (start, end), "exact_whole_reference_identity"
        else:
            pos, method = project_interval(source.sequence, parent.sequence, start, end, peptide), "full_reference_alignment"
    if not pos:
        return dict(result, reason="parent_absent_or_projection_ambiguous")
    return dict(result, parent_start=pos[0], parent_end=pos[1], parent_exact=True, method=method, status="verified")


EVIDENCE_FIELDS = ("event_id", "family", "organism", "mhc_class", "source_file", "source_row_index", "assay_type",
                   "assay_id", "structure_id", "epitope", "chemistry", "iedb_backbones", "iedb_modifications", "source_url", "parent_url", "source_accession",
                   "source_version", "source_sha256", "source_provider", "parent_accession", "parent_version",
                   "parent_sha256", "parent_provider", "source_start", "source_end", "parent_start", "parent_end",
                   "source_exact", "parent_exact", "method", "status", "reason", *FIELDS)
EVIDENCE_SCHEMA = pa.schema([(k, pa.int64() if k in {
    "source_row_index", "source_start", "source_end", "parent_start", "parent_end"
} else pa.bool_() if k in {"source_exact", "parent_exact"} else pa.list_(pa.string()) if k == "iedb_backbones" else pa.string()) for k in EVIDENCE_FIELDS])
WINDOW_SCHEMA = pa.schema([
    ("window_id", pa.string()), ("family", pa.string()), ("organism", pa.string()), ("mhc_class", pa.string()),
    ("parent_url", pa.string()), ("parent_accession", pa.string()), ("parent_version", pa.string()),
    ("parent_sha256", pa.string()), ("window_start", pa.int64()), ("window_end", pa.int64()), ("sequence", pa.string()),
    ("contains_epitope", pa.int8()), ("pending_candidate", pa.bool_()),
])
PROVENANCE_SCHEMA = pa.schema([
    ("window_id", pa.string()), ("family", pa.string()), ("parent_url", pa.string()),
    ("window_start", pa.int64()), ("window_end", pa.int64()), ("sequence", pa.string()), ("contains_epitope", pa.int8()),
    ("verified_event_ids", pa.list_(pa.string())), ("pending_candidate_event_ids", pa.list_(pa.string())),
])
HOLDOUT_SCHEMA = pa.schema([
    ("window_id", pa.string()), ("family", pa.string()), ("parent_url", pa.string()),
    ("window_start", pa.int64()), ("window_end", pa.int64()), ("sequence", pa.string()), ("excluded_event_ids", pa.list_(pa.string())),
])
GLOBAL_SCHEMA = pa.schema([
    ("sequence", pa.string()), ("global_contains_epitope", pa.int8()), ("observations", pa.int64()),
    ("positive_observations", pa.int64()), ("pending_candidate_observations", pa.int64()),
])


class BufferedParquet:
    def __init__(self, path, schema):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.schema = path, schema
        self.partial = path.with_suffix(".partial")
        self.rows = []

    def __enter__(self):
        self.writer = pq.ParquetWriter(self.partial, self.schema, compression="zstd")
        return self

    def append(self, row):
        self.rows.append(row)
        if len(self.rows) == 20_000:
            self.flush()

    def flush(self):
        if self.rows:
            self.writer.write_table(pa.Table.from_pylist(self.rows, schema=self.schema))
            self.rows.clear()

    def __exit__(self, exc_type, exc, trace):
        try:
            if exc_type is None:
                self.flush()
        finally:
            self.writer.close()
        if exc_type is None:
            self.partial.replace(self.path)


def raw_records(output, family):
    for path in sorted((output / "raw").glob(f"{family}_*.jsonl.gz")):
        with gzip.open(path, "rt") as stream:
            for line in stream:
                yield json.loads(line)


def windows_for_interval(start, end, length):
    return range(max(1, end - 24), min(start, length - 24) + 1)


def pending_positions(sequence, peptide):
    # Candidates are flagged for review and cannot supply a positive label.
    if not AA.fullmatch(peptide) or len(peptide) > 25:
        return
    offset = sequence.find(peptide)
    while offset >= 0:
        yield from windows_for_interval(offset + 1, offset + len(peptide), len(sequence))
        offset = sequence.find(peptide, offset + 1)


def excluded_positions(sequence, event):
    # Exact backbone occurrences here are review candidates, never positive evidence.
    for peptide in event["iedb_backbones"]:
        yield from pending_positions(sequence, peptide)
    # Also protect legacy positives when historical name truncation used a different
    # peptide or IEDB did not resolve a backbone.
    legacy = AA.search(event["epitope"])
    if not legacy:
        return
    try:
        start, end = (int(event[f"epitope__{side}_position"]) for side in ("starting", "ending"))
    except ValueError:
        return
    if exact_at(sequence, legacy[0], start, end):
        yield from windows_for_interval(start, end, len(sequence))


def build_family(output, family, registry, structures=None, *, raw_input=None):
    organism, mhc = FAMILY_META[family]
    marker = output / "checkpoints" / f"{family}.json"
    if marker.is_file():
        return json.loads(marker.read_text())
    raw_input = output if raw_input is None else raw_input
    registry.prepare(raw_records(raw_input, family))
    refs = {}
    evidence = defaultdict(list)
    pending = defaultdict(list)
    excluded = defaultdict(list)
    counters = Counter()
    reasons = Counter()
    methods = Counter()
    used_references = {}
    with ExitStack() as stack:
        good = stack.enter_context(BufferedParquet(output / "evidence_verified" / f"{family}.parquet", EVIDENCE_SCHEMA))
        bad = stack.enter_context(BufferedParquet(output / "evidence_pending" / f"{family}.parquet", EVIDENCE_SCHEMA))
        for event in raw_records(raw_input, family):
            result = verify_event(event, registry)
            parent = event["parent_url"]
            if parent and parent not in refs:
                refs[parent] = registry.ref(organism, parent)
            for url in (event["source_url"], parent):
                if url and url not in used_references:
                    used_references[url] = registry.ref(organism, url)
            counters["events"] += 1
            counters[f"events_{result['chemistry']}"] += 1
            if result["status"] == "verified":
                good.append(result)
                evidence[parent].append((result["parent_start"], result["parent_end"], result["epitope"], result["event_id"]))
                counters["verified"] += 1
                methods[result["method"]] += 1
            else:
                bad.append(result)
                if result["chemistry"] == "simple":
                    pending[parent].append((result["epitope"], result["event_id"]))
                else:
                    excluded[parent].append(result)
                counters["pending"] += 1
                reasons[result["reason"]] += 1
        references = stack.enter_context(BufferedParquet(output / "references" / f"{family}.parquet", pa.schema([
            (key, pa.string()) for key in ("url", "accession", "version", "sequence", "provider", "header", "sha256")
        ])))
        for url, ref in sorted(used_references.items()):
            if ref:
                references.append(dict(url=url, **asdict(ref), sha256=ref.sha256))
        schema = WINDOW_SCHEMA if structures is None else pa.schema([*WINDOW_SCHEMA, *pa.schema(STRUCTURE_FIELDS)])
        windows = stack.enter_context(BufferedParquet(output / "families" / f"{family}.parquet", schema))
        trace = stack.enter_context(BufferedParquet(output / "provenance" / f"{family}.parquet", PROVENANCE_SCHEMA))
        holdouts = stack.enter_context(BufferedParquet(output / "holdouts" / f"{family}.parquet", HOLDOUT_SCHEMA))
        proteins = stack.enter_context(BufferedParquet(output / "proteins" / f"{family}.parquet", pa.schema([
            ("parent_url", pa.string()), ("sequence_length", pa.int64()), ("status", pa.string()),
            ("parent_sha256", pa.string()), ("expected_windows", pa.int64()),
            ("eligible_event_ids", pa.list_(pa.string())),
            ("structure_status", pa.string()), ("structure_prediction_id", pa.string()),
        ])))
        for url, ref in sorted(refs.items()):
            length = len(ref.sequence) if ref else 0
            total = max(0, length - 24)
            status = ("unresolved_reference" if not ref else "too_short" if not total else
                      "eligible" if url in evidence else "no_verified_simple_evidence")
            eligible_ids = sorted(event_id for _, _, _, event_id in evidence.get(url, ()))
            if status != "eligible":
                total = 0
            counters[f"proteins_{status}"] += 1
            structure_status, whole_structure, prediction_id = None, None, None
            if structures is not None and total:
                pinned = ref.provider == "archived_parent_fasta" and bool(ref.version or re.fullmatch(
                    r"[0-9][A-Za-z0-9]{3}_[A-Za-z0-9]+", ref.accession))
                structure_status, whole_structure, prediction_id = structures.resolve(organism, url, ref.sequence, pinned)
                counters[f"structural_proteins_{structure_status}"] += 1
            proteins.append(dict(parent_url=url, sequence_length=length, status=status,
                                 parent_sha256=ref.sha256 if ref else "", expected_windows=total,
                                 eligible_event_ids=eligible_ids, structure_status=structure_status,
                                 structure_prediction_id=prediction_id))
            if not total:
                continue
            positive, review, withheld = defaultdict(set), defaultdict(set), defaultdict(set)
            for a, b, epitope, event_id in evidence[url]:
                if not exact_at(ref.sequence, epitope, a, b):
                    raise ValueError(f"Verified evidence differs from the generation reference: {event_id}")
                for pos in windows_for_interval(a, b, length):
                    positive[pos].add(event_id)
            for peptide, event_id in pending[url]:
                for pos in pending_positions(ref.sequence, peptide):
                    review[pos].add(event_id)
            for event in excluded[url]:
                for pos in excluded_positions(ref.sequence, event):
                    withheld[pos].add(event["event_id"])
            ref_sha = ref.sha256
            for pos in range(1, total + 1):
                verified_ids, pending_ids = sorted(positive[pos]), sorted(review[pos])
                seq = ref.sequence[pos - 1:pos + 24]
                common = dict(window_id=f"{family}|{url}|{pos}", family=family, parent_url=url,
                              window_start=pos, window_end=pos + 24, sequence=seq)
                if pos in withheld and not verified_ids:
                    holdouts.append(dict(common, excluded_event_ids=sorted(withheld[pos])))
                    counters["held_out_windows"] += 1
                    continue
                common["contains_epitope"] = int(bool(verified_ids))
                counters["windows"] += 1
                counters["positive_windows"] += bool(verified_ids)
                counters["pending_candidate_windows"] += bool(pending_ids)
                row = dict(common, organism=organism, mhc_class=mhc, parent_accession=ref.accession,
                           parent_version=ref.version, parent_sha256=ref_sha, pending_candidate=bool(pending_ids))
                if structures is not None:
                    row.update(secondary_structure=whole_structure[pos - 1:pos + 24] if whole_structure else None,
                               structure_prediction_id=prediction_id, structure_status=structure_status)
                    counters[f"structural_windows_{structure_status}"] += 1
                windows.append(row)
                trace.append(dict(common, verified_event_ids=verified_ids, pending_candidate_event_ids=pending_ids))
    stats = dict(counters, methods=dict(methods), pending_reasons=dict(reasons))
    write_json(marker, stats)
    print("FAMILY", family, stats, flush=True)
    return stats


def reconcile_family(output, family, structures=None):
    refs = {r["url"]: r for batch in pq.ParquetFile(output / "references" / f"{family}.parquet").iter_batches()
            for r in batch.to_pylist()}
    for ref in refs.values():
        if hashlib.sha256(ref["sequence"].encode()).hexdigest() != ref["sha256"]:
            raise ValueError(f"Reference checksum mismatch for {ref['url']}")
    evidence = {}
    pending = {}
    for folder, table in (("evidence_verified", evidence), ("evidence_pending", pending)):
        for batch in pq.ParquetFile(output / folder / f"{family}.parquet").iter_batches():
            for r in batch.to_pylist():
                eid = r["event_id"]
                if eid in table:
                    raise ValueError(f"Duplicate evidence ID: {eid}")
                if table is evidence:
                    source, parent = refs.get(r["source_url"]), refs[r["parent_url"]]
                    direct_methods = {"iedb_explicit_parent_reference", "verified_prior_coordinate_audit"}
                    source_exact = bool(source and r["source_sha256"] == source["sha256"]
                                        and r["source_start"] is not None
                                        and exact_at(source["sequence"], r["epitope"], r["source_start"], r["source_end"]))
                    if (r["status"] != "verified" or r["chemistry"] != "simple"
                            or r["epitope__modifications"].strip() or not r["method"] or not r["assay_id"] or not r["structure_id"]
                            or r["source_exact"] != source_exact or not r["parent_exact"]
                            or (r["method"] not in direct_methods and not source_exact)
                            or any(json.loads(r["iedb_modifications"]).values())
                            or r["parent_sha256"] != parent["sha256"]
                            or not exact_at(parent["sequence"], r["epitope"], r["parent_start"], r["parent_end"])):
                        raise ValueError(f"Unverified coordinates used as evidence: {eid}")
                elif r["status"] != "pending" or not r["reason"]:
                    raise ValueError(f"Pending evidence has no reason: {eid}")
                table[eid] = r
    if evidence.keys() & pending.keys():
        raise ValueError(f"Verified and pending overlap in {family}")
    expected_positive = defaultdict(lambda: defaultdict(set))
    expected_review = defaultdict(lambda: defaultdict(set))
    expected_holdouts = defaultdict(lambda: defaultdict(set))
    eligible_ids = defaultdict(list)
    for eid, e in evidence.items():
        parent = e["parent_url"]
        eligible_ids[parent].append(eid)
        for pos in windows_for_interval(e["parent_start"], e["parent_end"], len(refs[parent]["sequence"])):
            expected_positive[parent][pos].add(eid)
    for eid, e in pending.items():
        parent = e["parent_url"]
        if parent not in eligible_ids:
            continue
        sequence = refs[parent]["sequence"]
        if e["chemistry"] == "simple":
            for pos in pending_positions(sequence, e["epitope"]):
                expected_review[parent][pos].add(eid)
        else:
            for pos in excluded_positions(sequence, e):
                if pos not in expected_positive[parent]:
                    expected_holdouts[parent][pos].add(eid)
    manifest = {
        r["parent_url"]: r
        for b in pq.ParquetFile(output / "proteins" / f"{family}.parquet").iter_batches()
        for r in b.to_pylist()
    }
    event_parents = {e["parent_url"] for table in (evidence, pending) for e in table.values() if e["parent_url"]}
    if manifest.keys() != event_parents:
        raise ValueError(f"Some scoped parent references are missing from the protein manifest in {family}")
    for url, protein in manifest.items():
        length = len(refs[url]["sequence"]) if url in refs else 0
        expected = max(0, length - 24) if url in eligible_ids else 0
        if protein["expected_windows"] != expected or protein["eligible_event_ids"] != sorted(eligible_ids.get(url, ())):
            raise ValueError(f"Wrong eligibility or expected window count for {url}")
    counts = Counter()
    counts["verified_events"] = len(evidence)
    counts["pending_events"] = len(pending)
    observed = Counter()
    last_start = {}
    structural_refs = {}
    remaining_holdouts = {url: dict(positions) for url, positions in expected_holdouts.items()}
    for batch in pq.ParquetFile(output / "holdouts" / f"{family}.parquet").iter_batches():
        for row in batch.to_pylist():
            url, start = row["parent_url"], row["window_start"]
            ids = remaining_holdouts.get(url, {}).pop(start, None)
            if (not ids or sorted(ids) != row["excluded_event_ids"] or row["family"] != family
                    or row["window_end"] != start + 24 or row["window_id"] != f"{family}|{url}|{start}"
                    or not exact_at(refs[url]["sequence"], row["sequence"], start, start + 24)):
                raise ValueError(f"Unexpected or incorrect held-out window: {row['window_id']}")
            counts["held_out_windows"] += 1
    if any(remaining_holdouts.values()):
        raise ValueError(f"Missing held-out positions for {family}")
    window = pq.ParquetFile(output / "families" / f"{family}.parquet")
    provenance = pq.ParquetFile(output / "provenance" / f"{family}.parquet")
    for batch, trace in itertools.zip_longest(window.iter_batches(), provenance.iter_batches()):
        if batch is None or trace is None or len(batch) != len(trace):
            raise ValueError("Mismatched provenance row groups")
        for row, line in zip(batch.to_pylist(), trace.to_pylist(), strict=True):
            for key in ("window_id", "family", "parent_url", "window_start", "window_end", "sequence", "contains_epitope"):
                if row[key] != line[key]:
                    raise ValueError(f"Provenance differs from window: {row['window_id']}")
            url, start = row["parent_url"], row["window_start"]
            observed[url] += 1
            ref = refs[url]
            if (start <= last_start.get(url, 0) or start > manifest[url]["expected_windows"]
                    or start in expected_holdouts.get(url, {}) or row["family"] != family
                    or row["window_end"] != start + 24 or row["window_id"] != f"{family}|{url}|{start}"
                    or row["parent_sha256"] != ref["sha256"]
                    or not exact_at(ref["sequence"], row["sequence"], start, start + 24)):
                raise ValueError(f"Missing, duplicate or incorrect window: {row['window_id']}")
            last_start[url] = start
            if structures is not None:
                if url not in structural_refs:
                    pinned = ref["provider"] == "archived_parent_fasta" and bool(
                        ref["version"] or re.fullmatch(r"[0-9][A-Za-z0-9]{3}_[A-Za-z0-9]+", ref["accession"]))
                    structural_refs[url] = structures.resolve(FAMILY_META[family][0], url, ref["sequence"], pinned)
                status, structural_sequence, prediction_id = structural_refs[url]
                expected = structural_sequence[start - 1:start + 24] if structural_sequence else None
                if (row["secondary_structure"], row["structure_prediction_id"], row["structure_status"]) != (
                        expected, prediction_id, status):
                    raise ValueError(f"Incorrect structural mapping: {row['window_id']}")
                counts[f"structural_windows_{status}"] += 1
            verified_ids = expected_positive[url].get(start, set())
            pending_ids = expected_review[url].get(start, set())
            if (line["verified_event_ids"] != sorted(verified_ids) or row["contains_epitope"] != bool(verified_ids)
                    or line["pending_candidate_event_ids"] != sorted(pending_ids)
                    or row["pending_candidate"] != bool(pending_ids)):
                raise ValueError(f"Window evidence differs from the independently enumerated intervals: {row['window_id']}")
            counts["positive_windows"] += row["contains_epitope"]
            counts["pending_candidate_windows"] += row["pending_candidate"]
            counts["windows"] += 1
    expected_counts = Counter({url: r["expected_windows"] - len(expected_holdouts.get(url, {}))
                               for url, r in manifest.items()})
    if observed != +expected_counts:
        raise ValueError(f"Missing window positions for {family}")
    return dict(counts)


def global_counts(output, families, structural=False, *, work_db=None):
    with closing(sqlite3.connect(work_db if work_db is not None else output / "global_work.sqlite")) as db:
        db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA cache_size=-131072;
          CREATE TABLE IF NOT EXISTS counts(seq TEXT PRIMARY KEY, observations INT, positives INT, candidates INT)
          WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS done(family TEXT, batch INTEGER, PRIMARY KEY(family,batch)) WITHOUT ROWID;
        """)
        columns = ["sequence", "contains_epitope", "pending_candidate"]
        if structural:
            columns.append("secondary_structure")
            db.execute("CREATE TABLE IF NOT EXISTS pairs(seq TEXT, ss INTEGER, PRIMARY KEY(seq,ss)) WITHOUT ROWID")
        for family in families:
            done = {i for (i,) in db.execute("SELECT batch FROM done WHERE family=?", (family,))}
            for i, batch in enumerate(pq.ParquetFile(output / "families" / f"{family}.parquet").iter_batches(
                batch_size=100_000, columns=columns,
            )):
                if i in done:
                    continue
                counts = defaultdict(lambda: [0, 0, 0])
                for seq, label, pending in zip(*(batch.column(i).to_pylist() for i in range(3))):
                    values = counts[seq]
                    values[0] += 1
                    values[1] += label
                    values[2] += pending
                with db:
                    db.executemany("""INSERT INTO counts VALUES(?,?,?,?)
                        ON CONFLICT(seq) DO UPDATE SET observations=counts.observations+excluded.observations,
                        positives=counts.positives+excluded.positives,candidates=counts.candidates+excluded.candidates""",
                        ((seq, *counts[seq]) for seq in sorted(counts)))
                    if structural:
                        pairs = {(seq, packed_structure(ss)) for seq, ss in zip(
                            batch.column(0).to_pylist(), batch.column(3).to_pylist()) if ss is not None}
                        db.executemany("INSERT OR IGNORE INTO pairs VALUES (?,?)", sorted(pairs))
                    db.execute("INSERT INTO done VALUES (?,?)", (family, i))
        with BufferedParquet(output / "global_index.parquet", GLOBAL_SCHEMA) as writer:
            for seq, total, positives, candidates in db.execute(
                "SELECT seq, observations, positives, candidates FROM counts ORDER BY seq"
            ):
                writer.append(dict(sequence=seq, global_contains_epitope=int(positives > 0),
                                   observations=total, positive_observations=positives,
                                   pending_candidate_observations=candidates))
        cursor = iter(db.execute("SELECT seq,observations,positives,candidates FROM counts ORDER BY seq"))
        stats = Counter()
        for batch in pq.ParquetFile(output / "global_index.parquet").iter_batches():
            for row in batch.to_pylist():
                expected = next(cursor, None)
                actual = (row["sequence"], row["observations"], row["positive_observations"],
                          row["pending_candidate_observations"])
                if actual != expected or row["global_contains_epitope"] != bool(row["positive_observations"]):
                    raise ValueError("Global index differs from the unique per-sequence aggregate")
                stats["unique_sequences"] += 1
                stats["positive_sequences"] += row["global_contains_epitope"]
                stats["observations"] += row["observations"]
                stats["positive_observations"] += row["positive_observations"]
        if next(cursor, None) is not None:
            raise ValueError("Global sequence index lacks entries")
        if structural:
            stats["unique_primary_secondary_pairs"] = db.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
        return dict(stats)


def old_comparison(output, old, families, selection):
    config = json.loads((old / "config.json").read_text())
    mapping = {source["mhc_family"]: source for source in config["sources"]}
    comparison = {}
    for family in families:
        source = mapping[family]
        path = old / "rows" / f"{source['organism']}_{source['mhc_class']}_{family}.parquet"
        positions = defaultdict(bytearray)
        stats = Counter()
        wanted = selection[family]
        for batch in pq.ParquetFile(path).iter_batches(
            batch_size=100_000, columns=["protein_url", "window_start", "contains_epitope"],
        ):
            # The historical label tables store original coordinates as decimal text.
            starts = batch.column(1).cast(pa.int64()).to_pylist()
            for url, start, label in zip(batch.column(0).to_pylist(), starts, batch.column(2).to_pylist()):
                url = normalize_url(url)
                if wanted is not None and url not in wanted:
                    continue
                stats["old_rows"] += 1
                slots = positions[url]
                if start >= len(slots):
                    slots.extend(bytes(start + 1 - len(slots)))
                existing = slots[start]
                if existing:
                    stats["old_duplicate_position_rows"] += 1
                else:
                    stats["old_unique_positions"] += 1
                if label and existing != 2:
                    stats["old_positive_positions"] += 1
                slots[start] = max(existing, label + 1)
        for folder in ("families", "holdouts"):
            columns = ["parent_url", "window_start"]
            if folder == "families":
                columns.append("contains_epitope")
            for batch in pq.ParquetFile(output / folder / f"{family}.parquet").iter_batches(columns=columns):
                for url, start, *labels in zip(*(col.to_pylist() for col in batch.columns)):
                    slots = positions.get(url)
                    prior_label = slots[start] if slots and start < len(slots) else 0
                    if folder == "holdouts":
                        if prior_label:
                            slots[start] = 0
                            stats["old_positions_in_holdouts"] += 1
                            stats["old_positive_positions_in_holdouts"] += prior_label == 2
                        continue
                    label = labels[0]
                    if not prior_label:
                        stats["new_positions"] += 1
                        stats["new_positive_positions"] += label
                        if slots is None:
                            stats["positions_on_previously_omitted_proteins"] += 1
                    else:
                        slots[start] = 0
                        if prior_label - 1 == label:
                            stats["positions_unchanged"] += 1
                        else:
                            stats[f"position_{prior_label - 1}_to_{label}"] += 1
        stats["old_positions_missing_in_rebuild"] = stats["old_positions_in_holdouts"]
        for slots in positions.values():
            stats["old_positions_missing_in_rebuild"] += slots.count(1) + slots.count(2)
            stats["old_positive_positions_elsewhere_excluded"] += slots.count(2)
        comparison[family] = dict(stats)
        print("HISTORICAL COMPARISON", family, dict(stats), flush=True)
    return comparison


def signature(path):
    stat = path.stat()
    return [str(path.resolve()), stat.st_size, stat.st_mtime_ns]


def input_content_hashes(manifest):
    records = [manifest["archive"], *manifest["fasta"], *manifest.get("structure_inputs", {}).values()]
    hashes = {}
    for record in records:
        path = Path(record[0])
        checksum = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(chunk)
        if signature(path) != record:
            raise ValueError(f"Input changed during content verification: {path}")
        hashes[str(path)] = checksum.hexdigest()
    return hashes


def run(output, archive, fasta, prior, selection, old, structure_dir=None, local_caches=(),
        *, verify_input_content=False):
    output = output.resolve()
    protected = [archive.parent, fasta, old, *local_caches]
    protected.extend(path for path in (prior, structure_dir) if path is not None)
    if any(output.is_relative_to(path.resolve()) or path.resolve().is_relative_to(output) for path in protected):
        raise ValueError("Output must be separate from all input directories")
    scope = {family: None if urls is None else sorted(urls) for family, urls in selection.items()}
    manifest = dict(version=2, scope=scope, archive=signature(archive),
                    fasta=[signature(fasta / f"{org}_parent_protein_fasta.csv") for org in SPECIES],
                    prior=str(prior.resolve()) if prior else None, previous_dataset=str(old.resolve()))
    structural_paths = {org: structure_dir / f"secondary_struct_{org}.csv" for org in SPECIES} if structure_dir else {}
    if structure_dir:
        manifest["structure_inputs"] = {org: signature(path) for org, path in structural_paths.items()}
    if local_caches:
        manifest["local_caches"] = [str(path.resolve()) for path in local_caches]
    output.mkdir(parents=True, exist_ok=True)
    with output_lock(output):
        cfg = output / "config.json"
        existing = json.loads(cfg.read_text()) if cfg.exists() else None
        if existing is not None:
            recorded_verification = "input_sha256" in existing
            if recorded_verification != verify_input_content:
                raise ValueError("Input content verification mode differs. Use the original mode or a new versioned output.")
        elif set(output.iterdir()) - {output / ".run.lock", output / "config.json.partial"}:
            raise ValueError("Use a new output directory.")
        if verify_input_content:
            manifest["input_sha256"] = input_content_hashes(manifest)
        if existing is None:
            write_json(cfg, manifest)
        elif existing != manifest:
            raise ValueError("Inputs or scope changed. Use a new versioned output.")
        elif not verify_input_content:
            warnings.warn("Resuming with historical metadata signatures. Input content has not been verified.",
                          RuntimeWarning, stacklevel=2)
        started = time.monotonic()
        (output / "checkpoints").mkdir(exist_ok=True)
        raw_stats = extract(archive, output, selection)
        registry = Registry(output, fasta, prior)
        structures = StructureArchive(structural_paths) if structural_paths else None
        registry.import_curated_caches(local_caches)
        family_stats = {family: build_family(output, family, registry, structures) for family in selection}
        validation = {}
        for family in selection:
            validation[family] = reconcile_family(output, family, structures)
            print("RECONCILED", family, validation[family], flush=True)
        if verify_input_content and input_content_hashes(manifest) != manifest["input_sha256"]:
            raise ValueError("Input content changed during reconstruction")
        finalize(output, old, selection, family_stats, validation, raw_stats, started,
                 structural=structures is not None)


def finalize(output, old, selection, family_stats, validation, raw_stats, started, *,
             structural, work_db=None):
    for family, status in validation.items():
        for field in ("windows", "positive_windows", "pending_candidate_windows", "held_out_windows"):
            if status.get(field, 0) != family_stats[family].get(field, 0):
                raise ValueError(f"Validation total differs for {family}/{field}")
        raw_count = sum(v.get("included", 0) for k, v in raw_stats.items() if k.startswith(f"{family}_"))
        if status["verified_events"] + status["pending_events"] != raw_count:
            raise ValueError(f"Evidence records lost in {family}")
    glob = global_counts(output, selection, structural=structural, work_db=work_db)
    if (glob.get("observations", 0) != sum(v.get("windows", 0) for v in validation.values())
            or glob.get("positive_observations", 0) != sum(v.get("positive_windows", 0) for v in validation.values())):
        raise ValueError("Global row totals differ from the validated family tables")
    comparison = old_comparison(output, old, selection, selection)
    summary = dict(status="validated", scope="full" if all(v is None for v in selection.values()) else "pilot",
                   families=family_stats, raw=raw_stats, validation=validation, global_index=glob,
                   previous=comparison, seconds=round(time.monotonic() - started, 2))
    write_json(output / "summary.json", summary)
    print("VALIDATED", glob, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--fasta", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--prior", type=Path, default=DEFAULT_PRIOR)
    parser.add_argument("--old", type=Path, default=ROOT / "data/global_epitope_labels")
    parser.add_argument("--structure-dir", type=Path)
    parser.add_argument("--curated-cache", type=Path, action="append", default=[])
    parser.add_argument("--verify-input-content", action="store_true",
                        help="Read and hash the archive, FASTA and structure inputs in full")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--pilot", type=Path)
    scope.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.full:
        selection = dict.fromkeys(FAMILY_META)
    else:
        selection = {family: set(map(normalize_url, urls))
                     for family, urls in json.loads(args.pilot.read_text()).items()}
        if not selection or not set(selection).issubset(FAMILY_META) or any(not v for v in selection.values()):
            parser.error("The pilot needs at least one known family with non-empty parent selections.")
    run(args.output, args.archive, args.fasta, args.prior, selection, args.old, args.structure_dir, args.curated_cache,
        verify_input_content=args.verify_input_content)


if __name__ == "__main__":
    main()
