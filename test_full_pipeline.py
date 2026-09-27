"""Run one raw prescription image through OCR, NER, and medicine mapping."""

import json
import os
from pathlib import Path

from inference import parse_ner_output, run_inference
from medicine_mapper import MedicineMapper, PrescriptionMapping
from ocr_engine import run_ocr


REPO_ROOT = Path(__file__).resolve().parent
IMAGE_PATH = REPO_ROOT / "public_train" / "prescription" / "image" / "VAIPE_P_TRAIN_0.png"
OUTPUT_PATH = REPO_ROOT / "results" / "VAIPE_P_TRAIN_0_full_pipeline.json"


def _print_ocr_stage(ocr_results: list[dict]) -> None:
    print("=== OCR STAGE ===")
    print(f"Tổng số vùng chữ: {len(ocr_results)}")
    print(f"Total OCR regions = phrase-level tokens into NER: {len(ocr_results)}")
    print("10 kết quả OCR đầu tiên:")
    for item in ocr_results[:10]:
        print(
            f"- text={item['text']} | confidence={item['confidence']:.4f} | box={item['box']}"
        )


def _print_ner_stage(predictions: list[dict], parsed_ner: dict) -> None:
    print("\n=== NER STAGE ===")
    print("20 dự đoán word→label đầu tiên:")
    for prediction in predictions[:20]:
        print(f"- {prediction['word']} → {prediction['label']}")
    print("NER đã parse:")
    print(json.dumps(parsed_ner, ensure_ascii=False, indent=2))


def _print_mapper_stage(mapping: PrescriptionMapping) -> None:
    print("\n=== MAPPER STAGE ===")
    if not mapping.drugs:
        print("Không có thuốc nào được NER phát hiện.")
        return

    for drug in mapping.drugs:
        normalized = drug.name_normalized if drug.match_confidence >= 70 else "NOT IN KB"
        print(f"- Thuốc #{drug.drug_number}")
        print(f"  name_extracted: {drug.name_extracted}")
        print(f"  match_confidence: {drug.match_confidence}")
        print(f"  name_normalized: {normalized}")
        print(f"  gloss_sections: {drug.gloss_sections}")


def _print_summary(mapping: PrescriptionMapping) -> None:
    total_drugs = len(mapping.drugs)
    mapped = sum(1 for drug in mapping.drugs if drug.match_confidence >= 70 and drug.drug_info)
    missing = total_drugs - mapped

    print("\n=== SUMMARY ===")
    print(f"Tổng số thuốc NER phát hiện: {total_drugs}")
    print(f"Số thuốc map được vào KB: {mapped}")
    print(f"Số thuốc thiếu trong KB: {missing}")


def main() -> None:
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy ảnh test: {IMAGE_PATH}")

    ocr_results = run_ocr(str(IMAGE_PATH))
    words = [str(item["text"]) for item in ocr_results]
    boxes = [item["box"] for item in ocr_results]

    predictions = run_inference(str(IMAGE_PATH), words, boxes)
    parsed_ner = parse_ner_output(predictions)

    mapper = MedicineMapper(auto_enrich=False)
    mapping = mapper.map_prescription("rx_test_ocr", parsed_ner)

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(mapper.to_json(mapping), encoding="utf-8")

    _print_ocr_stage(ocr_results)
    _print_ner_stage(predictions, parsed_ner)
    _print_mapper_stage(mapping)
    _print_summary(mapping)
    print(f"\nĐã lưu JSON đầy đủ: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
