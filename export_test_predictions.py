"""Run OCR and NER over public test prescription images and export predictions."""

import argparse
import csv
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from count_drugs import normalize_drug_name


CSV_HEADER = [
    "prescription_id",
    "entity_index",
    "predicted_label",
    "text",
    "ocr_confidence",
    "box_x1",
    "box_y1",
    "box_x2",
    "box_y2",
    "char_length",
    "image_filename",
]
LABEL_ORDER = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
REPO_ROOT = Path(__file__).resolve().parent
TEST_IMAGE_DIR = REPO_ROOT / "public_test" / "prescription" / "image"
RESULTS_DIR = REPO_ROOT / "results"
FULL_CSV_PATH = RESULTS_DIR / "vaipe_test_predictions.csv"
DRUGS_CSV_PATH = RESULTS_DIR / "vaipe_test_drugs_only.csv"


@dataclass(frozen=True)
class PredictionRow:
    prescription_id: str
    entity_index: int
    predicted_label: str
    text: str
    ocr_confidence: float
    box_x1: int
    box_y1: int
    box_x2: int
    box_y2: int
    char_length: int
    image_filename: str

    def as_csv_row(self) -> list[Any]:
        return [
            self.prescription_id,
            self.entity_index,
            self.predicted_label,
            self.text,
            f"{self.ocr_confidence:.6f}",
            self.box_x1,
            self.box_y1,
            self.box_x2,
            self.box_y2,
            self.char_length,
            self.image_filename,
        ]


def _natural_key(path: Path) -> tuple[str, int | str]:
    stem = path.stem
    suffix = stem.rsplit("_", 1)[-1]
    return stem[: -len(suffix)], int(suffix) if suffix.isdigit() else suffix


def _image_paths(limit: int | None = None) -> list[Path]:
    paths = sorted(
        [
            *TEST_IMAGE_DIR.glob("*.png"),
            *TEST_IMAGE_DIR.glob("*.jpg"),
            *TEST_IMAGE_DIR.glob("*.jpeg"),
        ],
        key=_natural_key,
    )
    return paths[:limit] if limit is not None else paths


def _safe_box(raw_box: Any) -> tuple[int, int, int, int]:
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) < 4:
        return 0, 0, 0, 0
    coords = []
    for coord in raw_box[:4]:
        try:
            coords.append(int(coord))
        except (TypeError, ValueError):
            coords.append(0)
    return tuple(coords)  # type: ignore[return-value]


def _write_csv(path: Path, rows: list[PredictionRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(CSV_HEADER)
        writer.writerows(row.as_csv_row() for row in rows)


def _rows_for_image(image_path: Path) -> list[PredictionRow]:
    print(f"  loading OCR/NER modules for {image_path.stem}...", flush=True)
    from inference import run_inference
    from ocr_engine import run_ocr

    print(f"  running OCR for {image_path.stem}...", flush=True)
    ocr_results = run_ocr(str(image_path))
    print(f"  OCR regions: {len(ocr_results)}", flush=True)
    words = [str(result["text"]) for result in ocr_results]
    boxes = [result["box"] for result in ocr_results]
    print(f"  running NER for {image_path.stem}...", flush=True)
    predictions = run_inference(str(image_path), words, boxes)
    print(f"  NER predictions: {len(predictions)}", flush=True)

    rows: list[PredictionRow] = []
    for entity_index, (ocr_result, prediction) in enumerate(zip(ocr_results, predictions)):
        text = str(ocr_result["text"])
        box_x1, box_y1, box_x2, box_y2 = _safe_box(ocr_result.get("box"))
        rows.append(
            PredictionRow(
                prescription_id=image_path.stem,
                entity_index=entity_index,
                predicted_label=str(prediction["label"]),
                text=text,
                ocr_confidence=float(ocr_result.get("confidence", 0.0)),
                box_x1=box_x1,
                box_y1=box_y1,
                box_x2=box_x2,
                box_y2=box_y2,
                char_length=len(text.strip()),
                image_filename=image_path.name,
            )
        )

    if len(predictions) != len(ocr_results):
        raise RuntimeError(
            f"Prediction count mismatch for {image_path.name}: "
            f"OCR={len(ocr_results)}, NER={len(predictions)}"
        )

    return rows


def _print_summary(rows: list[PredictionRow], processed_count: int, errors: list[tuple[str, str]]) -> None:
    label_counts = Counter(row.predicted_label for row in rows)
    drug_counts = Counter(
        normalized
        for row in rows
        if row.predicted_label == "drugname"
        for normalized in [normalize_drug_name(row.text)]
        if normalized
    )

    print("\n=== SUMMARY ===")
    print(f"Total prescriptions processed: {processed_count}")
    print(f"Prescriptions crashed: {len(errors)}")
    for prescription_id, message in errors:
        print(f"- {prescription_id}: {message}")

    print("\nRow count per label:")
    for label in LABEL_ORDER:
        print(f"- {label}: {label_counts[label]}")

    print("\nTop 20 most frequent drugname predictions:")
    for rank, (drug_name, count) in enumerate(drug_counts.most_common(20), start=1):
        print(f"{rank:>2}. {drug_name:<45} {count}")


def export_predictions(limit: int | None = None) -> None:
    image_paths = _image_paths(limit=limit)
    if not image_paths:
        raise FileNotFoundError(f"No test prescription images found in {TEST_IMAGE_DIR}")

    all_rows: list[PredictionRow] = []
    errors: list[tuple[str, str]] = []
    total = len(image_paths)

    for index, image_path in enumerate(image_paths, start=1):
        if index == 1 or index % 10 == 0 or index == total:
            print(f"[{index}/{total}] Processing {image_path.stem}...", flush=True)

        try:
            all_rows.extend(_rows_for_image(image_path))
        except Exception as exc:  # Continue exporting other prescriptions.
            short_error = f"{type(exc).__name__}: {exc}"
            errors.append((image_path.stem, short_error))
            print(f"[ERROR] {image_path.stem}: {short_error}", flush=True)
            traceback.print_exc(limit=1)

    drug_rows = [row for row in all_rows if row.predicted_label == "drugname"]
    _write_csv(FULL_CSV_PATH, all_rows)
    _write_csv(DRUGS_CSV_PATH, drug_rows)

    print(f"\nFull CSV: {FULL_CSV_PATH}")
    print(f"Drugs-only CSV: {DRUGS_CSV_PATH}")
    _print_summary(all_rows, total - len(errors), errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export OCR -> NER predictions for VAIPE-P test prescriptions.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N test images.")
    args = parser.parse_args()
    export_predictions(limit=args.limit)


if __name__ == "__main__":
    main()
