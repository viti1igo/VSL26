"""Export VAIPE-P NER annotation entities into flat CSV review files."""

import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from count_drugs import find_vaipe_dataset


CSV_HEADER = [
    "prescription_id",
    "entity_index",
    "label",
    "text",
    "box_x1",
    "box_y1",
    "box_x2",
    "box_y2",
    "char_length",
    "image_filename",
]
LABEL_ORDER = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
REPO_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = REPO_ROOT / "results"
FULL_CSV_PATH = RESULTS_DIR / "vaipe_ner_dataset.csv"
DRUGS_CSV_PATH = RESULTS_DIR / "vaipe_drugs_only.csv"


@dataclass(frozen=True)
class EntityRow:
    prescription_id: str
    entity_index: int
    label: str
    text: str
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
            self.label,
            self.text,
            self.box_x1,
            self.box_y1,
            self.box_x2,
            self.box_y2,
            self.char_length,
            self.image_filename,
        ]


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


def _image_filename_for(annotation_path: Path) -> str:
    image_dir = annotation_path.parent.parent / "image"
    for extension in [".png", ".jpg", ".jpeg"]:
        candidate = image_dir / f"{annotation_path.stem}{extension}"
        if candidate.exists():
            return candidate.name
    return f"{annotation_path.stem}.png"


def _iter_annotation_items(annotation: Any) -> Iterable[tuple[str, str, Any]]:
    if isinstance(annotation, list):
        for item in annotation:
            if not isinstance(item, dict):
                continue
            yield str(item.get("label", "other")), str(item.get("text", "")), item.get("box", [0, 0, 0, 0])
        return

    if isinstance(annotation, dict):
        words = annotation.get("words", [])
        labels = annotation.get("ner_tags", [])
        boxes = annotation.get("bboxes", annotation.get("boxes", []))
        for text, label, box in zip(words, labels, boxes):
            yield str(label), str(text), box


def load_rows(label_dir: Path) -> list[EntityRow]:
    rows: list[EntityRow] = []
    for annotation_path in sorted(label_dir.glob("*.json")):
        with annotation_path.open("r", encoding="utf-8") as file:
            annotation = json.load(file)

        prescription_id = annotation_path.stem
        image_filename = _image_filename_for(annotation_path)
        entity_index = 0

        for label, raw_text, raw_box in _iter_annotation_items(annotation):
            text = raw_text.strip()
            if not text:
                continue

            box_x1, box_y1, box_x2, box_y2 = _safe_box(raw_box)
            rows.append(
                EntityRow(
                    prescription_id=prescription_id,
                    entity_index=entity_index,
                    label=label,
                    text=raw_text,
                    box_x1=box_x1,
                    box_y1=box_y1,
                    box_x2=box_x2,
                    box_y2=box_y2,
                    char_length=len(text),
                    image_filename=image_filename,
                )
            )
            entity_index += 1

    return rows


def write_csv(path: Path, rows: list[EntityRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(CSV_HEADER)
        writer.writerows(row.as_csv_row() for row in rows)


def _rows_by_label(rows: list[EntityRow]) -> dict[str, list[EntityRow]]:
    grouped: dict[str, list[EntityRow]] = defaultdict(list)
    for row in rows:
        grouped[row.label].append(row)
    return grouped


def print_summary(rows: list[EntityRow]) -> None:
    counts = Counter(row.label for row in rows)
    grouped = _rows_by_label(rows)
    rng = random.Random(42)

    print(f"Total rows written: {len(rows)}")
    print("\nRow count per label:")
    for label in LABEL_ORDER:
        print(f"- {label}: {counts[label]}")

    print("\nTop 3 longest entities per label:")
    for label in LABEL_ORDER:
        print(f"\n[{label}]")
        for row in sorted(grouped.get(label, []), key=lambda item: item.char_length, reverse=True)[:3]:
            print(
                f"- len={row.char_length} | {row.prescription_id}#{row.entity_index} | "
                f"{row.text!r} | box={[row.box_x1, row.box_y1, row.box_x2, row.box_y2]}"
            )

    print("\nAverage character length per label:")
    for label in LABEL_ORDER:
        label_rows = grouped.get(label, [])
        average = sum(row.char_length for row in label_rows) / len(label_rows) if label_rows else 0.0
        print(f"- {label}: {average:.2f}")

    print("\nFive random example rows per label:")
    for label in LABEL_ORDER:
        label_rows = grouped.get(label, [])
        sample = rng.sample(label_rows, k=min(5, len(label_rows))) if label_rows else []
        print(f"\n[{label}]")
        for row in sample:
            print(
                f"- {row.prescription_id},{row.entity_index},{row.label},"
                f"{row.text!r},{[row.box_x1, row.box_y1, row.box_x2, row.box_y2]},"
                f"{row.char_length},{row.image_filename}"
            )


def main() -> None:
    label_dir = find_vaipe_dataset()
    if label_dir is None:
        raise SystemExit(1)

    rows = load_rows(label_dir)
    drug_rows = [row for row in rows if row.label == "drugname"]

    write_csv(FULL_CSV_PATH, rows)
    write_csv(DRUGS_CSV_PATH, drug_rows)

    print(f"Full CSV: {FULL_CSV_PATH}")
    print(f"Drugs-only CSV: {DRUGS_CSV_PATH}")
    print_summary(rows)


if __name__ == "__main__":
    main()
