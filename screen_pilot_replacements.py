"""Screen pilot candidate prescriptions for complete usage gloss sections."""

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from inference import parse_ner_output, run_inference
from medicine_mapper import MedicineMapper, PrescriptionMapping
from ocr_engine import run_ocr


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO_ROOT = Path(__file__).resolve().parent
IMAGE_DIR = REPO_ROOT / "public_train" / "prescription" / "image"
RESULTS_DIR = REPO_ROOT / "results"
REPORT_PATH = RESULTS_DIR / "pilot_replacement_screening.md"
GLOSS_JSON_PATH = RESULTS_DIR / "replacement_candidates_gloss.json"

AMLODIPINE_IDS = [
    "VAIPE_P_TRAIN_680",
    "VAIPE_P_TRAIN_681",
    "VAIPE_P_TRAIN_682",
    "VAIPE_P_TRAIN_904",
    "VAIPE_P_TRAIN_905",
    "VAIPE_P_TRAIN_989",
    "VAIPE_P_TRAIN_990",
    "VAIPE_P_TRAIN_991",
    "VAIPE_P_TRAIN_992",
    "VAIPE_P_TRAIN_993",
    "VAIPE_P_TRAIN_994",
    "VAIPE_P_TRAIN_995",
    "VAIPE_P_TRAIN_996",
    "VAIPE_P_TRAIN_997",
]
ENALAPRIL_IDS = [
    "VAIPE_P_TRAIN_398",
    "VAIPE_P_TRAIN_399",
    "VAIPE_P_TRAIN_455",
    "VAIPE_P_TRAIN_457",
    "VAIPE_P_TRAIN_458",
    "VAIPE_P_TRAIN_459",
    "VAIPE_P_TRAIN_460",
    "VAIPE_P_TRAIN_901",
]
TIME_TOKENS = {"buổi sáng", "buổi tối", "buổi trưa", "buổi chiều"}


def find_image(prescription_id: str) -> Path:
    for extension in (".png", ".jpg", ".jpeg"):
        image_path = IMAGE_DIR / f"{prescription_id}{extension}"
        if image_path.exists():
            return image_path
    raise FileNotFoundError(f"Missing image for {prescription_id}")


def run_full_pipeline(prescription_id: str, mapper: MedicineMapper) -> tuple[PrescriptionMapping, dict[str, Any]]:
    image_path = find_image(prescription_id)
    ocr_results = run_ocr(str(image_path))
    words = [str(item["text"]).strip() for item in ocr_results]
    boxes = [item["box"] for item in ocr_results]
    predictions = run_inference(str(image_path), words, boxes)
    ner_output = parse_ner_output(predictions)
    mapping = mapper.map_prescription(prescription_id, ner_output)
    return mapping, ner_output


def select_target_drug(mapping: PrescriptionMapping, canonical: str):
    canonical = canonical.lower()
    for drug in mapping.drugs:
        info = drug.drug_info
        values = [
            str(drug.name_normalized).lower(),
            str(info.drug_id).lower() if info else "",
            str(info.name_generic).lower() if info else "",
            str(info.generic_name_en).lower() if info else "",
        ]
        if canonical in values:
            return drug
    return mapping.drugs[0] if mapping.drugs else None


def evaluate_dung_nhu_nao(tokens: list[str]) -> tuple[bool, list[str], int]:
    has_count = any(re.fullmatch(r"\d+\s+viên", token) for token in tokens)
    time_count = sum(1 for token in tokens if token in TIME_TOKENS)
    has_time = time_count > 0
    ends_daily = bool(tokens) and tokens[-1] == "mỗi ngày"
    reasons = []
    if not has_count:
        reasons.append("missing viên count")
    if not has_time:
        reasons.append("missing timing")
    if not ends_daily:
        reasons.append("missing final mỗi ngày")

    # Lower is better. Complete simple one-dose cases outrank complex cases.
    dose_count = sum(1 for token in tokens if re.fullmatch(r"\d+\s+viên", token))
    score = 0
    if not reasons:
        score += 100
    if dose_count == 1:
        score += 30
    if time_count == 1:
        score += 30
    score -= max(0, len(tokens) - 4)
    return not reasons, reasons, score


