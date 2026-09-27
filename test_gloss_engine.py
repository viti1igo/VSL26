"""Run the locked four-prescription pilot set through structured gloss generation."""

import json
import os
import csv
from collections import Counter
from pathlib import Path

from inference import parse_ner_output, run_inference
from medicine_mapper import MedicineMapper, PrescriptionMapping, VSL_FOOTAGE
from ocr_engine import run_ocr


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO_ROOT = Path(__file__).resolve().parent
IMAGE_DIR = REPO_ROOT / "public_train" / "prescription" / "image"
RESULTS_DIR = REPO_ROOT / "results"
PILOT_PRESCRIPTION_IDS = [
    "VAIPE_P_TRAIN_904",
    "VAIPE_P_TRAIN_457",
    "VAIPE_P_TRAIN_871",
    "VAIPE_P_TRAIN_877",
]
PILOT_EXPECTED = {
    "VAIPE_P_TRAIN_904": ("PAMLONOR 5mg", "Amlodipine"),
    "VAIPE_P_TRAIN_457": ("ENALAPRIL", "Enalapril"),
    "VAIPE_P_TRAIN_871": ("AMOXICILIN 500mg", "Amoxicillin"),
    "VAIPE_P_TRAIN_877": ("PANACTOL 500mg", "Paracetamol"),
}
MANIFEST_PATH = RESULTS_DIR / "pilot_manifest.md"
FOOTAGE_CSV_PATH = RESULTS_DIR / "vsl_footage_required.csv"


def find_image(prescription_id: str) -> Path:
    for extension in (".png", ".jpg", ".jpeg"):
        image_path = IMAGE_DIR / f"{prescription_id}{extension}"
        if image_path.exists():
            return image_path
    raise FileNotFoundError(f"Missing image for {prescription_id} in {IMAGE_DIR}")


def run_full_pipeline(prescription_id: str, mapper: MedicineMapper) -> PrescriptionMapping:
    image_path = find_image(prescription_id)
    ocr_results = run_ocr(str(image_path))
    words = [str(item["text"]).strip() for item in ocr_results]
    boxes = [item["box"] for item in ocr_results]
    predictions = run_inference(str(image_path), words, boxes)
    ner_output = parse_ner_output(predictions)
    return mapper.map_prescription(prescription_id, ner_output)


def flatten_closing_tokens(closing: dict) -> list[str]:
    tokens = []
    for value in closing.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, list):
                    tokens.extend(str(token) for token in item)
                else:
                    tokens.append(str(item))
    return tokens


def all_gloss_tokens(mapping: PrescriptionMapping) -> list[str]:
    tokens = []
    for drug in mapping.drugs:
        for section_tokens in drug.gloss_sections.values():
            tokens.extend(section_tokens)
    tokens.extend(flatten_closing_tokens(mapping.universal_closing))
    return tokens


def is_complete_dung_nhu_nao(tokens: list[str]) -> bool:
    has_count = any(token.endswith(" viên") and token[:1].isdigit() for token in tokens)
    has_time = any(token in {"buổi sáng", "buổi tối", "buổi trưa", "buổi chiều"} for token in tokens)
    return has_count and has_time and bool(tokens) and tokens[-1] == "mỗi ngày"


def has_missing_vsl(mapping: PrescriptionMapping) -> bool:
    for drug in mapping.drugs:
        for ids in drug.vsl_footage_ids_by_section.values():
            if any(str(item).startswith("VSL_MISSING") for item in ids):
                return True
    return False


def complete_status(mapping: PrescriptionMapping) -> str:
    if not mapping.drugs:
        return "INCOMPLETE: no drug detected"
    incomplete = [
        drug.name_extracted
        for drug in mapping.drugs
        if not is_complete_dung_nhu_nao(drug.gloss_sections.get("dung_nhu_nao", []))
    ]
    if incomplete:
        return "INCOMPLETE: " + ", ".join(incomplete)
    if has_missing_vsl(mapping):
        return "INCOMPLETE: VSL_MISSING token"
    return "COMPLETE"


def print_mapping(mapping: PrescriptionMapping) -> None:
    print(f"\n=== {mapping.prescription_id} ===")
    print(f"Diagnoses: {mapping.diagnoses_extracted}")
    for drug in mapping.drugs:
        print(f"Drug {drug.drug_number}: {drug.name_extracted}")
        print(f"  normalized: {drug.name_normalized} ({drug.match_confidence:.1f})")
        print(f"  dung_cho: {drug.gloss_sections.get('dung_cho', [])}")
        print(f"  dung_nhu_nao: {drug.gloss_sections.get('dung_nhu_nao', [])}")
        print(f"  luu_y: {drug.gloss_sections.get('luu_y', [])}")

    closing = mapping.universal_closing
    print("Universal Closing:")
    print(f"  tac_dung_phu_cluster: {closing.get('tac_dung_phu_cluster', [])}")
    print(f"  if_one_of_three: {closing.get('if_one_of_three', [])}")
    print(f"  actions: {closing.get('actions', [])}")
    print(f"Estimated video duration: {mapping.estimated_video_duration_seconds} seconds")


