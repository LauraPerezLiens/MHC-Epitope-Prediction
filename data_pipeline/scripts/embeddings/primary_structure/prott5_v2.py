"""Generate one reproducible ProtT5 vector per exact primary sequence in NAP-CNB v2."""

import argparse
import fcntl
from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
from time import perf_counter

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

EXPECTED_SEQUENCES = 14_530_324
EXPECTED_WINDOWS = 49_123_503
MODEL = "Rostlab/prot_t5_xl_half_uniref50-enc"
REVISION = "94a6abc029ae13029317b140b7424e012bf8dfbf"
WIDTH = 1024
SHARD_ROWS = 100_000
SEED = 20261119
CANONICAL = "ACDEFGHIKLMNPQRSTVWY"
STANDARD = frozenset(CANONICAL)
ALPHABET = re.compile(r"[ACDEFGHIKLMNPQRSTVWYXUBZ]{25}")
RESIDUE_MAP = str.maketrans("UBZ", "XXX")
INVENTORY = Path("results/nap_cnb_v2_embedding_audit/missing_prott5_sequences.parquet")
SELECTION = Path("results/nap_cnb_v2_final_selection/selection.json")
CHECKPOINT = Path("/tmp/nap_prott5_3a/checkpoint")
HASHES = Path("results/nap_cnb_v2_prott5_audit_3a/checkpoint_hashes.json")


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            digest.update(data)
    return digest.hexdigest()


def input_sequence(sequence):
    if not ALPHABET.fullmatch(sequence):
        raise ValueError(f"Unexpected primary sequence alphabet or length: {sequence!r}")
    return sequence.translate(RESIDUE_MAP)


def load_inventory(path, selection):
    spec = json.loads(selection.read_text())
    if spec["totals"]["positive_final"] + spec["totals"]["negative_final"] != EXPECTED_WINDOWS:
        raise ValueError("Selection window count differs")
    for entry in spec["input_signatures"]:
        stat = (selection.parent / entry["path"]).stat()
        if (stat.st_size, stat.st_mtime_ns) != (entry["bytes"], entry["mtime_ns"]):
            raise ValueError(f"Selection input changed: {entry['path']}")
    for name, expected in spec["supplement_sha256"].items():
        if sha_file(selection.parent / name) != expected:
            raise ValueError(f"Selection supplement changed: {name}")
    table = pq.read_table(path, columns=["sequence", "windows"])
    if table.num_rows != EXPECTED_SEQUENCES or pc.sum(table["windows"]).as_py() != EXPECTED_WINDOWS:
        raise ValueError("Historical audit inventory does not cover the definitive selection")
    return table["sequence"]


def audit_inventory(sequences):
    raw = set()
    hashes = set()
    transformed_special = set()
    special = 0
    for chunk in sequences.chunks:
        for sequence in chunk.to_pylist():
            transformed = input_sequence(sequence)
            raw.add(sequence)
            hashes.add(hashlib.sha256(sequence.encode("ascii")).digest())
            if set(sequence) - STANDARD:
                special += 1
                transformed_special.add(transformed)
    if len(raw) != len(sequences) or len(hashes) != len(sequences):
        raise ValueError("Duplicate primary or SHA-256 collision; resolve using the exact sequence ID")
    return dict(unique=len(raw), sha256_collisions=len(raw)-len(hashes), special_sequences=special,
                preprocessing_collisions=special-len(transformed_special))


