"""Build a batch synthetic drug-illness dataset from exported NER entities."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from count_drugs import normalize_drug_name
from medicine_mapper import DrugInfo, DrugKnowledgeBase, MedicineMapper


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = REPO_ROOT / "results" / "vaipe_ner_dataset.csv"
DEFAULT_OUTPUT = REPO_ROOT / "results" / "drug_illness_synthetic.csv"
LABEL_ORDER = ["date", "diagnose", "usage", "quantity", "drugname", "other"]


def _input_columns(df: pd.DataFrame) -> tuple[str, str, str]:
    if "merged_text" in df.columns and "label" in df.columns:
        index_col = "group_index" if "group_index" in df.columns else "entity_index"
        return "label", "merged_text", index_col

    if "predicted_label" in df.columns:
        return "predicted_label", "text", "entity_index"

    if "label" in df.columns:
        return "label", "text", "entity_index"

    raise ValueError("Input CSV must contain either label/text, predicted_label/text, or label/merged_text columns.")


def _merge_token_level_rows(df: pd.DataFrame, label_col: str, text_col: str, index_col: str) -> pd.DataFrame:
    required = {"prescription_id", label_col, text_col, index_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {sorted(missing)}")

    sorted_df = df.sort_values(["prescription_id", index_col]).reset_index(drop=True)
    merged_rows: list[dict[str, Any]] = []

    for prescription_id, group in sorted_df.groupby("prescription_id", sort=False):
        group_index = 0
        current_label: str | None = None
        current_rows: list[dict[str, Any]] = []

        def flush_current() -> None:
            nonlocal current_label, current_rows, group_index
            if not current_rows:
                return

            merged_text = " ".join(str(row[text_col]).strip() for row in current_rows).strip()
            if merged_text:
                merged_rows.append(
                    {
                        "prescription_id": prescription_id,
                        "group_index": group_index,
                        "label": current_label,
                        "merged_text": merged_text,
                    }
                )
                group_index += 1

            current_label = None
            current_rows = []

        for row in group.to_dict("records"):
            label = str(row[label_col])
            text = str(row[text_col]).strip()
            if not text:
                continue

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

    return pd.DataFrame(merged_rows, columns=["prescription_id", "group_index", "label", "merged_text"])


def load_phrase_rows(input_path: Path) -> pd.DataFrame:
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    label_col, text_col, index_col = _input_columns(df)

    if text_col == "merged_text":
        phrase_df = df.rename(columns={label_col: "label"})[
            ["prescription_id", index_col, "label", "merged_text"]
        ].copy()
        phrase_df = phrase_df.rename(columns={index_col: "group_index"})
        phrase_df["merged_text"] = phrase_df["merged_text"].fillna("").astype(str).str.strip()
        return phrase_df[phrase_df["merged_text"] != ""].sort_values(
            ["prescription_id", "group_index"]
        )

    return _merge_token_level_rows(df, label_col, text_col, index_col)


def _group_prescriptions(phrase_df: pd.DataFrame) -> dict[str, dict[str, list[str]]]:
    prescriptions: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"diagnose": [], "drugname": [], "quantity": [], "usage": []}
    )

    for row in phrase_df.to_dict("records"):
        label = str(row["label"])
        if label not in prescriptions[str(row["prescription_id"])]:
            continue

        text = str(row["merged_text"]).strip()
        if text:
            prescriptions[str(row["prescription_id"])][label].append(text)

    return prescriptions


def _drug_info_json(drug_info: DrugInfo | None) -> str:
    if drug_info is None:
        return ""
    return json.dumps(asdict(drug_info), ensure_ascii=False)


def _match_or_enrich(
    drug_raw: str,
    kb: DrugKnowledgeBase,
    mapper: MedicineMapper | None,
    enrich: bool,
) -> tuple[DrugInfo | None, str, float, bool]:
    drug_info, name_match, confidence = kb.match_drug(drug_raw)
    if drug_info is not None:
        return drug_info, drug_info.name_generic, float(confidence), False

    normalized_raw = normalize_drug_name(drug_raw)
    if enrich and mapper is not None and normalized_raw:
        try:
            enriched = mapper.enrich_drug_with_llm(normalized_raw)
            if enriched is not None:
                kb.add_drug(enriched, aliases=[drug_raw, normalized_raw])
                drug_info, name_match, confidence = kb.match_drug(drug_raw)
                if drug_info is not None:
                    return drug_info, drug_info.name_generic, float(confidence), False
        except Exception as exc:
            print(f"Warning: enrichment failed for {drug_raw!r}: {type(exc).__name__}: {exc}")

    return None, "", 0.0, True


def build_synthetic_dataset(input_path: Path, output_path: Path, enrich: bool = False) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV does not exist: {input_path}")

    phrase_df = load_phrase_rows(input_path)
    prescriptions = _group_prescriptions(phrase_df)
    kb = DrugKnowledgeBase(db_path="vaipe_drugs.db")
    mapper = MedicineMapper(db_path="vaipe_drugs.db", auto_enrich=False) if enrich else None

    output_rows: list[dict[str, Any]] = []
    unmatched_names: Counter[str] = Counter()
    skipped_prescriptions = 0

    for prescription_id, fields in sorted(prescriptions.items()):
        diagnoses = fields["diagnose"]
        drugs = fields["drugname"]
        if not diagnoses or not drugs:
            skipped_prescriptions += 1
            continue

        diagnoses_text = "; ".join(diagnoses)
        quantity_text = "; ".join(fields["quantity"])
        usage_text = "; ".join(fields["usage"])

        try:
            for drug_raw in drugs:
                drug_info, normalized_name, confidence, needs_enrichment = _match_or_enrich(
                    drug_raw=drug_raw,
                    kb=kb,
                    mapper=mapper,
                    enrich=enrich,
                )
                if needs_enrichment:
                    normalized_for_count = normalize_drug_name(drug_raw)
                    if normalized_for_count:
                        unmatched_names[normalized_for_count] += 1

                output_rows.append(
                    {
                        "prescription_id": prescription_id,
                        "drug_raw": drug_raw,
                        "drug_normalized": normalized_name,
                        "diagnoses": diagnoses_text,
                        "quantity": quantity_text,
                        "usage": usage_text,
                        "match_confidence": round(float(confidence), 2),
                        "needs_enrichment": bool(needs_enrichment),
                        "kb_info": _drug_info_json(drug_info),
                    }
                )
        except Exception as exc:
            skipped_prescriptions += 1
            print(f"Warning: skipped prescription {prescription_id}: {type(exc).__name__}: {exc}")

    output_df = pd.DataFrame(
        output_rows,
        columns=[
            "prescription_id",
            "drug_raw",
            "drug_normalized",
            "diagnoses",
            "quantity",
            "usage",
            "match_confidence",
            "needs_enrichment",
            "kb_info",
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    matched_count = int((~output_df["needs_enrichment"]).sum()) if not output_df.empty else 0
    unmatched_count = int(output_df["needs_enrichment"].sum()) if not output_df.empty else 0
    processed_prescriptions = len(prescriptions) - skipped_prescriptions

    print(f"Total prescriptions processed: {processed_prescriptions}")
    print(f"Total (prescription, drug) pairs found: {len(output_df)}")
    print(f"Matched drugs: {matched_count}")
    print(f"Unmatched drugs: {unmatched_count}")
    print("Top 10 unmatched drug names by frequency:")
    for rank, (drug_name, count) in enumerate(unmatched_names.most_common(10), start=1):
        print(f"{rank:>2}. {drug_name:<45} {count}")

    return output_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synthetic drug-illness rows from VAIPE-P NER outputs.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input NER CSV path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output synthetic CSV path.")
    parser.add_argument("--enrich", action="store_true", help="Call LLM enrichment for missing drugs.")
    args = parser.parse_args()

    build_synthetic_dataset(input_path=args.input, output_path=args.output, enrich=args.enrich)
    print(f"Saved synthetic dataset: {args.output}")


if __name__ == "__main__":
    main()
