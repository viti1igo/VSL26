"""Create the pilot video-editing Excel workbook from locked gloss outputs."""

import csv
import json
import sys
from pathlib import Path
from typing import Any

try:
    from openpyxl import Workbook
except ImportError:
    # The local venv has Pillow for embedded images, while Homebrew Python has
    # openpyxl. This keeps the exporter usable if pip install hangs locally.
    for site_packages in Path("/opt/homebrew/lib").glob("python*/site-packages"):
        if (site_packages / "openpyxl").exists():
            sys.path.append(str(site_packages))
            break
    from openpyxl import Workbook

from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

from medicine_mapper import VSL_FOOTAGE


REPO_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = REPO_ROOT / "results"
OUTPUT_XLSX = RESULTS_DIR / "pilot_video_editing_sheet.xlsx"
FOOTAGE_CSV = RESULTS_DIR / "vsl_footage_required.csv"
LABEL_DIR = REPO_ROOT / "public_train" / "prescription" / "label"
IMAGE_DIR = REPO_ROOT / "public_train" / "prescription" / "image"
PILOT_IDS = [
    "VAIPE_P_TRAIN_904",
    "VAIPE_P_TRAIN_457",
    "VAIPE_P_TRAIN_871",
    "VAIPE_P_TRAIN_877",
]

PILOT_HEADERS = [
    "row_id",
    "prescription_id",
    "prescription_image",
    "image_path",
    "drug_number",
    "drug_name_extracted",
    "drug_name_normalized",
    "ner_diagnose",
    "ner_drugname",
    "ner_quantity",
    "ner_usage",
    "ner_date",
    "ner_other_count",
    "gloss_dung_cho",
    "gloss_dung_nhu_nao",
    "gloss_luu_y",
    "gloss_ket_bai_full",
    "full_video_sequence",
    "total_token_count",
    "estimated_duration_sec",
    "vsl_footage_ids",
]


def text(value: Any) -> str:
    return str(value or "").strip()


def join_tokens(tokens: list[str]) -> str:
    return " + ".join(tokens)


def flatten_closing(closing: dict[str, Any]) -> list[list[str]]:
    sections: list[list[str]] = []
    cluster = closing.get("tac_dung_phu_cluster") or []
    if cluster:
        sections.append([str(token) for token in cluster])
    if_one = closing.get("if_one_of_three") or []
    if if_one:
        sections.append([str(token) for token in if_one])
    for action in closing.get("actions") or []:
        sections.append([str(token) for token in action])
    return sections


def flatten_closing_tokens(closing: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for section in flatten_closing(closing):
        tokens.extend(section)
    return tokens


def closing_for_editor(closing: dict[str, Any]) -> str:
    return " || ".join(join_tokens(section) for section in flatten_closing(closing))


def footage_ids_for_tokens(tokens: list[str]) -> list[str]:
    return [VSL_FOOTAGE.get(token, f"VSL_TBD_{token}") for token in tokens]


def all_row_tokens(drug: dict[str, Any], closing: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str]]:
    sections = drug.get("gloss_sections") or {}
    dung_cho = [str(token) for token in sections.get("dung_cho") or []]
    dung_nhu_nao = [str(token) for token in sections.get("dung_nhu_nao") or []]
    luu_y = [str(token) for token in sections.get("luu_y") or []]
    ket_bai = flatten_closing_tokens(closing)
    return dung_cho, dung_nhu_nao, luu_y, ket_bai


def load_mapping(prescription_id: str) -> dict[str, Any]:
    path = RESULTS_DIR / f"pilot_final_{prescription_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing pilot final JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def matching_image(prescription_id: str) -> Path:
    for extension in (".png", ".jpg", ".jpeg"):
        image_path = IMAGE_DIR / f"{prescription_id}{extension}"
        if image_path.exists():
            return image_path
    raise FileNotFoundError(f"Missing image for {prescription_id}")