class Encoder:
    def __init__(self, checkpoint, hashes, precision):
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import sentencepiece
        import torch
        from transformers import T5EncoderModel, T5Tokenizer

        expected = json.loads(hashes.read_text())
        for name, checksum in expected.items():
            if sha_file(checkpoint / name) != checksum:
                raise ValueError(f"Checkpoint checksum mismatch: {name}")
        if torch.cuda.device_count() != 1:
            raise RuntimeError("Expose exactly one GPU through CUDA_VISIBLE_DEVICES")
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = False
        torch.manual_seed(SEED)
        self.torch = torch
        self.tokenizer = T5Tokenizer.from_pretrained(checkpoint, local_files_only=True, legacy=True,
                                                     do_lower_case=False)
        self.reference = sentencepiece.SentencePieceProcessor(model_file=str(checkpoint / "spiece.model"))
        dtype = torch.float16 if precision == "fp16" else torch.float32
        t = perf_counter()
        self.model = T5EncoderModel.from_pretrained(
            checkpoint, local_files_only=True, use_safetensors=False, weights_only=True,
            torch_dtype=dtype, attn_implementation="eager",
        ).to(device="cuda", dtype=dtype).eval()
        torch.cuda.synchronize()
        self.load_seconds = perf_counter()-t
        if self.model.training or self.model.config.d_model != WIDTH:
            raise ValueError("Unexpected model dimension or evaluation state")
        self.config = dict(model=MODEL,revision=REVISION,checkpoint_sha256=expected,precision=precision,
                           pooling="float32 mean of final hidden states at active positions including EOS",
                           tokenization="SentencePiece legacy, uppercase spaced residues; U/B/Z to X; fixed 26 active tokens",
                           gpu=torch.cuda.get_device_name(),torch=version("torch"),cuda=torch.version.cuda,
                           transformers=version("transformers"),sentencepiece=version("sentencepiece"),
                           tokenizers=version("tokenizers"),numpy=version("numpy"),python=os.sys.version.split()[0],
                           deterministic=True,attention="eager",tf32=False,fp16_reduced_precision_reduction=False,
                           cublas_workspace=os.environ["CUBLAS_WORKSPACE_CONFIG"],seed=SEED)
        # Verify all accepted residue symbols and EOS using the independently loaded vocabulary.
        self.tokens([aa * 25 for aa in CANONICAL + "XUBZ"], crosscheck=True)

    def tokens(self, sequences, crosscheck=False):
        texts = [" ".join(input_sequence(seq)) for seq in sequences]
        tokens = self.tokenizer(texts, add_special_tokens=True, padding=False, truncation=False, return_tensors="pt")
        ids, masks = tokens["input_ids"], tokens["attention_mask"]
        if (ids.shape != (len(texts), 26) or not masks.all() or not (ids[:, -1] == self.tokenizer.eos_token_id).all()
                or (ids[:, :-1] == self.tokenizer.unk_token_id).any()):
            raise ValueError("Unexpected residue tokens, mask or EOS")
        if crosscheck:
            reference = [self.reference.encode(t,out_type=int)+[self.tokenizer.eos_token_id] for t in texts]
            if ids.tolist()!=reference:
                raise ValueError("Tokenizer differs from SentencePiece")
        return ids, masks

    def embed(self, sequences):
        t = perf_counter()
        ids, mask = self.tokens(sequences)
        token_seconds = perf_counter()-t
        t = perf_counter()
        with self.torch.inference_mode():
            x = self.model(input_ids=ids.cuda(),attention_mask=mask.cuda()).last_hidden_state
            # All masks are active. The mean accumulates in float32 even for FP16 forward passes.
            values = x.mean(dim=1,dtype=self.torch.float32).cpu().numpy()
        self.torch.cuda.synchronize()
        if values.shape!=(len(sequences),WIDTH) or values.dtype!=np.float32 or not np.isfinite(values).all():
            raise ValueError("Invalid embedding batch")
        return values, token_seconds, perf_counter()-t


