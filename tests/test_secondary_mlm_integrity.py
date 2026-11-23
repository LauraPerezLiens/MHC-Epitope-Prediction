from argparse import Namespace
import json
import math
import importlib.util
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from data_pipeline.scripts.secondaryBERT import build_secondary_mlm_dataset as builder


class SecondaryMlmIntegrityTests(unittest.TestCase):
    def test_empty_mask_has_undefined_training_loss_and_is_rejected(self):
        logits = torch.zeros((1, 8))
        labels = torch.tensor([-100])
        self.assertTrue(torch.nn.functional.cross_entropy(logits, labels).isnan())
        from data_pipeline.scripts.secondaryBERT import train_secondary_mlm as trainer
        with self.assertRaisesRegex(RuntimeError, "no masked tokens"):
            trainer.require_masked_training_tokens(labels)
        trainer.require_masked_training_tokens(torch.tensor([-100, 5]))

    def test_validator_does_not_publish_metrics_for_zero_masked_tokens(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            args = Namespace(dataset_dir=path.parent, model_dir=path.parent, output_json=path,
                             batch_size=1, parquet_batch_rows=1, mlm_probability=0.0,
                             seed=42, max_val_proteins=None, logging_steps=10)
            transformers = ModuleType("transformers")
            model = type("FakeModel", (), {
                "to": lambda self, _: self, "eval": lambda self: self,
                "__call__": lambda self, **_: SimpleNamespace(logits=torch.zeros(1, 27, 8)),
            })()
            transformers.BertForMaskedLM = SimpleNamespace(from_pretrained=lambda _: model)
            transformers.BertTokenizer = SimpleNamespace(
                from_pretrained=lambda _: lambda *a, **k: {"input_ids": [2, 5, 6, 7, 5, 3]})
            with patch.dict(sys.modules, {"transformers": transformers}):
                from data_pipeline.scripts.secondaryBERT import validate_secondary_mlm as validator
                units = [{"rows": 1, "windows": 1}]
                data = [torch.tensor([2] + [5] * 25 + [3])]
                with patch.object(validator, "args", return_value=args), \
                        patch.object(validator, "init_dist", return_value=(0, 1, torch.device("cpu"))), \
                        patch.object(validator, "build_units", return_value=units), \
                        patch.object(validator, "DS", return_value=data), \
                        patch.object(validator, "embedding_sanity", return_value={"all_embeddings_identical": False}):
                    with self.assertRaisesRegex(RuntimeError, "no masked tokens"):
                        validator.main()
                    self.assertFalse(path.exists())
                    args.mlm_probability = 1.0
                    validator.main()
            metrics = json.loads(path.read_text())
            self.assertEqual(metrics["masked_tokens"], 25)
            self.assertAlmostEqual(metrics["mlm_loss"], math.log(8), places=6)
            self.assertAlmostEqual(metrics["perplexity"], 8.0, places=5)

    def test_interrupted_dataset_write_does_not_publish_partial_directory(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            inputs.mkdir()
            pd.DataFrame({"protein_id": range(10), "sequence": ["AA"] * 10,
                          "secondary_structure": ["CH"] * 10}).to_csv(inputs / "chunk_0.csv", index=False)
            output = root / "dataset"
            args = Namespace(data_dir=root, input_dir=inputs, output_dir=output,
                             test_size=0.2, val_size=0.2, random_state=42)
            write = pd.DataFrame.to_parquet

            def interrupted(frame, path, **kwargs):
                if Path(path).name == "train.parquet":
                    raise InterruptedError("fixture")
                return write(frame, path, **kwargs)

            with patch.object(builder, "parse_args", return_value=args):
                with patch.object(pd.DataFrame, "to_parquet", interrupted):
                    with self.assertRaises(InterruptedError):
                        builder.main()
                self.assertFalse(output.exists())
                builder.main()
                self.assertEqual({path.name for path in output.iterdir()},
                                 {"all_cleaned.parquet", "train.parquet", "val.parquet", "test.parquet", "vocab.txt"})
                with self.assertRaises(FileExistsError):
                    builder.main()


class UniRefPredictionIntegrityTests(unittest.TestCase):
    def setUp(self):
        from data_pipeline.scripts.secondaryBERT import build_secondary_mlm_dataset
        source = Path(build_secondary_mlm_dataset.__file__).with_name("predict_uniref30_secondary_structure.py")
        spec = importlib.util.spec_from_file_location("uniref_prediction_fixture", source)
        self.predictor = importlib.util.module_from_spec(spec)
        tensorflow = ModuleType("tensorflow")
        keras = ModuleType("tensorflow.keras")
        utils = ModuleType("tensorflow.keras.utils")
        utils.to_categorical = lambda indices, num_classes: np.eye(num_classes, dtype=np.float32)[indices]
        keras.Model = object
        keras.models = SimpleNamespace(load_model=lambda _: None)
        tensorflow.keras = keras
        tensorflow.config = SimpleNamespace(threading=SimpleNamespace(
            set_intra_op_parallelism_threads=lambda _: None, set_inter_op_parallelism_threads=lambda _: None))
        with patch.dict(os.environ), patch.dict(sys.modules, {
            "tensorflow": tensorflow, "tensorflow.keras": keras, "tensorflow.keras.utils": utils,
        }):
            spec.loader.exec_module(self.predictor)

    def test_rejects_nonfinite_or_incompatible_model_output(self):
        for values in (np.full((1, 2, 3), np.nan), np.zeros((2, 2, 3)),
                       np.zeros((1, 1, 3)), np.zeros((1, 2, 4))):
            with self.subTest(shape=values.shape):
                model = SimpleNamespace(predict=lambda *a, **k: values)
                with self.assertRaisesRegex(ValueError, "Invalid prediction"):
                    self.predictor.predict_window_probabilities("AC", model)

    def test_duplicate_fasta_ids_do_not_replace_previous_outputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "chunk.fasta"
            good = root / "chunk.csv"
            skipped = root / "chunk_skipped.csv"
            good.write_text("original predictions")
            skipped.write_text("original skipped rows")
            args = Namespace(input=source, output=None, outputs_dir=root, data_dir=root, model_path=root)
            source.write_text(">id description\nAC\n>id duplicate\nCA\n")
            with patch.object(self.predictor, "parse_arguments", return_value=args), \
                    patch.object(self.predictor, "predict_secondary_structure", side_effect=lambda seq, _: "C" * len(seq)):
                with self.assertRaisesRegex(ValueError, "Duplicate protein ID"):
                    self.predictor.main()
                self.assertEqual(good.read_text(), "original predictions")
                self.assertEqual(skipped.read_text(), "original skipped rows")
                source.write_text(">id1\nAC\n>id2\nCA\n")
                self.predictor.main()
                self.assertEqual(pd.read_csv(good)[["protein_id", "sequence"]].values.tolist(),
                                 [["id1", "AC"], ["id2", "CA"]])
