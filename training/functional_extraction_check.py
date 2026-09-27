"""Run OCR -> LayoutLMv3 -> parser checks for a trained checkpoint.

This is not a gold-label accuracy test. It measures whether a checkpoint
produces usable parsed drug rows on unlabeled prescription images.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _repo_root() -> Path:
    return REPO_ROOT


def _image_paths(paths: list[Path], limit: int | None) -> list[Path]:
    images: list[Path] = []
    for path in paths:
        path = path.expanduser()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            images.append(path)
        elif path.is_dir():
            images.extend(
                sorted(
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES
                )
            )
    images = sorted(dict.fromkeys(images))
    return images[:limit] if limit else images


def _run_image(image_path: Path) -> dict[str, Any]:
    from inference import parse_ner_output, run_inference
    from ocr_engine import run_ocr

    ocr_results = run_ocr(str(image_path))
    words = [str(item["text"]) for item in ocr_results]
    boxes = [item["box"] for item in ocr_results]
    predictions = run_inference(str(image_path), words, boxes)
    parsed = parse_ner_output(predictions)
    label_counts = Counter(prediction["label"] for prediction in predictions)
    return {
        "image": str(image_path),
        "ocr_region_count": len(ocr_results),
        "prediction_count": len(predictions),
        "label_counts": dict(label_counts),
        "raw_groups": parsed.get("raw_groups", {}),
        "parsed_drugs": parsed.get("drugs", []),
        "non_other_predictions": [
            prediction for prediction in predictions if prediction["label"] != "other"
        ],
    }


def _write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "image",
                "ocr_region_count",
                "prediction_count",
                "parsed_drug_count",
                "parsed_drug_names",
                "label_counts_json",
            ]
        )
        for item in results:
            drugs = item.get("parsed_drugs") or []
            writer.writerow(
                [
                    item["image"],
                    item["ocr_region_count"],
                    item["prediction_count"],
                    len(drugs),
                    " | ".join(str(drug.get("name", "")) for drug in drugs),
                    json.dumps(item["label_counts"], ensure_ascii=False),
                ]
            )


def parse_args() -> argparse.Namespace:
    repo_root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, help="Checkpoint directory to evaluate.")
    parser.add_argument(
        "--image-path",
        type=Path,
        action="append",
        default=[],
        help="Image file or directory. Can be passed multiple times.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=repo_root / "results" / "functional_extraction_check.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=repo_root / "results" / "functional_extraction_check.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = _repo_root()
    checkpoint = Path(args.checkpoint).expanduser().resolve()
    if not checkpoint.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint}")

    image_inputs = args.image_path or [
        repo_root / "survey_input" / "vaipe_10" / "images",
        repo_root / "survey_input" / "archive_mix_10" / "images",
        repo_root / "survey_input" / "real_world_10" / "images",
    ]
    images = _image_paths(image_inputs, args.limit)
    if not images:
        raise FileNotFoundError("No prescription images found for functional check.")

    os.environ["VSL_LAYOUTLMV3_CHECKPOINT"] = str(checkpoint)
    results = []
    for index, image_path in enumerate(images, start=1):
        print(f"[{index}/{len(images)}] {image_path}")
        results.append(_run_image(image_path))

    summary = {
        "checkpoint": str(checkpoint),
        "image_count": len(results),
        "images_with_parsed_drugs": sum(
            1 for item in results if len(item.get("parsed_drugs") or []) > 0
        ),
        "total_parsed_drugs": sum(len(item.get("parsed_drugs") or []) for item in results),
        "label_totals": dict(
            sum((Counter(item["label_counts"]) for item in results), Counter())
        ),
    }
    payload = {"summary": summary, "results": results}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(args.output_csv, results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote JSON: {args.output_json}")
    print(f"Wrote CSV: {args.output_csv}")


if __name__ == "__main__":
    main()
