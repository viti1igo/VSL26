"""Validate post-Wave-1 KB cleanup on prescriptions containing newly handled drugs."""

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from count_drugs import normalize_drug_name
from inference import parse_ner_output, run_inference
from medicine_mapper import MedicineMapper, MappingResult
from ocr_engine import run_ocr


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO_ROOT = Path(__file__).resolve().parent
LABEL_DIR = REPO_ROOT / "public_train" / "prescription" / "label"
IMAGE_DIR = REPO_ROOT / "public_train" / "prescription" / "image"
CURRENT_DB = REPO_ROOT / "vaipe_drugs.db"
BACKUP_DB = REPO_ROOT / "vaipe_drugs.db.backup_wave1"
REPORT_PATH = REPO_ROOT / "results" / "wave1_validation_report_v2.md"

WAVE1_TERMS = [
    "dixirein",
    "sergurop",
    "mediplex",
    "chorlatcyn",
    "livonic",
    "medibogan",
    "bloza",
    "ingaron",
    "mezafen",
    "alfachim",
    "fudcime",
    "carudxan",
    "famogast",
    "gluzitop",
    "milurit",
    "vitamin c stada",
    "goutcolcin",
    "sadapron",
    "becosemid",
    "anpemux",
    "dorocron",
    "normagut",
    "spasvina",
    "pyme diapromr",
    "vitamincstada",
    "bố gan p h",
    "kahagan",
    "gaphyton s",
    "tioga",
    "nifedipin hasan 20 retard",
    "nifedipin t stada retard",
    "c floode",
]
NORMALIZED_WAVE1_TERMS = [normalize_drug_name(term) for term in WAVE1_TERMS]


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_marks.lower()).strip()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_annotation_drugs(annotation_path: Path) -> list[str]:
    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    drugs: list[str] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("label") == "drugname":
                text = clean_text(item.get("text"))
                if text:
                    drugs.append(text)
    elif isinstance(data, dict):
        for word, label in zip(data.get("words", []), data.get("ner_tags", [])):
            if label == "drugname":
                text = clean_text(word)
                if text:
                    drugs.append(text)

    return drugs


def matching_image(stem: str) -> Path | None:
    for extension in (".png", ".jpg", ".jpeg"):
        candidate = IMAGE_DIR / f"{stem}{extension}"
        if candidate.exists():
            return candidate
    return None


def hits_wave1_terms(drugs: list[str]) -> list[str]:
    normalized_drugs = normalize_drug_name(" ".join(drugs))
    return [term for term in NORMALIZED_WAVE1_TERMS if term and term in normalized_drugs]


def select_prescriptions(limit: int = 10) -> list[dict[str, Any]]:
    if not LABEL_DIR.exists():
        raise FileNotFoundError(f"Missing label directory: {LABEL_DIR}")
    if not IMAGE_DIR.exists():
        raise FileNotFoundError(f"Missing image directory: {IMAGE_DIR}")

    selected: list[dict[str, Any]] = []
    used_prescriptions: set[str] = set()
    covered_terms: set[str] = set()
    candidates: list[dict[str, Any]] = []

    for annotation_path in sorted(LABEL_DIR.glob("*.json")):
        image_path = matching_image(annotation_path.stem)
        if image_path is None:
            continue
        annotation_drugs = load_annotation_drugs(annotation_path)
        hits = hits_wave1_terms(annotation_drugs)
        if not hits:
            continue
        candidates.append(
            {
                "prescription_id": annotation_path.stem,
                "image_path": image_path,
                "annotation_drugs": annotation_drugs,
                "wave1_hits": hits,
            }
        )

    # First pass: maximize unique Wave 1 names represented in the validation set.
    for candidate in candidates:
        if len(selected) >= limit:
            break
        if candidate["prescription_id"] in used_prescriptions:
            continue
        if any(hit not in covered_terms for hit in candidate["wave1_hits"]):
            selected.append(candidate)
            used_prescriptions.add(candidate["prescription_id"])
            covered_terms.update(candidate["wave1_hits"])

    # Second pass: fill any remaining slots with matching prescriptions.
    for candidate in candidates:
        if len(selected) >= limit:
            break
        if candidate["prescription_id"] in used_prescriptions:
            continue
        selected.append(candidate)
        used_prescriptions.add(candidate["prescription_id"])

    return selected


def matched_drug_count(mapping_drugs: list[MappingResult]) -> int:
    return sum(1 for drug in mapping_drugs if drug.drug_info is not None and drug.match_confidence >= 70.0)


def cleanup_actions(parsed_ner: dict[str, Any]) -> list[dict[str, str]]:
    return list(parsed_ner.get("cleanup_applied") or [])


