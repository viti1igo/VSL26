"""Merge adjacent token-level NER predictions into phrase-level CSV rows."""

from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = Path("/home/oai/share/vaipe_test_predictions.csv")
LOCAL_INPUT_PATH = REPO_ROOT / "results" / "vaipe_test_predictions.csv"
OUTPUT_PATH = REPO_ROOT / "results" / "vaipe_test_predictions_merged.csv"
LABEL_ORDER = ["diagnose", "drugname", "quantity", "usage", "date", "other"]


def resolve_input_path() -> Path:
    if DEFAULT_INPUT_PATH.exists():
        return DEFAULT_INPUT_PATH
    if LOCAL_INPUT_PATH.exists():
        return LOCAL_INPUT_PATH
    raise FileNotFoundError(
        f"Không tìm thấy file đầu vào tại {DEFAULT_INPUT_PATH} hoặc {LOCAL_INPUT_PATH}"
    )


def merge_predictions(input_path: Path, output_path: Path) -> pd.DataFrame:
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    df = df.sort_values(["prescription_id", "entity_index"]).reset_index(drop=True)

    merged_rows = []
    for prescription_id, group in df.groupby("prescription_id", sort=False):
        group_index = 0
        current_label = None
        current_rows = []

        def flush_current() -> None:
            nonlocal group_index, current_rows, current_label
            if not current_rows:
                return

            merged_text = " ".join(str(row["text"]).strip() for row in current_rows).strip()
            merged_rows.append(
                {
                    "prescription_id": prescription_id,
                    "group_index": group_index,
                    "label": current_label,
                    "merged_text": merged_text,
                    "merged_box_x1": min(int(row["box_x1"]) for row in current_rows),
                    "merged_box_y1": min(int(row["box_y1"]) for row in current_rows),
                    "merged_box_x2": max(int(row["box_x2"]) for row in current_rows),
                    "merged_box_y2": max(int(row["box_y2"]) for row in current_rows),
                    "merged_char_length": len(merged_text.strip()),
                    "image_filename": current_rows[0]["image_filename"],
                }
            )
            group_index += 1
            current_rows = []
            current_label = None

        for row in group.to_dict("records"):
            label = row["predicted_label"]
            if current_label is None:
                current_label = label
                current_rows = [row]
                continue

            if label == current_label:
                current_rows.append(row)
            else:
                flush_current()
                current_label = label
                current_rows = [row]

        flush_current()

    merged_df = pd.DataFrame(
        merged_rows,
        columns=[
            "prescription_id",
            "group_index",
            "label",
            "merged_text",
            "merged_box_x1",
            "merged_box_y1",
            "merged_box_x2",
            "merged_box_y2",
            "merged_char_length",
            "image_filename",
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return merged_df


def main() -> None:
    input_path = resolve_input_path()
    merged_df = merge_predictions(input_path, OUTPUT_PATH)

    print(f"Saved merged CSV: {OUTPUT_PATH}")
    print(f"Total merged rows: {len(merged_df)}")
    print("Merged phrase count per label:")
    counts = merged_df["label"].value_counts()
    for label in LABEL_ORDER:
        print(f"- {label}: {int(counts.get(label, 0))}")


if __name__ == "__main__":
    main()
