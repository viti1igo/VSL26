"""Inspect VAIPE-P annotation structure around drug rows for one sample file."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ocr_engine import run_ocr


REPO_ROOT = Path(__file__).resolve().parent
LABEL_PATH = REPO_ROOT / "public_train" / "prescription" / "label" / "VAIPE_P_TRAIN_0.json"
IMAGE_PATH = REPO_ROOT / "public_train" / "prescription" / "image" / "VAIPE_P_TRAIN_0.png"


def _load_annotation(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        words = data.get("words") or data.get("tokens") or []
        boxes = data.get("bboxes") or data.get("boxes") or []
        labels = data.get("ner_tags") or data.get("labels") or []
        return [
            {"text": text, "box": box, "label": label}
            for text, box, label in zip(words, boxes, labels)
        ]
    raise ValueError(f"Định dạng annotation không hỗ trợ: {type(data).__name__}")


def _y_overlap(a: list[int], b: list[int]) -> int:
    return max(0, min(int(a[3]), int(b[3])) - max(int(a[1]), int(b[1])))


def _nearby_ocr_rows(ocr_results: list[dict], gt_box: list[int], tolerance: int = 20) -> list[dict]:
    gt_y1, gt_y2 = int(gt_box[1]), int(gt_box[3])
    nearby = []
    for item in ocr_results:
        box = item["box"]
        overlaps = _y_overlap(gt_box, box) > 0
        close = abs(int(box[1]) - gt_y1) <= tolerance or abs(int(box[3]) - gt_y2) <= tolerance
        if overlaps or close:
            nearby.append(item)
    return sorted(nearby, key=lambda item: (item["box"][1], item["box"][0]))


def _print_annotation_structure(entries: list[dict]) -> None:
    labels = Counter(str(entry.get("label", "other")) for entry in entries)
    print("=== FULL ANNOTATION STRUCTURE ===")
    print(f"Tổng số entry: {len(entries)}")
    print("Label counts:")
    for label, count in sorted(labels.items()):
        print(f"- {label}: {count}")

    print("\nFirst 5 entries label=other:")
    for entry in [item for item in entries if item.get("label") == "other"][:5]:
        print(f"- text={entry.get('text')} | box={entry.get('box')}")

    print("\nEntries label=drugname hoặc quantity:")
    for entry in entries:
        if entry.get("label") in {"drugname", "quantity"}:
            print(
                f"- label={entry.get('label')} | text={entry.get('text')} | "
                f"chars={len(str(entry.get('text', '')))} | box={entry.get('box')}"
            )


def _print_drug_row_comparison(entries: list[dict], ocr_results: list[dict]) -> None:
    print("\n=== SIDE-BY-SIDE DRUG ROW COMPARISON ===")
    target_entries = [
        entry for entry in entries if entry.get("label") in {"drugname", "quantity"}
    ]
    for index, entry in enumerate(target_entries, start=1):
        text = str(entry.get("text", ""))
        box = entry.get("box", [0, 0, 0, 0])
        print(f"\nGT #{index}:")
        print(f"- label={entry.get('label')} | text={text} | chars={len(text)} | box={box}")
        print("- OCR regions near same y-range:")
        nearby = _nearby_ocr_rows(ocr_results, box)
        if not nearby:
            print("  (không có OCR region gần y-range này)")
            continue
        for item in nearby:
            ocr_text = str(item["text"])
            print(
                f"  text={ocr_text} | chars={len(ocr_text)} | "
                f"char_diff={len(ocr_text) - len(text)} | box={item['box']}"
            )


def main() -> None:
    if not LABEL_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy annotation: {LABEL_PATH}")
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {IMAGE_PATH}")

    entries = _load_annotation(LABEL_PATH)
    ocr_results = run_ocr(str(IMAGE_PATH))

    print(f"Annotation: {LABEL_PATH}")
    print(f"Image: {IMAGE_PATH}")
    _print_annotation_structure(entries)
    _print_drug_row_comparison(entries, ocr_results)


if __name__ == "__main__":
    main()