def cleanup_count(parsed_ner: dict[str, Any], action: str) -> int:
    return sum(1 for item in cleanup_actions(parsed_ner) if item.get("action") == action)


def pre_cleanup_drug_count(parsed_ner: dict[str, Any]) -> int:
    return len((parsed_ner.get("raw_groups_pre_cleanup") or {}).get("drugname") or [])


def post_cleanup_drug_count(parsed_ner: dict[str, Any]) -> int:
    return len((parsed_ner.get("raw_groups") or {}).get("drugname") or [])


def summarize_cleanup(results: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts: dict[str, int] = {}
    possible_overfiltered: list[str] = []
    pre_total = 0
    post_total = 0

    for result in results:
        parsed_ner = result["ner_output"]
        pre_total += pre_cleanup_drug_count(parsed_ner)
        post_total += post_cleanup_drug_count(parsed_ner)
        for action in cleanup_actions(parsed_ner):
            action_name = action.get("action", "")
            action_counts[action_name] = action_counts.get(action_name, 0) + 1
            if action_name in {"rejected_short_drug", "rejected_punctuation_or_single_char"}:
                possible_overfiltered.append(
                    f"{result['selection']['prescription_id']}: {action.get('text', '')}"
                )

    return {
        "pre_total": pre_total,
        "post_total": post_total,
        "action_counts": action_counts,
        "possible_overfiltered": possible_overfiltered,
    }


def describe_drug_info(drug: MappingResult) -> tuple[str, str, str, bool]:
    if drug.drug_info is None:
        return "", "", "", False

    drug_info = drug.drug_info
    mapped_illness = "; ".join(drug_info.illness_vn or [])
    drug_class = clean_text(drug_info.drug_class_vn)
    traditional = bool(getattr(drug_info, "is_traditional", False)) or drug_info.name_generic is None
    return mapped_illness, drug_class, clean_text(drug_info.drug_id), traditional


def plausibility_check(drug: MappingResult, diagnoses: list[str]) -> tuple[str, str]:
    if drug.drug_info is None:
        return "FLAG", "Không map được vào KB."

    diagnosis_text = strip_accents(" ".join(diagnoses))
    mapped_illness, drug_class, _drug_id, traditional = describe_drug_info(drug)
    info_text = strip_accents(
        " ".join(
            [
                drug.name_normalized,
                mapped_illness,
                drug_class,
                clean_text(drug.drug_info.child_friendly_use_vn),
                clean_text(drug.drug_info.name_generic),
                clean_text(drug.drug_info.name_vn),
            ]
        )
    )

    if traditional:
        return "OK", "Thuốc đông y/thảo dược; cần người review ngữ cảnh nhưng không sai rõ ràng."
    if not diagnosis_text:
        return "OK", "NER không trích xuất chẩn đoán để đối chiếu."

    hypertension = any(token in diagnosis_text for token in ("tang huyet ap", "i10", "huyet ap"))
    diabetes = any(token in diagnosis_text for token in ("dai thao duong", "e11", "tieu duong"))
    respiratory = any(
        token in diagnosis_text
        for token in (
            "viem hong",
            "viem phe quan",
            "viem amidan",
            "nhiem khuan ho hap",
            "cum",
            "virus",
        )
    ) or bool(re.search(r"\bho\b", diagnosis_text))
    allergy = any(token in diagnosis_text for token in ("di ung", "viem mui", "ngua", "me day"))
    gastric = any(token in diagnosis_text for token in ("da day", "trao nguoc", "loet", "dau thuong vi"))
    liver = any(token in diagnosis_text for token in ("gan", "mat", "viem gan"))
    gout = any(token in diagnosis_text for token in ("gout", "gut", "acid uric"))
    musculoskeletal = any(
        token in diagnosis_text
        for token in ("khop", "tran dich", "m25", "dau lung", "dau vai", "dau co", "thoai hoa")
    )

    checks = [
        (
            hypertension,
            ("huyet ap", "tim mach", "arb", "uc che men", "chen kenh calci", "loi tieu", "losartan", "nifedipine", "doxazosin"),
            "Chẩn đoán tăng huyết áp nhưng thuốc không giống nhóm tim mạch/hạ áp.",
        ),
        (
            diabetes,
            ("duong huyet", "dai thao duong", "gliclazide", "metformin", "insulin"),
            "Chẩn đoán đái tháo đường nhưng thuốc không giống nhóm hạ đường huyết.",
        ),
        (
            respiratory,
            ("khang sinh", "ho hap", "long dom", "giam dau", "ha sot", "chong viem", "di ung", "carbocisteine", "cefixime", "cefpodoxime", "loratadine", "paracetamol"),
            "Chẩn đoán hô hấp/viêm họng nhưng thuốc không giống kháng sinh, long đờm, dị ứng hoặc giảm đau/hạ sốt.",
        ),
        (
            allergy,
            ("di ung", "khang histamin", "loratadine", "cetirizine", "me day"),
            "Chẩn đoán dị ứng nhưng thuốc không giống nhóm kháng histamin/dị ứng.",
        ),
        (
            gastric,
            ("da day", "ppi", "prazol", "famotidine", "omeprazole", "khang histamin h2"),
            "Chẩn đoán dạ dày nhưng thuốc không giống nhóm dạ dày/PPI/H2.",
        ),
        (
            liver,
            ("gan", "mat", "actiso", "duoc lieu", "thao duoc"),
            "Chẩn đoán gan/mật nhưng thuốc không có dấu hiệu hỗ trợ gan/mật.",
        ),
        (
            gout,
            ("gout", "colchicine", "allopurinol", "acid uric"),
            "Chẩn đoán gout nhưng thuốc không giống colchicine/allopurinol.",
        ),
        (
            musculoskeletal,
            ("giam dau", "chong viem", "nsaid", "loxoprofen", "diclofenac", "paracetamol", "corticoid", "prednisolone"),
            "Chẩn đoán cơ-xương-khớp nhưng thuốc không giống nhóm giảm đau/chống viêm.",
        ),
    ]

    active_checks = [check for check in checks if check[0]]
    if not active_checks:
        return "OK", "Không có rule chẩn đoán cụ thể; không thấy sai rõ ràng."

    if any(any(keyword in info_text for keyword in keywords) for _active, keywords, _message in active_checks):
        return "OK", "Nhóm thuốc phù hợp với ít nhất một chẩn đoán/rule."

    messages = [message for _active, _keywords, message in active_checks]
    return "FLAG", " ".join(messages)


def run_pipeline_for_prescription(item: dict[str, Any], mapper_after: MedicineMapper, mapper_before: MedicineMapper | None) -> dict[str, Any]:
    image_path = item["image_path"]
    prescription_id = item["prescription_id"]

    ocr_results = run_ocr(str(image_path))
    words = [clean_text(result["text"]) for result in ocr_results]
    boxes = [result["box"] for result in ocr_results]
    predictions = run_inference(str(image_path), words, boxes)
    parsed_ner = parse_ner_output(predictions)

    after_mapping = mapper_after.map_prescription(prescription_id, parsed_ner)
    before_mapping = mapper_before.map_prescription(prescription_id, parsed_ner) if mapper_before else None

    return {
        "selection": item,
        "ocr_count": len(ocr_results),
        "ner_output": parsed_ner,
        "after_mapping": after_mapping,
        "before_mapping": before_mapping,
    }


def render_report(results: list[dict[str, Any]]) -> str:
    total_before = 0
    matched_before = 0
    total_after = 0
    matched_after = 0
    flagged_rows: list[tuple[str, MappingResult, str]] = []

    lines: list[str] = [
        "# Wave 1 Validation Report v2",
        "",
        "Validation reran OCR → NER → Mapper on 10 training prescriptions selected from annotations containing Wave 1 drug names.",
        "This version includes parse_ner_output cleanup diagnostics for enumeration, dosage, and stray punctuation drug entries.",
        "",
    ]

    for result in results:
        before_mapping = result["before_mapping"]
        after_mapping = result["after_mapping"]
        total_after += len(after_mapping.drugs)
        matched_after += matched_drug_count(after_mapping.drugs)
        if before_mapping is not None:
            total_before += len(before_mapping.drugs)
            matched_before += matched_drug_count(before_mapping.drugs)

    before_rate = matched_before / total_before if total_before else 0.0
    after_rate = matched_after / total_after if total_after else 0.0
    improvement = after_rate - before_rate
    cleanup_summary = summarize_cleanup(results)
    action_counts = cleanup_summary["action_counts"]
    rejected_noise = (
        action_counts.get("rejected_enumeration", 0)
        + action_counts.get("rejected_pure_dosage", 0)
        + action_counts.get("rejected_punctuation_or_single_char", 0)
        + action_counts.get("rejected_short_drug", 0)
        + action_counts.get("rejected_empty_drug", 0)
        + action_counts.get("rejected_empty_after_cleanup", 0)
    )

    lines.extend(
        [
            "## Coverage Summary",
            "",
            f"- Before Wave 1: {matched_before}/{total_before} drugs matched ({before_rate:.1%})",
            f"- After Wave 1: {matched_after}/{total_after} drugs matched ({after_rate:.1%})",
            f"- Coverage improvement: {improvement:+.1%} points",
            "",
        ]
    )

    lines.extend(
        [
            "## Parser Cleanup Summary",
            "",
            f"- Drug groups before cleanup: {cleanup_summary['pre_total']}",
            f"- Drug groups after cleanup: {cleanup_summary['post_total']}",
            f"- Noise drug entries rejected or rerouted: {rejected_noise}",
            f"- Enumeration entries rejected: {action_counts.get('rejected_enumeration', 0)}",
            f"- Pure dosage entries removed from drugs: {action_counts.get('rejected_pure_dosage', 0)}",
            f"- Pure dosage entries rerouted to quantity: {action_counts.get('rerouted_to_quantity', 0)}",
            f"- Leading enumerations stripped from drug names: {action_counts.get('stripped_enumeration', 0)}",
            f"- Stray punctuation/single-character entries rejected: {action_counts.get('rejected_punctuation_or_single_char', 0)}",
            f"- Short drug entries rejected: {action_counts.get('rejected_short_drug', 0)}",
            "",
            "Potential over-filter cases:",
        ]
    )
    if cleanup_summary["possible_overfiltered"]:
        lines.extend(f"- {item}" for item in cleanup_summary["possible_overfiltered"])
    else:
        lines.append("- None. No short alphanumeric drug names such as `C1000` were filtered in this run.")
    lines.append("")

    lines.extend(["## Prescription Details", ""])
    for result in results:
        selection = result["selection"]
        mapping = result["after_mapping"]
        parsed_ner = result["ner_output"]
        diagnoses = mapping.diagnoses_extracted
        lines.extend(
            [
                f"### {selection['prescription_id']}",
                "",
                f"- Wave 1 target terms in annotation: {', '.join(selection['wave1_hits'])}",
                f"- Annotation drug rows: {' | '.join(selection['annotation_drugs'])}",
                f"- OCR regions: {result['ocr_count']}",
                f"- Diagnoses extracted by NER: {'; '.join(diagnoses) if diagnoses else '(none)'}",
                f"- Drug groups before cleanup: {pre_cleanup_drug_count(parsed_ner)}",
                f"- Drug groups after cleanup: {post_cleanup_drug_count(parsed_ner)}",
                f"- Cleanup actions: {json.dumps(cleanup_actions(parsed_ner), ensure_ascii=False) if cleanup_actions(parsed_ner) else '[]'}",
                f"- Drugs detected by NER: {' | '.join(drug.name_extracted for drug in mapping.drugs) if mapping.drugs else '(none)'}",
                "",
                "| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |",
                "|---|---|---:|---|---|---|",
            ]
        )
        for drug in mapping.drugs:
            mapped_illness, drug_class, _drug_id, _traditional = describe_drug_info(drug)
            sanity, sanity_note = plausibility_check(drug, diagnoses)
            if sanity == "FLAG":
                flagged_rows.append((selection["prescription_id"], drug, sanity_note))
            lines.append(
                "| "
                + " | ".join(
                    [
                        clean_text(drug.name_extracted).replace("|", "/"),
                        clean_text(drug.name_normalized).replace("|", "/"),
                        f"{drug.match_confidence:.1f}",
                        (mapped_illness or "").replace("|", "/"),
                        (drug_class or "").replace("|", "/"),
                        f"{sanity}: {sanity_note}".replace("|", "/"),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Flagged Potentially Wrong Mappings", ""])
    if not flagged_rows:
        lines.append("- None flagged by the rule-based consistency checks.")
    else:
        for prescription_id, drug, reason in flagged_rows:
            lines.append(
                f"- **{prescription_id}**: `{drug.name_extracted}` → `{drug.name_normalized}` "
                f"({drug.match_confidence:.1f}) — {reason}"
            )
    lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- This is a rule-based smoke test, not clinical validation.",
            "- A `FLAG` means the mapper output deserves manual inspection; it does not prove the mapping is wrong.",
            "- The before/after comparison uses the same OCR and NER output, then maps once with `vaipe_drugs.db.backup_wave1` and once with the current `vaipe_drugs.db`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    selected = select_prescriptions(limit=10)
    if len(selected) < 10:
        print(f"Warning: only found {len(selected)} matching prescriptions.")

    mapper_after = MedicineMapper(db_path=str(CURRENT_DB), auto_enrich=False)
    mapper_before = MedicineMapper(db_path=str(BACKUP_DB), auto_enrich=False) if BACKUP_DB.exists() else None

    results: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] Processing {item['prescription_id']}...")
        results.append(run_pipeline_for_prescription(item, mapper_after, mapper_before))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = render_report(results)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print("\n" + report)
    print(f"Saved report to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