def extract_annotation_entities(prescription_id: str) -> dict[str, Any]:
    path = LABEL_DIR / f"{prescription_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing annotation JSON: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = {"date": [], "diagnose": [], "drugname": [], "quantity": [], "usage": []}
    other_count = 0

    if isinstance(data, list):
        for item in data:
            label = text(item.get("label")) if isinstance(item, dict) else ""
            value = text(item.get("text")) if isinstance(item, dict) else ""
            if label == "other":
                other_count += 1
            elif label in groups and value:
                groups[label].append(value)
    elif isinstance(data, dict):
        words = data.get("words") or data.get("tokens") or []
        labels = data.get("ner_tags") or data.get("labels") or []
        for word, label in zip(words, labels):
            label = text(label)
            value = text(word)
            if label == "other":
                other_count += 1
            elif label in groups and value:
                groups[label].append(value)

    return {
        "date": " | ".join(groups["date"]),
        "diagnose": " | ".join(groups["diagnose"]),
        "drugname": " | ".join(groups["drugname"]),
        "quantity": " | ".join(groups["quantity"]),
        "usage": " | ".join(groups["usage"]),
        "other_count": other_count,
    }


def make_preview_image(image_path: Path, row_id: int) -> Path:
    preview_dir = RESULTS_DIR / "_excel_previews"
    preview_dir.mkdir(exist_ok=True)
    output_path = preview_dir / f"{image_path.stem}_preview.png"
    with PILImage.open(image_path) as image:
        image = image.convert("RGB")
        width = 200
        height = max(1, int(image.height * (width / image.width)))
        image.resize((width, height)).save(output_path)
    return output_path


def append_prescription_image(ws, image_path: Path, row_number: int, errors: list[str]) -> None:
    try:
        preview_path = make_preview_image(image_path, row_number)
        excel_image = ExcelImage(str(preview_path))
        excel_image.width = 200
        excel_image.height = 150
        ws.add_image(excel_image, f"C{row_number}")
    except Exception as exc:
        errors.append(f"Image embed failed for {image_path}: {exc}")