def screen_candidate(prescription_id: str, canonical: str, mapper: MedicineMapper) -> dict[str, Any]:
    try:
        mapping, ner_output = run_full_pipeline(prescription_id, mapper)
        drug = select_target_drug(mapping, canonical)
        if drug is None:
            return {
                "prescription_id": prescription_id,
                "drug": canonical,
                "status": "INCOMPLETE",
                "fail_reasons": ["no drug detected by NER"],
                "dung_nhu_nao": [],
                "usage": "",
                "mapping": asdict(mapping),
                "ner_output": ner_output,
                "score": -999,
            }

        dung_nhu_nao = drug.gloss_sections.get("dung_nhu_nao", [])
        complete, fail_reasons, score = evaluate_dung_nhu_nao(dung_nhu_nao)
        return {
            "prescription_id": prescription_id,
            "drug": canonical,
            "name_extracted": drug.name_extracted,
            "name_normalized": drug.name_normalized,
            "match_confidence": drug.match_confidence,
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "fail_reasons": fail_reasons,
            "dung_nhu_nao": dung_nhu_nao,
            "usage": drug.usage_extracted,
            "quantity": drug.quantity_extracted,
            "mapping": asdict(mapping),
            "ner_output": ner_output,
            "score": score,
        }
    except Exception as exc:
        return {
            "prescription_id": prescription_id,
            "drug": canonical,
            "status": "ERROR",
            "fail_reasons": [str(exc)],
            "dung_nhu_nao": [],
            "usage": "",
            "score": -999,
        }


def pick_best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    complete = [row for row in rows if row["status"] == "COMPLETE"]
    if not complete:
        return None
    return sorted(complete, key=lambda row: (-row["score"], row["prescription_id"]))[0]


def top_three(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (-row["score"], row["prescription_id"]))[:3]


def render_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| prescription_id | drug | name_extracted | dung_nhu_nao | status | fail reasons |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["prescription_id"],
                    row["drug"],
                    str(row.get("name_extracted", "")).replace("|", "/"),
                    json.dumps(row["dung_nhu_nao"], ensure_ascii=False).replace("|", "/"),
                    row["status"],
                    "; ".join(row["fail_reasons"]) if row["fail_reasons"] else "",
                ]
            )
            + " |"
        )
    return lines


def build_report(amlodipine_rows: list[dict[str, Any]], enalapril_rows: list[dict[str, Any]]) -> str:
    best_amlodipine = pick_best(amlodipine_rows)
    best_enalapril = pick_best(enalapril_rows)
    lines = [
        "# Pilot Replacement Screening",
        "",
        "Completion criteria: `dung_nhu_nao` contains at least one `N viên`, at least one time-of-day token, and ends with `mỗi ngày`.",
        "",
        "## Amlodipine Candidates",
        "",
        *render_table(amlodipine_rows),
        "",
        "## Enalapril Candidates",
        "",
        *render_table(enalapril_rows),
        "",
        "## Recommended Replacements",
        "",
    ]
    if best_amlodipine:
        lines.append(
            f"- Drug 1 (Amlodipine): `{best_amlodipine['prescription_id']}` with usage "
            f"`{best_amlodipine['dung_nhu_nao']}`"
        )
    else:
        lines.append("- Drug 1 (Amlodipine): no complete replacement found")

    if best_enalapril:
        lines.append(
            f"- Drug 2 (Enalapril): `{best_enalapril['prescription_id']}` with usage "
            f"`{best_enalapril['dung_nhu_nao']}`"
        )
    else:
        lines.append("- Drug 2 (Enalapril): no complete replacement found")

    lines.extend(
        [
            "- Drug 3 (Amoxicillin): `VAIPE_P_TRAIN_871` (kept, already complete)",
            "- Drug 4 (Paracetamol): `VAIPE_P_TRAIN_877` (kept, already complete)",
            "",
        ]
    )
    return "\n".join(lines)


def save_top_candidates(amlodipine_rows: list[dict[str, Any]], enalapril_rows: list[dict[str, Any]]) -> None:
    payload = {
        "amlodipine": top_three(amlodipine_rows),
        "enalapril": top_three(enalapril_rows),
    }
    for rows in payload.values():
        for row in rows:
            row.pop("score", None)
    GLOSS_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    mapper = MedicineMapper(db_path=str(REPO_ROOT / "vaipe_drugs.db"), auto_enrich=False)

    amlodipine_rows = []
    for index, prescription_id in enumerate(AMLODIPINE_IDS, start=1):
        print(f"[Amlodipine {index}/{len(AMLODIPINE_IDS)}] {prescription_id}")
        amlodipine_rows.append(screen_candidate(prescription_id, "amlodipine", mapper))

    enalapril_rows = []
    for index, prescription_id in enumerate(ENALAPRIL_IDS, start=1):
        print(f"[Enalapril {index}/{len(ENALAPRIL_IDS)}] {prescription_id}")
        enalapril_rows.append(screen_candidate(prescription_id, "enalapril", mapper))

    report = build_report(amlodipine_rows, enalapril_rows)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")
    save_top_candidates(amlodipine_rows, enalapril_rows)

    print("\n" + report)
    print(f"Saved report: {REPORT_PATH}")
    print(f"Saved top candidate gloss JSON: {GLOSS_JSON_PATH}")


if __name__ == "__main__":
    main()
