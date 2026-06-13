"""Compare LayoutLMv3 and vision-LLM extraction through the same VSL mapper."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from count_drugs import find_vaipe_dataset
from llm_extractor import load_project_env
from medicine_mapper import MedicineMapper, PrescriptionMapping


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
DEFAULT_PILOT_ID = "VAIPE_P_TRAIN_904"


def _resolve_image_path(image: str | None, prescription_id: str | None) -> Path:
    if image:
        path = Path(image).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        return path

    target_id = prescription_id or DEFAULT_PILOT_ID
    label_dir = find_vaipe_dataset()
    if label_dir is None:
        raise FileNotFoundError(
            "Could not find VAIPE-P labels. Pass --image for a direct image path."
        )

    image_dir = label_dir.parent / "image"
    for extension in (".png", ".jpg", ".jpeg"):
        candidate = image_dir / f"{target_id}{extension}"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Could not find image for prescription ID: {target_id}")


def _mapping_readiness(mapping: PrescriptionMapping) -> dict[str, Any]:
    mapped_drugs = [
        drug
        for drug in mapping.drugs
        if drug.drug_info is not None and drug.match_confidence >= 70
    ]
    missing_vsl = []
    vsl_tbd = []
    usage_complete = 0

    for drug in mapping.drugs:
        usage_lower = drug.usage_extracted.lower()
        quantity_lower = drug.quantity_extracted.lower()
        has_tablet_count = "viên" in usage_lower or "viên" in quantity_lower
        has_timing = any(
            marker in usage_lower or marker in quantity_lower
            for marker in ("sáng", "trưa", "chiều", "tối")
        )
        if has_tablet_count and has_timing:
            usage_complete += 1

        for section, footage_ids in drug.vsl_footage_ids_by_section.items():
            for footage_id in footage_ids:
                if footage_id.startswith("VSL_MISSING:"):
                    missing_vsl.append(
                        {
                            "drug": drug.name_extracted,
                            "section": section,
                            "footage_id": footage_id,
                        }
                    )
                elif footage_id.startswith("VSL_TBD"):
                    vsl_tbd.append(
                        {
                            "drug": drug.name_extracted,
                            "section": section,
                            "footage_id": footage_id,
                        }
                    )

    return {
        "diagnosis_count": len(mapping.diagnoses_extracted),
        "drug_count": len(mapping.drugs),
        "mapped_drug_count": len(mapped_drugs),
        "usage_complete_count": usage_complete,
        "missing_vsl_count": len(missing_vsl),
        "placeholder_vsl_count": len(vsl_tbd),
        "total_gloss_token_count": mapping.total_gloss_token_count,
        "estimated_video_duration_seconds": mapping.estimated_video_duration_seconds,
        "video_ready": bool(mapping.drugs)
        and len(mapped_drugs) == len(mapping.drugs)
        and usage_complete == len(mapping.drugs)
        and not missing_vsl,
        "missing_vsl": missing_vsl,
        "placeholder_vsl": vsl_tbd,
    }


def _run_layoutlmv3_method(image_path: Path) -> dict[str, Any]:
    from inference import parse_ner_output, run_inference
    from ocr_engine import run_ocr

    ocr_results = run_ocr(str(image_path))
    words = [str(item["text"]) for item in ocr_results]
    boxes = [item["box"] for item in ocr_results]
    predictions = run_inference(str(image_path), words, boxes)
    parsed_ner = parse_ner_output(predictions)
    return {
        "method": "layoutlmv3_ocr_ner",
        "parsed_ner": parsed_ner,
        "debug": {
            "ocr_region_count": len(ocr_results),
            "prediction_count": len(predictions),
            "ocr_preview": ocr_results[:20],
            "prediction_preview": predictions[:40],
        },
    }


def _run_vlm_method(image_path: Path, model: str | None) -> dict[str, Any]:
    from llm_extractor import extract_prescription_with_vlm, vlm_extraction_to_mapper_input

    extraction = extract_prescription_with_vlm(image_path, model=model)
    parsed_ner = vlm_extraction_to_mapper_input(extraction)
    return {
        "method": "vlm_direct_extraction",
        "parsed_ner": parsed_ner,
        "debug": {
            "raw_vlm_extraction": extraction,
        },
    }


def _map_method_output(
    prescription_id: str,
    method_output: dict[str, Any],
    mapper: MedicineMapper,
) -> dict[str, Any]:
    mapping = mapper.map_prescription(
        f"{prescription_id}_{method_output['method']}",
        method_output["parsed_ner"],
    )
    return {
        **method_output,
        "mapping": asdict(mapping),
        "readiness": _mapping_readiness(mapping),
    }


def _method_names(method_arg: str) -> list[str]:
    if method_arg == "both":
        return ["layoutlmv3", "vlm"]
    return [method_arg]


def _print_method_summary(result: dict[str, Any]) -> None:
    readiness = result["readiness"]
    mapping = result["mapping"]
    print(f"\n[{result['method']}]")
    print(f"- diagnosis_count: {readiness['diagnosis_count']}")
    print(f"- drug_count: {readiness['drug_count']}")
    print(f"- mapped_drug_count: {readiness['mapped_drug_count']}")
    print(f"- usage_complete_count: {readiness['usage_complete_count']}")
    print(f"- missing_vsl_count: {readiness['missing_vsl_count']}")
    print(f"- placeholder_vsl_count: {readiness['placeholder_vsl_count']}")
    print(f"- video_ready: {readiness['video_ready']}")
    for drug in mapping["drugs"]:
        print(
            "- drug: "
            f"{drug['name_extracted']} -> {drug['name_normalized']} "
            f"({drug['match_confidence']}%) | "
            f"quantity={drug['quantity_extracted']!r} | "
            f"usage={drug['usage_extracted']!r}"
        )


def run_comparison(
    image_path: Path,
    *,
    method: str,
    model: str | None,
    allow_missing_api_key: bool,
) -> dict[str, Any]:
    load_project_env()
    prescription_id = image_path.stem
    mapper = MedicineMapper(db_path=str(REPO_ROOT / "vaipe_drugs.db"), auto_enrich=False)
    results = []
    skipped = []

    for method_name in _method_names(method):
        if method_name == "layoutlmv3":
            method_output = _run_layoutlmv3_method(image_path)
        elif method_name == "vlm":
            if not os.getenv("OPENAI_API_KEY") and allow_missing_api_key:
                skipped.append(
                    {
                        "method": "vlm_direct_extraction",
                        "reason": "OPENAI_API_KEY is not set",
                    }
                )
                continue
            method_output = _run_vlm_method(image_path, model)
        else:
            raise ValueError(f"Unknown method: {method_name}")

        results.append(_map_method_output(prescription_id, method_output, mapper))

    report = {
        "prescription_id": prescription_id,
        "image_path": str(image_path),
        "methods_requested": _method_names(method),
        "methods_completed": [result["method"] for result in results],
        "skipped": skipped,
        "results": results,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare LayoutLMv3 OCR+NER against direct VLM extraction."
    )
    parser.add_argument("--image", default=None, help="Path to a prescription image.")
    parser.add_argument(
        "--prescription-id",
        default=None,
        help="VAIPE prescription ID to resolve from public_train/prescription/image.",
    )
    parser.add_argument(
        "--method",
        choices=["layoutlmv3", "vlm", "both"],
        default="both",
        help="Which extraction method to run.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Vision model override. Defaults to OPENAI_VISION_MODEL or llm_extractor default.",
    )
    parser.add_argument(
        "--fail-if-no-api-key",
        action="store_true",
        help="Fail instead of skipping VLM when OPENAI_API_KEY is missing.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path. Defaults to results/extraction_method_comparison_<id>.json.",
    )
    args = parser.parse_args()

    image_path = _resolve_image_path(args.image, args.prescription_id)
    report = run_comparison(
        image_path,
        method=args.method,
        model=args.model,
        allow_missing_api_key=not args.fail_if_no_api_key,
    )

    output_path = (
        Path(args.output).expanduser()
        if args.output
        else RESULTS_DIR / f"extraction_method_comparison_{image_path.stem}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Image: {image_path}")
    print(f"Output: {output_path}")
    if report["skipped"]:
        print("\nSkipped:")
        for item in report["skipped"]:
            print(f"- {item['method']}: {item['reason']}")

    for result in report["results"]:
        _print_method_summary(result)


if __name__ == "__main__":
    main()
