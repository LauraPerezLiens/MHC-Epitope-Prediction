#!/usr/bin/env python3
"""Logistic regression using the MLP training and evaluation protocol verbatim."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'neural_network/MLP'))
import mlp_layernorm_shuffled_ladder100_dualeval as protocol
from check_preparation import validate_preparation


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=PROJECT/'data/data_input_nn_shuffled_concatenate')
    p.add_argument('--scaler', type=Path, default=PROJECT/'neural_network/MLP/standardizer_all_train_chunks.npz')
    p.add_argument('--output', type=Path, default=PROJECT/'results/logistic_regression_balanced')
    p.add_argument('--epochs', type=int, default=10)
    p.add_argument('--batch-size', type=int, default=8192)
    p.add_argument('--lr', type=float, default=.001)
    p.add_argument('--l2', type=float, default=.0001, help='AdamW weight decay, as in MLP')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--device', choices=('auto', 'cpu', 'cuda'), default='auto')
    p.add_argument('--gpus', type=int, choices=(1,), default=1)
    p.add_argument('--log-every', type=int, default=10)
    p.add_argument('--checkpoint-every', type=int, default=10)
    p.add_argument('--eval-batch-size', type=int, default=1024)
    p.add_argument('--eval-target-per-class', type=int, default=29006)
    p.add_argument('--max-chunks', type=int, default=None)
    p.add_argument('--shared-eval-dir', type=Path)
    p.add_argument('--resume', action='store_true')
    return p


def run(args):
    if args.batch_size <= 0 or args.batch_size % 2:
        raise ValueError('Batch size must be positive and even for exact 50/50 batches')
    if args.device == 'cpu':
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
    if args.device == 'cuda' and not protocol.torch.cuda.is_available():
        raise ValueError('CUDA requested but unavailable')
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output/'.writer.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = {k: str(v.resolve()) if isinstance(v, Path) else v
              for k, v in vars(args).items() if k != 'resume'}
    config.update(protocol='mlp_exact_50_50_v1', model_type='logistic',
                  scaler_sha256=hashlib.sha256(args.scaler.read_bytes()).hexdigest())
    config_path = args.output/'config.json'
    if config_path.exists():
        if not args.resume:
            raise ValueError('Output already exists; use --resume or a new --output')
        previous = json.loads(config_path.read_text())
        adjustable = {'epochs', 'log_every', 'checkpoint_every'}
        if ({k: v for k, v in config.items() if k not in adjustable} !=
                {k: v for k, v in previous.items() if k not in adjustable}):
            raise ValueError('Resume configuration changed')
        if args.epochs < previous['epochs']:
            raise ValueError('Resume may extend epochs, not reduce them')
    elif args.resume:
        raise ValueError('No balanced run to resume; natural-distribution checkpoints are incompatible')
    print('PREPARATION: validating existing data and TRAIN scaler...', flush=True)
    validate_preparation(args.root, args.scaler)
    print('PREPARATION: validation complete. Protocol = MLP; model = logistic regression.', flush=True)
    config_path.write_text(json.dumps(config, indent=2)+'\n')
    cli = ['--model-type', 'logistic', '--root', str(args.root),
           '--scaler-path', str(args.scaler), '--output-dir', str(args.output),
           '--epochs', str(args.epochs), '--batch-size', str(args.batch_size),
           '--learning-rate', str(args.lr), '--weight-decay', str(args.l2),
           '--seed', str(args.seed), '--dropout', '0', '--eval-every', 'chunk',
           '--report-every-chunks', str(args.log_every),
           '--checkpoint-every', str(args.checkpoint_every),
           '--eval-batch-size', str(args.eval_batch_size),
           '--eval-target-per-class', str(args.eval_target_per_class)]
    if args.max_chunks is not None:
        cli += ['--max-chunks', str(args.max_chunks)]
    # Keep cache writes private by default; identical seeds and jobs give the same rows.
    cli += ['--shared-eval-dir', str(args.shared_eval_dir or args.output/'eval_all')]
    if args.resume:
        recovery = args.output/'recovery_lr_primary_secondary.pt'
        last = args.output/'last_lr_primary_secondary.pt'
        cli += ['--resume', str(recovery if recovery.is_file() else last)]
    protocol.main(protocol.parse_args(cli))


if __name__ == '__main__':
    run(parser().parse_args())
