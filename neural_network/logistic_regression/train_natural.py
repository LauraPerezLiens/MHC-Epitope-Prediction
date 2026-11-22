#!/usr/bin/env python3
"""Streaming logistic regression on prepared ProtT5 + SecondaryBERT features."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch import nn

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'neural_network/MLP'))
from dataset import (TRAIN, VALIDATION, TEST, ModalityStandardizer,
                     discover_datasets, list_chunk_ids, load_chunk_metadata, load_rows)
from check_preparation import validate_preparation


class Metrics:
    """Exact threshold metrics; bounded-memory ROC/PR AUC via score histograms."""
    def __init__(self, bins=10000):
        self.loss = 0.0
        self.confusion = np.zeros(4, dtype=np.int64)  # TN, FP, FN, TP
        self.hist = np.zeros((2, bins), dtype=np.int64)

    def update(self, logits, labels, loss_sum):
        scores = torch.sigmoid(logits.detach()).cpu().numpy()
        y = labels.detach().cpu().numpy().astype(np.int64)
        if not np.isfinite(scores).all() or not math.isfinite(loss_sum):
            raise ValueError('Nonfinite predictions/loss')
        self.loss += loss_sum
        self.confusion += np.bincount(2 * y + (scores >= .5), minlength=4)
        bins = np.minimum((scores * self.hist.shape[1]).astype(np.int64), self.hist.shape[1] - 1)
        self.hist += np.bincount(y * self.hist.shape[1] + bins,
                                minlength=self.hist.size).reshape(self.hist.shape)

    def result(self):
        tn, fp, fn, tp = map(int, self.confusion)
        n = tn + fp + fn + tp
        if not n:
            raise ValueError('Requested split contains no rows')
        def ratio(a, b):
            return a / b if b else None
        pos, neg = tp + fn, tn + fp
        tps = np.r_[0, np.cumsum(self.hist[1, ::-1])]
        fps = np.r_[0, np.cumsum(self.hist[0, ::-1])]
        roc = float(np.sum(np.diff(fps / neg) * (tps[1:] + tps[:-1]) / (2 * pos))) if pos and neg else None
        precision = np.divide(tps[1:], tps[1:] + fps[1:],
                              out=np.ones(len(tps)-1), where=(tps[1:]+fps[1:]) != 0)
        ap = float(np.sum(np.diff(tps) / pos * precision)) if pos else None
        return dict(rows=n, loss=self.loss/n, accuracy=(tn+tp)/n,
                    balanced_accuracy=((tp/pos + tn/neg)/2 if pos and neg else None),
                    precision=ratio(tp, tp+fp), recall=ratio(tp, pos), specificity=ratio(tn, neg),
                    f1=ratio(2*tp, 2*tp+fp+fn),
                    mcc=ratio(tp*tn-fp*fn, math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn))),
                    tn=tn, fp=fp, fn=fn, tp=tp,
                    roc_auc_histogram=roc, average_precision_histogram=ap,
                    auc_bins=self.hist.shape[1])


def chunk_batches(ds, cid, split, scaler, batch_size, rng=None):
    meta = load_chunk_metadata(ds, cid)
    rows = np.flatnonzero(meta['split_id'] == split)
    stores = {}
    # Read in physical order for disk locality, shuffle only the in-memory batch.
    for start in range(0, len(rows), batch_size):
        selected = rows[start:start+batch_size]
        x = load_rows(ds, cid, selected, meta['group_id'][selected],
                      'primary_secondary', secondary_stores=stores)
        x = scaler.transform(x)
        y = np.asarray(meta['y'][selected], dtype=np.float32)
        if not np.isfinite(x).all():
            raise ValueError(f'Nonfinite features: {ds["name"]}, chunk {cid}')
        if rng is not None:
            order = rng.permutation(len(y))
            x, y = x[order], y[order]
        yield torch.from_numpy(x), torch.from_numpy(y)


def atomic_save(value, path):
    temporary = path.with_suffix(path.suffix + '.partial')
    torch.save(value, temporary)
    os.replace(temporary, path)



def report_progress(phase, processed, total, metrics, started, epoch=None):
    """Report cumulative metrics for rows seen in this phase, never resample."""
    values = metrics.result() if metrics.confusion.sum() else {'rows': 0}
    record = dict(phase=phase, chunks=processed, total_chunks=total,
                  elapsed_seconds=round(time.monotonic()-started, 2),
                  metrics_scope='cumulative', metrics=values)
    if epoch is not None:
        record['epoch'] = epoch
    print(f'{phase} chunks={processed}/{total} ' + json.dumps(record), flush=True)


def evaluate(model, datasets, jobs, split, scaler, args, device):
    model.eval()
    metrics = Metrics()
    started = time.monotonic()
    with torch.inference_mode():
        for index, (di, cid) in enumerate(jobs):
            for x, y in chunk_batches(datasets[di], cid, split, scaler, args.batch_size):
                x, y = x.to(device), y.to(device)
                logits = model(x).squeeze(-1)
                loss = nn.functional.binary_cross_entropy_with_logits(logits, y, reduction='sum')
                metrics.update(logits, y, loss.item())
            if (index+1) % args.log_every == 0 or index+1 == len(jobs):
                phase = 'VALIDATION' if split == VALIDATION else 'TEST'
                report_progress(phase, index+1, len(jobs), metrics, started)
    return metrics.result()


def run(args):
    if args.epochs < 1 or args.batch_size < 1 or args.log_every < 1 or args.checkpoint_every < 1:
        raise ValueError('Epochs, batch size and intervals must be positive')
    if not math.isfinite(args.lr) or args.lr <= 0 or not math.isfinite(args.l2) or args.l2 < 0:
        raise ValueError('lr must be positive and l2 nonnegative, both finite')
    if not args.scaler.is_file():
        raise FileNotFoundError(f'Existing TRAIN scaler required: {args.scaler}')
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / '.writer.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items() if k != 'resume'}
    config['root'], config['scaler'] = str(args.root.resolve()), str(args.scaler.resolve())
    config['scaler_sha256'] = hashlib.sha256(args.scaler.read_bytes()).hexdigest()
    config_path = args.output / 'config.json'
    if config_path.exists():
        if not args.resume:
            raise ValueError('Output already exists; use --resume or a new --output')
        previous = json.loads(config_path.read_text())
        adjustable = {'epochs', 'log_every', 'checkpoint_every'}
        if ({k: v for k, v in previous.items() if k not in adjustable} !=
                {k: v for k, v in config.items() if k not in adjustable}):
            raise ValueError('Resume configuration changed; use the original arguments')
        if args.epochs < previous['epochs']:
            raise ValueError('Resume may extend epochs, not reduce them')
    elif args.resume:
        raise ValueError('No existing run to resume')
    print('PREPARATION: validating existing data and TRAIN scaler...', flush=True)
    validate_preparation(args.root, args.scaler)
    print('PREPARATION: validation complete.', flush=True)
    datasets = discover_datasets(args.root)
    jobs = [(di, cid) for di, ds in enumerate(datasets) for cid in sorted(list_chunk_ids(ds))]
    config_path.write_text(json.dumps(config, indent=2)+'\n')
    scaler = ModalityStandardizer.load(args.scaler)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else torch.device(args.device)
    if args.gpus < 0:
        raise ValueError('--gpus must be nonnegative (0 selects all visible GPUs)')
    gpu_ids = []
    if device.type == 'cuda':
        first = device.index if device.index is not None else 0
        available = list(range(first, torch.cuda.device_count()))
        if not available or (args.gpus and args.gpus > len(available)):
            raise ValueError('Requested GPUs are not available; check CUDA_VISIBLE_DEVICES')
        gpu_ids = available[:args.gpus] if args.gpus else available
        device = torch.device('cuda', first)
    elif args.gpus > 1:
        raise ValueError('Multiple GPUs require a CUDA device')
    torch.manual_seed(args.seed)
    model = nn.Linear(1792, 1).to(device)
    # Keep the base module for portable checkpoints and the L2 penalty.
    predictor = nn.DataParallel(model, device_ids=gpu_ids) if len(gpu_ids) > 1 else model
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    last = args.output / 'last.pt'
    start_epoch, cursor, best = 0, 0, float('inf')
    running = Metrics()
    if args.resume:
        state = torch.load(last, map_location='cpu', weights_only=False)
        model.load_state_dict(state['model'])
        optimizer.load_state_dict(state['optimizer'])
        start_epoch, cursor, best = state['epoch'], state['cursor'], state['best']
        running = state['metrics']
    print(f'DEVICE={device}; GPU_IDS={gpu_ids}; chunks={len(jobs)}; all TRAIN rows once/epoch; no class resampling', flush=True)
    def checkpoint(epoch, cursor, metrics):
        atomic_save(dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                         epoch=epoch, cursor=cursor, best=best, metrics=metrics), last)
    for epoch in range(start_epoch, args.epochs):
        started = time.monotonic()
        order = np.random.default_rng(np.random.SeedSequence([args.seed, epoch])).permutation(len(jobs))
        predictor.train()
        for position in range(cursor, len(order)):
            di, cid = jobs[order[position]]
            rng = np.random.default_rng(np.random.SeedSequence([args.seed, epoch, di, cid]))
            for x, y in chunk_batches(datasets[di], cid, TRAIN, scaler, args.batch_size, rng):
                x, y = x.to(device), y.to(device)
                optimizer.zero_grad(set_to_none=True)
                logits = predictor(x).squeeze(-1)
                bce = nn.functional.binary_cross_entropy_with_logits(logits, y)
                loss = bce + .5 * args.l2 * model.weight.square().sum()
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite training objective')
                loss.backward()
                optimizer.step()
                running.update(logits, y, bce.detach().item()*len(y))
            if (position+1) % args.checkpoint_every == 0:
                checkpoint(epoch, position+1, running)
            if (position+1) % args.log_every == 0 or position+1 == len(jobs):
                report_progress('TRAIN', position+1, len(jobs), running, started, epoch+1)
        train = running.result()
        validation = evaluate(predictor, datasets, jobs, VALIDATION, scaler, args, device)
        if validation['loss'] < best:
            best = validation['loss']
            atomic_save(dict(model=model.state_dict(), epoch=epoch+1, validation=validation), args.output/'best.pt')
        record = dict(epoch=epoch+1, train_online=train, validation=validation,
                      elapsed_seconds=time.monotonic()-started)
        # One authoritative file per epoch; resuming cannot duplicate history lines.
        (args.output/f'epoch_{epoch+1:04d}.json').write_text(json.dumps(record, indent=2)+'\n')
        print(json.dumps(record), flush=True)
        cursor, running = 0, Metrics()
        checkpoint(epoch+1, 0, running)
    state = torch.load(args.output/'best.pt', map_location='cpu', weights_only=False)
    model.load_state_dict(state['model'])
    test = evaluate(predictor, datasets, jobs, TEST, scaler, args, device)
    result = dict(best_epoch=state['epoch'], validation=state['validation'], test=test,
                  device=str(device), gpu_ids=gpu_ids, chunks=len(jobs), features=1792,
                  threshold=.5, selection='minimum full VALIDATION BCE',
                  note='Existing row splits and augmented rows retained; AUC uses 10000-bin histograms.')
    (args.output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    np.savez(args.output/'coefficients.npz', weight=model.weight.detach().cpu().numpy(),
             bias=model.bias.detach().cpu().numpy(), primary_mean=scaler.primary_mean,
             primary_scale=scaler.primary_scale, secondary_mean=scaler.secondary_mean,
             secondary_scale=scaler.secondary_scale)
    print(json.dumps(result, indent=2), flush=True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=PROJECT/'data/data_input_nn_shuffled_concatenate')
    p.add_argument('--scaler', type=Path, default=PROJECT/'neural_network/MLP/standardizer_all_train_chunks.npz')
    p.add_argument('--output', type=Path, default=PROJECT/'results/logistic_regression_all')
    p.add_argument('--epochs', type=int, default=10)
    p.add_argument('--batch-size', type=int, default=8192)
    p.add_argument('--lr', type=float, default=.001)
    p.add_argument('--l2', type=float, default=.0001)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--device', default='auto', help='auto, cpu, cuda, cuda:0, ...')
    p.add_argument('--gpus', type=int, default=0, help='Number of visible GPUs; 0 uses all, 1 disables multi-GPU')
    p.add_argument('--log-every', type=int, default=10)
    p.add_argument('--checkpoint-every', type=int, default=10)
    p.add_argument('--resume', action='store_true')
    return p


if __name__ == '__main__':
    run(parser().parse_args())
