#!/usr/bin/env python3
"""Measure existing ProtT5 embeddings for BLOSUM62 single substitutions.

Sample complete 26-row groups in one random original chunk per family. Variant
identity/order is reconstructed with the retained augmentation implementation,
not recovered independently from the archived augmented sequence CSV. Validate
26-row contiguity, global row ordering, original group/protein/label metadata.
Reference: all distinct-sequence original/original pairs within each sampled
family. This is descriptive, not a biological mutation-effect validation.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def load_array(path):
    if path.exists():
        return np.load(path, allow_pickle=False)
    raw = subprocess.check_output(['zstd', '-qdc', str(path) + '.zst'])
    record = json.loads(Path(str(path) + '.archive.json').read_text())
    if hashlib.sha256(raw).hexdigest() != record['original_sha256']:
        raise ValueError(f'Checksum mismatch: {path}')
    return np.load(io.BytesIO(raw), allow_pickle=False)


def metrics(a, b, mean, scale):
    a, b = a.astype(np.float64), b.astype(np.float64)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Invalid embedding')
    delta = b-a
    standardized_delta = delta/scale
    return {'cosine_similarity': float(np.clip(np.dot(a,b)/norm,-1,1)),
            'relative_l2': float(np.linalg.norm(delta)/np.linalg.norm(a)),
            'l2': float(np.linalg.norm(delta)),
            'scaled_l2': float(np.linalg.norm(standardized_delta)),
            'scaled_rms': float(np.sqrt(np.mean(standardized_delta**2))),
            'scaled_relative_l2': float(np.linalg.norm(standardized_delta)/max(np.linalg.norm((a-mean)/scale),1e-15)),
            'max_abs_difference': float(np.max(np.abs(delta))),
            'exact_equal': bool(np.array_equal(a,b))}


def describe(frame):
    columns=['cosine_similarity','relative_l2','l2','scaled_l2','scaled_rms','scaled_relative_l2']
    return {c:{'min':float(frame[c].min()),'p05':float(frame[c].quantile(.05)),
               'median':float(frame[c].median()),'p95':float(frame[c].quantile(.95)),
               'max':float(frame[c].max())} for c in columns}


def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    lock=(args.output/'.run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    spec=importlib.util.spec_from_file_location('augmentation',ROOT/'data_pipeline/scripts/data_augmentation/generate_blosum62_variants.py')
    augmentation=importlib.util.module_from_spec(spec);spec.loader.exec_module(augmentation)
    manifest=json.loads((args.root/'reorder_manifest.json').read_text())
    with np.load(args.scaler, allow_pickle=False) as scaler:
        mean = scaler['primary_mean'].astype(np.float64)
        scale = scaler['primary_scale'].astype(np.float64)
    if mean.shape!=(1024,) or scale.shape!=(1024,) or not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale<=0).any():
        raise ValueError('Invalid Primary scaler')
    rng=np.random.default_rng(args.seed);mutations=[];controls=[];sampled=[]
    for source in manifest['sources']:
        store=Path(source['master_index']).parent
        family=Path(*store.parts[-4:-1]);candidates=sorted(store.glob('chunk_*_X.npy.archive.json'))
        if not candidates:raise ValueError(f'No original chunks: {store}')
        marker=candidates[int(rng.integers(len(candidates)))];stem=marker.name.replace('_X.npy.archive.json','');cid=int(stem.split('_')[1])
        gids=load_array(store/f'{stem}_group_id.npy');protein=load_array(store/f'{stem}_protein_group_id.npy');labels=load_array(store/f'{stem}_y.npy')
        unique,first,n=np.unique(gids,return_index=True,return_counts=True)
        valid=(n==26)&(first+26<=len(gids))
        eligible=first[valid]
        if len(eligible)<args.groups_per_source:raise ValueError('Insufficient complete groups')
        starts=sorted(rng.choice(eligible,size=args.groups_per_source,replace=False))
        x=load_array(store/f'{stem}_X.npy')
        if x.shape!=(len(gids),1024):raise ValueError('Invalid Primary shape')
        targets={int(gids[start]):int(start) for start in starts}
        original_path=args.sources/family/f'classification_{"_".join(family.parts)}.csv'
        originals={}
        for frame in pd.read_csv(original_path,chunksize=200000,keep_default_na=False):
            hits=frame[frame.group_id.isin(targets)]
            originals.update({int(row['group_id']):row for row in hits.to_dict('records')})
            if len(originals)==len(targets):break
        if len(originals)!=len(targets):raise ValueError('Missing original sequences')
        family_samples=[]
        for gid,start in targets.items():
            row=originals[gid];sequence=row['25aa_seq']
            if len(sequence)!=25 or start!=(gid-1)*26-cid*100000:
                raise ValueError('Unexpected sequence length or augmentation ordering')
            if not (gids[start:start+26]==gid).all() or not (protein[start:start+26]==row['protein_group_id']).all() or not (labels[start:start+26]==row['contains_epitope']).all():
                raise ValueError('Group/protein/label mismatch')
            info={'source_family':str(family),'source_dataset_id':source['id'],
                  'source_group_id':gid,'global_group_id':gid+source['group_id_offset'],
                  'protein_group_id':row['protein_group_id'],'protein_url':row['protein_url'],
                  'contains_epitope':row['contains_epitope'],'original_sequence':sequence,
                  'original_chunk':stem,'original_row':start}
            sampled.append(info);family_samples.append((info,x[start].copy()))
            variants=augmentation.build_variants(sequence)
            for position,variant in enumerate(variants[1:],1):
                if sum(a!=b for a,b in zip(sequence,variant))!=1:raise ValueError('Not a single substitution')
                mutations.append(dict(info,position=position,from_amino_acid=sequence[position-1],
                                      to_amino_acid=variant[position-1],variant_sequence=variant,
                                      variant_row=start+position,**metrics(x[start],x[start+position],mean,scale)))
        for (a,xa),(b,xb) in itertools.combinations(family_samples,2):
            if a['original_sequence']==b['original_sequence']:continue
            controls.append({'source_family':str(family),'group_a':a['global_group_id'],
                             'group_b':b['global_group_id'],'protein_url_a':a['protein_url'],
                             'protein_url_b':b['protein_url'],'same_protein':a['protein_url']==b['protein_url'],
                             'sequence_a':a['original_sequence'],'sequence_b':b['original_sequence'],
                             'sequence_hamming_distance':sum(a!=b for a,b in zip(a['original_sequence'],b['original_sequence'])),
                             **metrics(xa,xb,mean,scale)})
        print(f'SOURCE {family} chunk={stem} groups={len(targets)} mutation_pairs={len(targets)*25}',flush=True)
        del x
    mutants=pd.DataFrame(mutations);reference=pd.DataFrame(controls)
    if reference.empty:raise ValueError('No distinct-sequence controls')
    for name,frame in [('mutation_pairs',mutants),('reference_pairs',reference)]:
        temp=args.output/f'{name}.csv.partial';frame.to_csv(temp,index=False);os.replace(temp,args.output/f'{name}.csv')
    summary={'status':'completed','seed':args.seed,'groups_per_source':args.groups_per_source,
             'sources':len(manifest['sources']),'sampled_groups':len(sampled),
             'mutation_pairs':len(mutants),'reference_pairs':len(reference),
             'exact_equal_mutation_pairs':int(mutants.exact_equal.sum()),
             'mutation_statistics':describe(mutants),'reference_statistics':describe(reference),
             'by_source':{family:{'mutation_pairs':len(frame),'statistics':describe(frame)}
                          for family,frame in mutants.groupby('source_family')},
             'variant_identity':'Reconstructed from retained BLOSUM62 generator and validated 26-row metadata/order; augmented sequence CSV not read independently.',
             'reference_scope':'All distinct-sequence original pairs among sampled groups within the same family and original chunk; can include the same protein or one-residue differences.',
             'limits':'Conservative BLOSUM62 substitutions only. One random chunk per family. Descriptive dependent pairs, not arbitrary mutations or biological effects.',
             'scaler_sha256':hashlib.sha256(args.scaler.read_bytes()).hexdigest()}
    temp=args.output/'summary.json.partial';temp.write_text(json.dumps(summary,indent=2)+'\n');os.replace(temp,args.output/'summary.json')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,column,title in [(axes[0],'cosine_similarity','Primary cosine similarity'),(axes[1],'scaled_l2','Primary distance after MLP scaler')]:
        ax.boxplot([mutants[column],reference[column]],tick_labels=['One substitution','Different groups'],showfliers=False)
        ax.set_title(title);ax.grid(axis='y',alpha=.25)
    fig.suptitle(f'{len(sampled)} groups / {len(manifest["sources"])} families; conservative BLOSUM62 changes')
    fig.tight_layout();fig.savefig(args.output/'comparison.png',dpi=160);plt.close(fig)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['by_source']},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'data/data_input_nn_shuffled_concatenate')
    parser.add_argument('--sources',type=Path,default=ROOT/'data/used_data/contradiction_sources')
    parser.add_argument('--scaler',type=Path,default=ROOT/'neural_network/MLP/standardizer_all_train_chunks.npz')
    parser.add_argument('--output',type=Path,default=ROOT/'results/primary_mutation_test')
    parser.add_argument('--groups-per-source',type=int,default=10)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    if args.groups_per_source<2:parser.error('--groups-per-source must be at least 2')
    run(args)