def identity_bytes(sequences, values):
    checksum = hashlib.sha256()
    checksum.update("".join(sequences).encode("ascii"))
    checksum.update(np.ascontiguousarray(values,dtype="<f4").tobytes())
    return checksum.hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, payload):
    partial = path.with_suffix(".partial")
    with partial.open("w") as f:
        json.dump(payload,f,indent=2,sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    partial.replace(path)
    sync_directory(path.parent)


class Store:
    def __init__(self, root, sequences, ordinals, config):
        self.root, self.sequences, self.ordinals = root, sequences, ordinals
        self.count = len(ordinals)
        self.config = config
        root.mkdir(parents=True,exist_ok=True)
        self.lock = (root/".lock").open("a")
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest = root/"manifest.json"
        if manifest.exists():
            if json.loads(manifest.read_text())!=config:
                raise ValueError("Store configuration or inventory changed")
        else:
            if set(p.name for p in root.iterdir()) - {".lock","manifest.partial"}:
                raise ValueError("Use an empty store")
            atomic_json(manifest,config)
        self.db=sqlite3.connect(root/"progress.sqlite")
        self.db.execute("PRAGMA synchronous=FULL")
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS batches (
                shard INTEGER, start INTEGER, rows INTEGER, digest TEXT,
                token_s REAL, forward_s REAL, write_s REAL,
                PRIMARY KEY(shard,start))""")

    def close(self):
        self.db.close()
        self.lock.close()

    def primary(self,start,rows):
        source=self.ordinals[start:start+rows]
        if isinstance(source,range):
            return self.sequences.slice(source.start,rows).to_pylist()
        return self.sequences.take(source).to_pylist()

    def blocks(self):
        for shard, head in enumerate(range(0,self.count,SHARD_ROWS)):
            yield shard,head,min(SHARD_ROWS,self.count-head)

    def matrix(self,shard,count,create=False):
        path=self.root/f"shard-{shard:04d}.npy"
        if not path.exists():
            if not create:
                raise ValueError(f"Missing shard {path}")
            tmp=path.with_suffix(".partial")
            arr=np.lib.format.open_memmap(tmp,"w+",dtype="<f4",shape=(count,WIDTH))
            arr.flush()
            del arr
            with tmp.open("rb") as f:
                os.fsync(f.fileno())
            tmp.replace(path)
            sync_directory(path.parent)
        arr=np.load(path,mmap_mode="r+" if create else "r",allow_pickle=False)
        if arr.shape!=(count,WIDTH) or arr.dtype!=np.dtype("<f4"):
            raise ValueError(f"Invalid shard header {path}")
        return path,arr

    def verify(self):
        verified=0
        bounds={shard:(head,count) for shard,head,count in self.blocks()}
        active=None
        for shard,start,rows,checksum in self.db.execute("SELECT shard,start,rows,digest FROM batches ORDER BY shard,start"):
            head,count=bounds[shard]
            batch=self.config["batch_size"]
            if start<0 or start>=count or start%batch or rows!=min(batch,count-start):
                raise ValueError(f"Invalid checkpoint {shard}/{start}")
            if shard!=active:
                _,matrix=self.matrix(shard,count)
                active=shard
            values=matrix[start:start+rows]
            if not np.isfinite(values).all() or identity_bytes(self.primary(head+start,rows),values)!=checksum:
                raise ValueError(f"Committed batch corrupt: {shard}/{start}")
            verified+=rows
        return verified

    def generate(self, encoder, limit):
        saved=self.verify()
        if saved==self.count:
            return 0
        generated=0
        for shard,head,count in self.blocks():
            done={r[0] for r in self.db.execute("SELECT start FROM batches WHERE shard=?",(shard,))}
            batch=self.config["batch_size"]
            todo=[i for i in range(0,count,batch) if i not in done]
            if not todo:
                continue
            path,matrix=self.matrix(shard,count,create=True)
            with path.open("rb") as f:
                for start in todo:
                    rows=min(batch,count-start)
                    keys=self.primary(head+start,rows)
                    values,token_s,forward_s=encoder.embed(keys)
                    t=perf_counter()
                    matrix[start:start+rows]=values
                    matrix.flush()
                    os.fsync(f.fileno())
                    checksum=identity_bytes(keys,values)
                    with self.db:
                        self.db.execute("INSERT INTO batches VALUES (?,?,?,?,?,?,?)",
                                        (shard,start,rows,checksum,token_s,forward_s,perf_counter()-t))
                    generated+=rows
                    if limit:
                        limit-=1
                        if limit==0:
                            return generated
        return generated

    def progress(self):
        rows,batches,token,forward,write=self.db.execute(
            "SELECT coalesce(sum(rows),0),count(*),coalesce(sum(token_s),0),coalesce(sum(forward_s),0),coalesce(sum(write_s),0) FROM batches"
        ).fetchone()
        return dict(rows=rows,batches=batches,expected=self.count,token_seconds=token,
                    forward_seconds=forward,write_seconds=write)


def config_for(args, encoder, ordinals):
    return dict(**encoder.config,batch_size=args.batch_size,shard_rows=SHARD_ROWS,dimension=WIDTH,
                storage="immutable committed rows in little-endian float32 NPY shards; SQLite batch receipts",
                stable_id="exact original sequence",inventory=str(args.inventory.resolve()),
                inventory_sha256=sha_file(args.inventory),selection_sha256=sha_file(args.selection),
                code_sha256=sha_file(Path(__file__)),sample_ordinals=None if isinstance(ordinals,range) else ordinals.tolist())


def pilot_ordinals(length):
    return np.sort(np.random.default_rng(SEED).choice(length,size=10_000,replace=False))


def benchmark(args,sequences,encoder):
    ordinals=pilot_ordinals(len(sequences))
    inputs=sequences.take(ordinals[:1024]).to_pylist()
    encoder.embed(inputs[:32])
    timings=[]
    for size in (32,128,256):
        encoder.torch.cuda.reset_peak_memory_stats()
        token=forward=0.
        for i in range(0,len(inputs),size):
            _,t,f=encoder.embed(inputs[i:i+size])
            token+=t
            forward+=f
        timings.append(dict(batch_size=size,inputs=len(inputs),token_seconds=token,forward_seconds=forward,
                            sequences_per_second=len(inputs)/(token+forward),
                            peak_vram_bytes=encoder.torch.cuda.max_memory_allocated()))
    fp16,_,_=encoder.embed(inputs[:128])
    encoder.model.float()
    fp32,_,_=encoder.embed(inputs[:128])
    delta=fp32-fp16
    return dict(load_seconds=encoder.load_seconds,arms=timings,rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                precision_control=dict(rows=128,max_abs=float(abs(delta).max()),
                  max_relative_l2=float(np.max(np.linalg.norm(delta,axis=1)/np.linalg.norm(fp32,axis=1)))),
                runtime=encoder.config)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["inventory","benchmark","pilot","full","verify","progress","repeat","locate"])
    parser.add_argument("--inventory",type=Path,default=INVENTORY)
    parser.add_argument("--selection",type=Path,default=SELECTION)
    parser.add_argument("--checkpoint",type=Path,default=CHECKPOINT)
    parser.add_argument("--hashes",type=Path,default=HASHES)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--sequence",action="append",default=[])
    parser.add_argument("--batch-size",type=int,default=128)
    parser.add_argument("--max-batches",type=int,default=0)
    args=parser.parse_args()
    if args.batch_size<=0 or args.max_batches<0:
        parser.error("Positive batch size and nonnegative batch limit required")
    if args.command=="progress":
        if not args.output:
            parser.error("--output is required")
        cfg=json.loads((args.output/"manifest.json").read_text())
        db=sqlite3.connect((args.output/"progress.sqlite").resolve().as_uri()+"?mode=ro",uri=True)
        try:
            rows,batches=db.execute("SELECT coalesce(sum(rows),0),count(*) FROM batches").fetchone()
            expected=EXPECTED_SEQUENCES if cfg["sample_ordinals"] is None else len(cfg["sample_ordinals"])
            print(json.dumps(dict(rows=rows,batches=batches,expected=expected),indent=2))
        finally:
            db.close()
        return
    t=perf_counter()
    sequences=load_inventory(args.inventory,args.selection)
    read_seconds=perf_counter()-t
    if args.command=="inventory":
        result=audit_inventory(sequences)
    elif args.command=="locate":
        if not args.sequence:
            parser.error("Pass at least one --sequence")
        for sequence in args.sequence:
            input_sequence(sequence)
        indexes=pc.index_in(pa.array(args.sequence),value_set=sequences).to_pylist()
        mapped=[]
        for sequence,index in zip(args.sequence,indexes,strict=True):
            shard,row=(None,None) if index is None else divmod(index,SHARD_ROWS)
            mapped.append(dict(sequence_id=sequence,sequence=sequence,length=25,ordinal=index,
                               sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                               full_shard=shard,full_row=row))
        result={"keys":mapped}
    elif args.command=="benchmark":
        result=benchmark(args,sequences,Encoder(args.checkpoint,args.hashes,"fp16"))
    else:
        if not args.output:
            parser.error("--output is required")
        saved=args.output/"manifest.json"
        if args.command in {"verify","repeat"} or saved.exists():
            cfg=json.loads(saved.read_text())
            if cfg["inventory_sha256"]!=sha_file(args.inventory) or cfg["selection_sha256"]!=sha_file(args.selection):
                raise ValueError("Recorded inputs differ")
            record=cfg["sample_ordinals"]
            ordinals=np.asarray(record,dtype=np.int64) if record is not None else range(len(sequences))
        else:
            cfg=None
            ordinals=pilot_ordinals(len(sequences)) if args.command=="pilot" else range(len(sequences))
        if args.command in {"pilot","full"}:
            if (args.command=="pilot")!= (not isinstance(ordinals,range)):
                raise ValueError("Store mode differs")
            if cfg and cfg["batch_size"] != args.batch_size:
                raise ValueError("Batch size differs from stored configuration")
            if cfg:
                store=Store(args.output,sequences,ordinals,cfg)
                try:
                    progress=store.progress()
                    verified=store.verify() if progress["rows"]==len(ordinals) else 0
                finally:
                    store.close()
                if verified==len(ordinals):
                    print(json.dumps({"verified":verified,"new_inferences":0,"inventory_read_seconds":read_seconds}))
                    return
            encoder=Encoder(args.checkpoint,args.hashes,"fp16")
            actual=config_for(args,encoder,ordinals)
            store=Store(args.output,sequences,ordinals,actual)
            try:
                start=perf_counter()
                new=store.generate(encoder,args.max_batches)
                result=dict(store.progress(),verified=store.verify(),new_inferences=new,
                            generation_wall_seconds=perf_counter()-start,model_load_seconds=encoder.load_seconds,
                            peak_vram_bytes=encoder.torch.cuda.max_memory_allocated(),
                            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            finally:
                store.close()
        else:
            store=Store(args.output,sequences,ordinals,cfg)
            try:
                result=store.progress()
                if args.command in {"verify","repeat"}:
                    result["verified"]=store.verify()
                if args.command=="repeat":
                    encoder=Encoder(args.checkpoint,args.hashes,"fp16")
                    args.batch_size=cfg["batch_size"]
                    if config_for(args,encoder,ordinals)!=cfg:
                        raise ValueError("Repeat uses a different environment or configuration")
                    shard,start,rows=store.db.execute("SELECT shard,start,rows FROM batches ORDER BY shard,start LIMIT 1").fetchone()
                    head=shard*SHARD_ROWS
                    _,x=store.matrix(shard,min(SHARD_ROWS,store.count-head))
                    y,_,_=encoder.embed(store.primary(head+start,rows))
                    result.update(repeated_rows=rows,bitwise_equal=bool(np.array_equal(y,x[start:start+rows])),
                                  max_abs=float(abs(y-x[start:start+rows]).max()))
                    if not result["bitwise_equal"]:
                        raise ValueError(f"Repetition differs: {result}")
            finally:
                store.close()
    result["inventory_read_seconds"]=read_seconds
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
