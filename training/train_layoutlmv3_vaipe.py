"""Safe LayoutLMv3 retraining entrypoint for VAIPE prescription NER.

The script trains only on gold VAIPE prescription labels. Unlabeled archive and
real-world prescriptions should be used by `functional_extraction_check.py`
after training as an out-of-distribution sanity check.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch
from datasets import Dataset
from PIL import Image
from transformers import (
    DefaultDataCollator,
    LayoutLMv3ForTokenClassification,
    LayoutLMv3ImageProcessor,
    LayoutLMv3Processor,
    LayoutLMv3TokenizerFast,
    Trainer,
    TrainingArguments,
)


LABELS = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
ID2LABEL = {index: label for index, label in enumerate(LABELS)}
LABEL2ID = {label: index for index, label in ID2LABEL.items()}
OTHER_ID = LABEL2ID["other"]
DATASET_SLUG = "tommyngx/vaipepill2022"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_dataset_root(dataset_root: str | None, download_kaggle: bool) -> Path:
    candidates: list[Path] = []
    if dataset_root:
        candidates.append(Path(dataset_root).expanduser())

    repo_root = _repo_root()
    candidates.extend(
        [
            repo_root,
            repo_root / "data" / "vaipepill2022",
            repo_root.parent / "vaipepill2022",
            Path.home() / "Downloads" / "vaipepill2022",
        ]
    )

    for candidate in candidates:
        if _has_vaipe_train(candidate):
            return candidate

    if not download_kaggle:
        checked = "\n".join(f"- {path}" for path in candidates)
        raise FileNotFoundError(
            "Could not find public_train/prescription/{image,label}. "
            "Pass --dataset-root or add --download-kaggle.\nChecked:\n" + checked
        )

    import kagglehub

    downloaded = Path(kagglehub.dataset_download(DATASET_SLUG))
    if not _has_vaipe_train(downloaded):
        raise FileNotFoundError(
            f"Kaggle download completed but VAIPE train labels were not found at {downloaded}"
        )
    return downloaded


def _has_vaipe_train(root: Path) -> bool:
    return (
        (root / "public_train" / "prescription" / "image").is_dir()
        and (root / "public_train" / "prescription" / "label").is_dir()
    )


def _split_dir(root: Path, split: str) -> Path:
    return root / split / "prescription"


def _safe_box(raw_box: Any, image_size: tuple[int, int] | None) -> list[int] | None:
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) < 4:
        return None

    try:
        coords = [float(value) for value in raw_box[:4]]
    except (TypeError, ValueError):
        return None

    x1, y1, x2, y2 = coords
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1

    # VAIPE annotations are usually already in LayoutLM's 0-1000 space. If a
    # future source stores pixel boxes, normalize them while loading.
    if image_size and any(value > 1000 for value in (x1, y1, x2, y2)):
        width, height = image_size
        width = max(width, 1)
        height = max(height, 1)
        x1, x2 = x1 * 1000 / width, x2 * 1000 / width
        y1, y2 = y1 * 1000 / height, y2 * 1000 / height

    return [max(0, min(1000, int(round(value)))) for value in (x1, y1, x2, y2)]


def _image_for_label(image_dir: Path, stem: str) -> Path | None:
    for suffix in (".png", ".jpg", ".jpeg"):
        candidate = image_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _items_from_annotation(annotation: Any) -> list[tuple[str, str, Any]]:
    if isinstance(annotation, list):
        rows = []
        for item in annotation:
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    str(item.get("text", "")).strip(),
                    str(item.get("label", "other")).strip(),
                    item.get("box", [0, 0, 0, 0]),
                )
            )
        return rows

    if isinstance(annotation, dict):
        words = annotation.get("words") or annotation.get("tokens") or []
        boxes = annotation.get("bboxes") or annotation.get("boxes") or []
        labels = annotation.get("ner_tags") or annotation.get("labels") or []
        return [
            (str(word).strip(), str(label).strip(), box)
            for word, label, box in zip(words, labels, boxes)
        ]

    return []


def load_vaipe_split(split_dir: Path) -> tuple[Dataset, dict[str, Any]]:
    image_dir = split_dir / "image"
    label_dir = split_dir / "label"
    if not label_dir.is_dir():
        return Dataset.from_list([]), {
            "split_dir": str(split_dir),
            "documents": 0,
            "tokens": 0,
            "label_counts": {},
            "skipped_annotations": ["missing_label_dir"],
        }

    records: list[dict[str, Any]] = []
    skipped: list[str] = []
    label_counts: Counter[str] = Counter()
    token_counts: list[int] = []

    for label_path in sorted(label_dir.glob("*.json")):
        image_path = _image_for_label(image_dir, label_path.stem)
        if image_path is None:
            skipped.append(f"{label_path.name}:missing_image")
            continue

        try:
            annotation = json.loads(label_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            skipped.append(f"{label_path.name}:invalid_json")
            continue

        try:
            with Image.open(image_path) as image:
                image_size = image.size
        except OSError:
            skipped.append(f"{label_path.name}:unreadable_image")
            continue

        tokens: list[str] = []
        boxes: list[list[int]] = []
        ner_tags: list[str] = []

        for text, label, raw_box in _items_from_annotation(annotation):
            if not text:
                continue
            safe_box = _safe_box(raw_box, image_size)
            if safe_box is None:
                continue
            safe_label = label if label in LABEL2ID else "other"
            tokens.append(text)
            boxes.append(safe_box)
            ner_tags.append(safe_label)
            label_counts[safe_label] += 1

        if not tokens:
            skipped.append(f"{label_path.name}:empty_after_cleaning")
            continue

        token_counts.append(len(tokens))
        records.append(
            {
                "id": label_path.stem,
                "image_path": str(image_path),
                "tokens": tokens,
                "bboxes": boxes,
                "ner_tags": ner_tags,
            }
        )

    audit = {
        "split_dir": str(split_dir),
        "documents": len(records),
        "tokens": sum(token_counts),
        "mean_tokens_per_document": (
            sum(token_counts) / len(token_counts) if token_counts else 0.0
        ),
        "label_counts": dict(label_counts),
        "skipped_annotations": skipped[:100],
        "skipped_count": len(skipped),
    }
    return Dataset.from_list(records), audit


def _make_splits(
    train_raw: Dataset,
    val_size: float,
    test_size: float,
    seed: int,
) -> tuple[Dataset, Dataset, Dataset]:
    if len(train_raw) < 10:
        raise ValueError(f"Need at least 10 labelled prescriptions, found {len(train_raw)}")

    holdout_size = val_size + test_size
    split = train_raw.train_test_split(test_size=holdout_size, seed=seed)
    holdout = split["test"]
    if test_size <= 0:
        return split["train"], holdout, Dataset.from_list([])

    relative_test_size = test_size / holdout_size
    val_test = holdout.train_test_split(test_size=relative_test_size, seed=seed)
    return split["train"], val_test["train"], val_test["test"]


def _load_processor(base_model: str) -> LayoutLMv3Processor:
    try:
        return LayoutLMv3Processor.from_pretrained(base_model, apply_ocr=False)
    except OSError:
        tokenizer = LayoutLMv3TokenizerFast.from_pretrained(base_model)
        image_processor = LayoutLMv3ImageProcessor.from_pretrained(
            "microsoft/layoutlmv3-base",
            apply_ocr=False,
        )
        return LayoutLMv3Processor(
            image_processor=image_processor,
            tokenizer=tokenizer,
        )


def _preprocess_dataset(
    dataset: Dataset,
    processor: LayoutLMv3Processor,
    max_length: int,
    batch_size: int,
) -> Dataset:
    def preprocess_batch(examples: dict[str, list[Any]]) -> dict[str, Any]:
        images = [Image.open(path).convert("RGB") for path in examples["image_path"]]
        word_labels = [
            [LABEL2ID.get(str(label), OTHER_ID) for label in labels]
            for labels in examples["ner_tags"]
        ]
        return processor(
            images=images,
            text=examples["tokens"],
            boxes=examples["bboxes"],
            word_labels=word_labels,
            truncation=True,
            padding="max_length",
            max_length=max_length,
        )

    return dataset.map(
        preprocess_batch,
        batched=True,
        batch_size=batch_size,
        remove_columns=dataset.column_names,
        desc="Encoding LayoutLMv3 inputs",
    )


def _limit_dataset(dataset: Dataset, max_samples: int | None) -> Dataset:
    if max_samples is None or max_samples <= 0 or len(dataset) <= max_samples:
        return dataset
    return dataset.select(range(max_samples))


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _compute_metrics(eval_pred: Any) -> dict[str, float]:
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    true_labels: list[int] = []
    predicted_labels: list[int] = []
    for pred_row, label_row in zip(predictions, labels):
        for pred, label in zip(pred_row, label_row):
            if int(label) == -100:
                continue
            true_labels.append(int(label))
            predicted_labels.append(int(pred))

    if not true_labels:
        return {"accuracy": 0.0, "f1_macro": 0.0, "f1_micro": 0.0}

    correct = sum(int(true == pred) for true, pred in zip(true_labels, predicted_labels))
    accuracy = correct / len(true_labels)

    label_f1s: list[float] = []
    total_tp = total_fp = total_fn = 0
    metrics: dict[str, float] = {"accuracy": accuracy}
    for label_id, label_name in ID2LABEL.items():
        tp = sum(
            int(true == label_id and pred == label_id)
            for true, pred in zip(true_labels, predicted_labels)
        )
        fp = sum(
            int(true != label_id and pred == label_id)
            for true, pred in zip(true_labels, predicted_labels)
        )
        fn = sum(
            int(true == label_id and pred != label_id)
            for true, pred in zip(true_labels, predicted_labels)
        )
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        label_f1s.append(f1)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        metrics[f"f1_{label_name}"] = f1
        metrics[f"recall_{label_name}"] = recall

    micro_precision = _safe_div(total_tp, total_tp + total_fp)
    micro_recall = _safe_div(total_tp, total_tp + total_fn)
    metrics["f1_micro"] = _safe_div(
        2 * micro_precision * micro_recall,
        micro_precision + micro_recall,
    )
    metrics["f1_macro"] = sum(label_f1s) / len(label_f1s)
    return metrics


def _training_args(args: argparse.Namespace, output_dir: Path) -> TrainingArguments:
    kwargs: dict[str, Any] = {
        "output_dir": str(output_dir),
        "overwrite_output_dir": args.overwrite_output_dir,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "per_device_eval_batch_size": args.per_device_eval_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "max_steps": args.max_steps,
        "num_train_epochs": args.num_train_epochs,
        "logging_steps": args.logging_steps,
        "save_steps": args.save_steps,
        "eval_steps": args.eval_steps,
        "save_strategy": "steps",
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_f1_macro",
        "greater_is_better": True,
        "save_total_limit": args.save_total_limit,
        "fp16": bool(args.fp16 and torch.cuda.is_available()),
        "dataloader_num_workers": args.dataloader_num_workers,
        "report_to": "none",
        "seed": args.seed,
        "data_seed": args.seed,
        "remove_unused_columns": False,
        "save_safetensors": True,
    }

    signature = inspect.signature(TrainingArguments.__init__)
    if "eval_strategy" in signature.parameters:
        kwargs["eval_strategy"] = "steps"
    else:
        kwargs["evaluation_strategy"] = "steps"

    return TrainingArguments(**kwargs)


def _default_output_dir(smoke: bool) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = "smoke" if smoke else stamp
    return _repo_root() / "models" / f"layoutlmv3_vaipe_retrain_{suffix}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", default=None)
    parser.add_argument("--download-kaggle", action="store_true")
    parser.add_argument("--base-model", default="microsoft/layoutlmv3-base")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--overwrite-output-dir", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--val-size", type=float, default=0.1)
    parser.add_argument("--test-size", type=float, default=0.1)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--preprocess-batch-size", type=int, default=2)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-eval-samples", type=int, default=None)
    parser.add_argument("--per-device-train-batch-size", type=int, default=8)
    parser.add_argument("--per-device-eval-batch-size", type=int, default=8)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.06)
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--num-train-epochs", type=float, default=8.0)
    parser.add_argument("--eval-steps", type=int, default=100)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--logging-steps", type=int, default=25)
    parser.add_argument("--save-total-limit", type=int, default=2)
    parser.add_argument("--dataloader-num-workers", type=int, default=0)
    parser.add_argument("--no-fp16", action="store_true")
    args = parser.parse_args()

    if args.smoke:
        args.max_train_samples = args.max_train_samples or 50
        args.max_eval_samples = args.max_eval_samples or 20
        args.max_steps = min(args.max_steps, 30)
        args.eval_steps = min(args.eval_steps, 10)
        args.save_steps = min(args.save_steps, 10)

    args.fp16 = not args.no_fp16
    if args.output_dir is None:
        args.output_dir = _default_output_dir(args.smoke)
    return args


def main() -> None:
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite_output_dir:
        raise FileExistsError(
            f"Output directory is not empty: {output_dir}. "
            "Use --overwrite-output-dir or choose a new --output-dir."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_root = _resolve_dataset_root(args.dataset_root, args.download_kaggle)
    train_raw, train_audit = load_vaipe_split(_split_dir(dataset_root, "public_train"))
    public_test_raw, public_test_audit = load_vaipe_split(
        _split_dir(dataset_root, "public_test")
    )
    if len(train_raw) == 0:
        raise ValueError(f"No labelled VAIPE public_train records found under {dataset_root}")

    train_split, val_split, test_split = _make_splits(
        train_raw,
        val_size=args.val_size,
        test_size=args.test_size,
        seed=args.seed,
    )
    train_split = _limit_dataset(train_split, args.max_train_samples)
    val_split = _limit_dataset(val_split, args.max_eval_samples)
    test_split = _limit_dataset(test_split, args.max_eval_samples)
    public_test_raw = _limit_dataset(public_test_raw, args.max_eval_samples)

    audit = {
        "dataset_root": str(dataset_root),
        "base_model": args.base_model,
        "labels": LABELS,
        "public_train_audit": train_audit,
        "public_test_audit": public_test_audit,
        "split_sizes": {
            "train": len(train_split),
            "validation": len(val_split),
            "test_from_public_train": len(test_split),
            "public_test_labelled": len(public_test_raw),
        },
        "args": _json_safe(vars(args)),
    }
    (output_dir / "data_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit["split_sizes"], indent=2))

    processor = _load_processor(args.base_model)
    train_ds = _preprocess_dataset(
        train_split,
        processor,
        max_length=args.max_length,
        batch_size=args.preprocess_batch_size,
    )
    val_ds = _preprocess_dataset(
        val_split,
        processor,
        max_length=args.max_length,
        batch_size=args.preprocess_batch_size,
    )
    test_ds = _preprocess_dataset(
        test_split,
        processor,
        max_length=args.max_length,
        batch_size=args.preprocess_batch_size,
    )

    model = LayoutLMv3ForTokenClassification.from_pretrained(
        args.base_model,
        num_labels=len(LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,
    )

    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": _training_args(args, output_dir),
        "train_dataset": train_ds,
        "eval_dataset": val_ds,
        "data_collator": DefaultDataCollator(return_tensors="pt"),
        "compute_metrics": _compute_metrics,
    }
    trainer_signature = inspect.signature(Trainer.__init__)
    if "processing_class" in trainer_signature.parameters:
        trainer_kwargs["processing_class"] = processor
    else:
        trainer_kwargs["tokenizer"] = processor

    trainer = Trainer(**trainer_kwargs)
    trainer.train()

    metrics = {
        "validation": trainer.evaluate(val_ds, metric_key_prefix="validation"),
        "test_from_public_train": trainer.evaluate(test_ds, metric_key_prefix="test"),
    }
    if len(public_test_raw) > 0:
        public_test_ds = _preprocess_dataset(
            public_test_raw,
            processor,
            max_length=args.max_length,
            batch_size=args.preprocess_batch_size,
        )
        metrics["public_test"] = trainer.evaluate(
            public_test_ds,
            metric_key_prefix="public_test",
        )

    final_dir = output_dir / "final"
    trainer.save_model(str(final_dir))
    processor.save_pretrained(str(final_dir))
    (output_dir / "final_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved final model: {final_dir}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