def build_pilot_rows(errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    row_id = 1
    for prescription_id in PILOT_IDS:
        mapping = load_mapping(prescription_id)
        annotation = extract_annotation_entities(prescription_id)
        image_path = matching_image(prescription_id)
        for drug in mapping.get("drugs", []):
            dung_cho, dung_nhu_nao, luu_y, ket_bai = all_row_tokens(drug, mapping.get("universal_closing") or {})
            full_sections = [dung_cho, dung_nhu_nao, luu_y, ket_bai]
            full_video_sequence = " ||| ".join(join_tokens(section) for section in full_sections)
            all_tokens = [token for section in full_sections for token in section]
            all_ids = []
            for section_name in ("dung_cho", "dung_nhu_nao", "luu_y"):
                all_ids.extend((drug.get("vsl_footage_ids_by_section") or {}).get(section_name) or [])
            all_ids.extend(footage_ids_for_tokens(ket_bai))
            rows.append(
                {
                    "row_id": row_id,
                    "prescription_id": prescription_id,
                    "prescription_image": "",
                    "image_path": str(image_path),
                    "drug_number": drug.get("drug_number"),
                    "drug_name_extracted": drug.get("name_extracted"),
                    "drug_name_normalized": drug.get("name_normalized"),
                    "ner_diagnose": annotation["diagnose"] or "(none)",
                    "ner_drugname": annotation["drugname"],
                    "ner_quantity": annotation["quantity"],
                    "ner_usage": annotation["usage"],
                    "ner_date": annotation["date"],
                    "ner_other_count": annotation["other_count"],
                    "gloss_dung_cho": join_tokens(dung_cho),
                    "gloss_dung_nhu_nao": join_tokens(dung_nhu_nao),
                    "gloss_luu_y": join_tokens(luu_y),
                    "gloss_ket_bai_full": closing_for_editor(mapping.get("universal_closing") or {}),
                    "full_video_sequence": full_video_sequence,
                    "total_token_count": len(all_tokens),
                    "estimated_duration_sec": mapping.get("estimated_video_duration_seconds"),
                    "vsl_footage_ids": " + ".join(all_ids),
                    "_image_path": image_path,
                    "_missing_vsl": [item for item in all_ids if str(item).startswith("VSL_MISSING")],
                }
            )
            row_id += 1
    return rows


def style_header(ws) -> None:
    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def style_pilot_sheet(ws) -> None:
    widths = {
        "A": 10,
        "B": 24,
        "C": 30,
        "D": 45,
        "E": 14,
        "F": 28,
        "G": 25,
        "H": 35,
        "I": 35,
        "J": 35,
        "K": 35,
        "L": 22,
        "M": 16,
        "N": 50,
        "O": 50,
        "P": 50,
        "Q": 70,
        "R": 80,
        "S": 18,
        "T": 22,
        "U": 80,
    }
    for column, width in widths.items():
        ws.column_dimensions[column].width = width
    for row in range(2, ws.max_row + 1):
        ws.row_dimensions[row].height = 150
    wrap_columns = set("NOPQRU")
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(
                wrap_text=cell.column_letter in wrap_columns,
                vertical="top",
            )


def add_pilot_sheet(wb: Workbook, errors: list[str]) -> tuple[int, bool]:
    ws = wb.active
    ws.title = "Pilot Videos"
    ws.append(PILOT_HEADERS)
    rows = build_pilot_rows(errors)
    for row in rows:
        ws.append([row.get(header, "") for header in PILOT_HEADERS])
        append_prescription_image(ws, row["_image_path"], ws.max_row, errors)
    style_header(ws)
    style_pilot_sheet(ws)
    all_complete = all(
        row["gloss_dung_cho"]
        and row["gloss_dung_nhu_nao"]
        and row["gloss_luu_y"]
        and row["gloss_ket_bai_full"]
        and not row["_missing_vsl"]
        for row in rows
    )
    return len(rows), all_complete


def add_footage_sheet(wb: Workbook) -> int:
    ws = wb.create_sheet("VSL Footage Tokens")
    headers = ["token", "vsl_id", "status", "frequency_in_pilot"]
    ws.append(headers)
    with FOOTAGE_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            ws.append([row.get(header, "") for header in headers])
    style_header(ws)
    for column in range(1, 5):
        ws.column_dimensions[get_column_letter(column)].width = [35, 45, 22, 20][column - 1]
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    return ws.max_row - 1


def add_readme_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("README")
    ws.column_dimensions["A"].width = 120
    lines = [
        "This workbook is a video editing sheet for the four locked VSL26 pilot prescriptions. Each row is one drug instance; future multi-drug prescriptions should use one row per drug and share prescription-level fields through prescription_id.",
        "The ' + ' separator marks gloss token boundaries. Each token should map to one VSL clip or placeholder clip assignment.",
        "The ' || ' separator marks sub-section boundaries inside ket_bai, the universal closing.",
        "The ' ||| ' separator marks major playback sections in full_video_sequence: dung_cho, dung_nhu_nao, luu_y, ket_bai.",
        "Any VSL_TBD_<token> placeholder needs a real VSL footage ID before final video assembly. VSL_MISSING should be zero; if it appears, the token is absent from VSL_FOOTAGE.",
        "Total: 4 rows, 1 drug per prescription.",
    ]
    for index, line in enumerate(lines, start=1):
        ws.cell(row=index, column=1, value=line)
        ws.cell(row=index, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    errors: list[str] = []
    wb = Workbook()
    pilot_rows, all_complete = add_pilot_sheet(wb, errors)
    footage_rows = add_footage_sheet(wb)
    add_readme_sheet(wb)
    wb.save(OUTPUT_XLSX)

    print(f"Output file: {OUTPUT_XLSX}")
    print(f"Sheet names: {', '.join(wb.sheetnames)}")
    print(f"Pilot Videos rows: {pilot_rows}")
    print(f"VSL Footage Tokens rows: {footage_rows}")
    print(f"README rows: {wb['README'].max_row}")
    if errors:
        print("Errors loading images or JSONs:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Errors loading images or JSONs: none")
    print(
        "Complete gloss data with no VSL_MISSING errors: "
        + ("yes" if all_complete else "no")
    )


if __name__ == "__main__":
    main()