def print_summary_table(mappings: list[PrescriptionMapping]) -> None:
    print("\n=== FINAL PILOT SUMMARY ===")
    print("| prescription_id | drug | complete_status | dung_cho | dung_nhu_nao | luu_y |")
    print("|---|---|---|---|---|---|")
    for mapping in mappings:
        for drug in mapping.drugs:
            print(
                "| "
                + " | ".join(
                    [
                        mapping.prescription_id,
                        drug.name_extracted.replace("|", "/"),
                        complete_status(mapping).replace("|", "/"),
                        json.dumps(drug.gloss_sections.get("dung_cho", []), ensure_ascii=False).replace("|", "/"),
                        json.dumps(drug.gloss_sections.get("dung_nhu_nao", []), ensure_ascii=False).replace("|", "/"),
                        json.dumps(drug.gloss_sections.get("luu_y", []), ensure_ascii=False).replace("|", "/"),
                    ]
                )
                + " |"
            )


def write_manifest(mappings: list[PrescriptionMapping]) -> None:
    token_counter = Counter()
    for mapping in mappings:
        token_counter.update(all_gloss_tokens(mapping))

    total_tokens = sum(mapping.total_gloss_token_count for mapping in mappings)
    lines = [
        "# Final Pilot Manifest",
        "",
        "Final pilot prescriptions are locked. Do not change this scope without creating a new manifest version.",
        "",
        "## Final Prescriptions",
        "",
        "| # | prescription_id | image_path | brand → generic | diagnosis extracted by NER | estimated duration |",
        "|---:|---|---|---|---|---:|",
    ]
    for index, mapping in enumerate(mappings, start=1):
        image_path = find_image(mapping.prescription_id)
        brand, generic = PILOT_EXPECTED[mapping.prescription_id]
        lines.append(
            f"| {index} | `{mapping.prescription_id}` | `{image_path}` | {brand} → {generic} | "
            f"{'; '.join(mapping.diagnoses_extracted) if mapping.diagnoses_extracted else '(none)'} | "
            f"{mapping.estimated_video_duration_seconds}s |"
        )

    lines.extend(["", "## Complete Gloss Output", ""])
    for mapping in mappings:
        lines.extend([f"### {mapping.prescription_id}", ""])
        for drug in mapping.drugs:
            lines.extend(
                [
                    f"- Drug: `{drug.name_extracted}` → `{drug.name_normalized}`",
                    f"- `dung_cho`: {json.dumps(drug.gloss_sections.get('dung_cho', []), ensure_ascii=False)}",
                    f"- `dung_nhu_nao`: {json.dumps(drug.gloss_sections.get('dung_nhu_nao', []), ensure_ascii=False)}",
                    f"- `luu_y`: {json.dumps(drug.gloss_sections.get('luu_y', []), ensure_ascii=False)}",
                    f"- `ket_bai`: {json.dumps(mapping.universal_closing, ensure_ascii=False)}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Token Totals",
            "",
            f"- Total tokens across all 4 videos: {total_tokens}",
            f"- Unique gloss tokens needed: {len(token_counter)}",
            "",
            "## Unique Gloss Tokens",
            "",
        ]
    )
    for token in sorted(token_counter):
        lines.append(f"- {token}")
    MANIFEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_footage_csv(mappings: list[PrescriptionMapping]) -> tuple[int, int]:
    token_counter = Counter()
    for mapping in mappings:
        token_counter.update(all_gloss_tokens(mapping))

    rows = []
    ready = 0
    needs_assignment = 0
    for token, frequency in sorted(token_counter.items()):
        vsl_id = VSL_FOOTAGE.get(token, f"VSL_TBD_{token}")
        status = "needs_assignment" if str(vsl_id).startswith("VSL_TBD_") else "ready"
        if status == "ready":
            ready += 1
        else:
            needs_assignment += 1
        rows.append(
            {
                "token": token,
                "vsl_id": vsl_id,
                "status": status,
                "frequency_in_pilot": frequency,
            }
        )

    with FOOTAGE_CSV_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["token", "vsl_id", "status", "frequency_in_pilot"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)
    return ready, needs_assignment


def main() -> None:
    mapper = MedicineMapper(db_path=str(REPO_ROOT / "vaipe_drugs.db"), auto_enrich=False)
    RESULTS_DIR.mkdir(exist_ok=True)

    mappings = []
    for prescription_id in PILOT_PRESCRIPTION_IDS:
        mapping = run_full_pipeline(prescription_id, mapper)
        mappings.append(mapping)
        print_mapping(mapping)
        output_path = RESULTS_DIR / f"pilot_final_{prescription_id}.json"
        output_path.write_text(mapper.to_json(mapping), encoding="utf-8")
        print(f"Saved: {output_path}")

    print_summary_table(mappings)
    write_manifest(mappings)
    ready, needs_assignment = write_footage_csv(mappings)
    missing_count = sum(1 for mapping in mappings if has_missing_vsl(mapping))
    print("\n=== FINAL VALIDATION ===")
    print(f"Complete prescriptions: {sum(1 for mapping in mappings if complete_status(mapping) == 'COMPLETE')}/4")
    print(f"VSL_MISSING errors: {missing_count}")
    print(f"VSL footage tokens ready: {ready}")
    print(f"VSL footage tokens needing assignment: {needs_assignment}")
    print(f"Saved manifest: {MANIFEST_PATH}")
    print(f"Saved footage list: {FOOTAGE_CSV_PATH}")


if __name__ == "__main__":
    main()
