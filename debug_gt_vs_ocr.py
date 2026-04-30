"""Compare NER predictions from ground-truth annotation input versus OCR input."""

import math
from pathlib import Path
from typing import Any

from inference import _load_annotation, run_inference
from ocr_engine import run_ocr


REPO_ROOT = Path(__file__).resolve().parent
LABEL_PATH = REPO_ROOT / "public_train" / "prescription" / "label" / "VAIPE_P_TRAIN_0.json"
IMAGE_PATH = REPO_ROOT / "public_train" / "prescription" / "image" / "VAIPE_P_TRAIN_0.png"


def _centroid(box: list[int]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _centroid_distance(a: list[int], b: list[int]) -> float:
    ax, ay = _centroid(a)
    bx, by = _centroid(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _y_overlap(a: list[int], b: list[int]) -> int:
    return max(0, min(int(a[3]), int(b[3])) - max(int(a[1]), int(b[1])))


def _closest_ocr(gt_box: list[int], ocr_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not ocr_rows:
        return None

    def score(row: dict[str, Any]) -> tuple[int, float]:
        box = row["box"]
        # Prefer same-line OCR regions, then nearest centroid.
        return (-_y_overlap(gt_box, box), _centroid_distance(gt_box, box))

    return min(ocr_rows, key=score)


def _run_ground_truth() -> tuple[list[str], list[list[int]], list[str], list[dict]]:
    words, boxes, labels = _load_annotation(LABEL_PATH)
    predictions = run_inference(str(IMAGE_PATH), words, boxes)
    return words, boxes, labels, predictions


def _run_ocr() -> tuple[list[dict], list[dict]]:
    ocr_rows = run_ocr(str(IMAGE_PATH))
    words = [str(row["text"]) for row in ocr_rows]
    boxes = [row["box"] for row in ocr_rows]
    predictions = run_inference(str(IMAGE_PATH), words, boxes)
    return ocr_rows, predictions


def main() -> None:
    if not LABEL_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy annotation: {LABEL_PATH}")
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {IMAGE_PATH}")

    gt_words, gt_boxes, gt_labels, gt_predictions = _run_ground_truth()
    ocr_rows, ocr_predictions = _run_ocr()

    print(f"Image: {IMAGE_PATH}")
    print(f"Annotation: {LABEL_PATH}")

    print("\n=== RUN A: GROUND TRUTH INPUT ===")
    correct = 0
    total = len(gt_words)
    for index, (word, gold_label) in enumerate(zip(gt_words, gt_labels)):
        predicted = (
            gt_predictions[index]["label"]
            if index < len(gt_predictions)
            else "TRUNCATED_BY_MAX_LENGTH"
        )
        is_match = predicted == gold_label
        correct += int(is_match)
        marker = "✓" if is_match else "✗"
        print(f"{word} | gt={gold_label} | pred={predicted} | match={marker}")

    print("\n=== RUN B: OCR INPUT ===")
    for index, row in enumerate(ocr_rows):
        predicted = (
            ocr_predictions[index]["label"]
            if index < len(ocr_predictions)
            else "TRUNCATED_BY_MAX_LENGTH"
        )
        print(f"{row['text']} | box={row['box']} | pred={predicted}")

    ocr_drug_count = sum(1 for prediction in ocr_predictions if prediction["label"] == "drugname")

    print("\n=== FINAL COMPARISON ===")
    print(f"Run A accuracy: {correct}/{total} correct predictions")
    print(f"Run B drug detection count: {ocr_drug_count} predictions labeled drugname")
    print(f"Run A returned predictions: {len(gt_predictions)}/{len(gt_words)} inputs")
    print(f"Run B returned predictions: {len(ocr_predictions)}/{len(ocr_rows)} inputs")

    print("\nGT drug entries vs closest OCR region:")
    for index, (word, box, gold_label) in enumerate(zip(gt_words, gt_boxes, gt_labels)):
        if gold_label != "drugname":
            continue

        gt_predicted = (
            gt_predictions[index]["label"]
            if index < len(gt_predictions)
            else "TRUNCATED_BY_MAX_LENGTH"
        )
        closest = _closest_ocr(box, ocr_rows)
        if closest is None:
            print(
                f'GT: text="{word}" label=drugname → GT_predicted={gt_predicted}\n'
                "OCR: (không có OCR region)"
            )
            continue

        closest_index = ocr_rows.index(closest)
        ocr_text = str(closest["text"])
        ocr_predicted = (
            ocr_predictions[closest_index]["label"]
            if closest_index < len(ocr_predictions)
            else "TRUNCATED_BY_MAX_LENGTH"
        )
        print(
            f'GT: text="{word}" label=drugname → GT_predicted={gt_predicted}\n'
            f'OCR: text="{ocr_text}" box={closest["box"]} → OCR_predicted={ocr_predicted}'
        )


if __name__ == "__main__":
    main()
