"""Prepare a review queue for unresolved drug names from synthetic dataset outputs."""

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

from count_drugs import normalize_drug_name


REPO_ROOT = Path(__file__).resolve().parent
STATUS_CSV = REPO_ROOT / "results" / "needed_drugs_translation_status.csv"
SYNTHETIC_CSV = REPO_ROOT / "results" / "drug_illness_synthetic.csv"
OUTPUT_CSV = REPO_ROOT / "results" / "unresolved_drug_review_queue.csv"
UNRESOLVED_STATUSES = {"no_kb_match", "rejected_ambiguous_match"}
TRADITIONAL_TERMS = {
    "hoạt huyết",
    "dưỡng não",
    "đinh lăng",
    "bạch quả",
    "kim tiền thảo",
    "râu ngô",
    "bổ gan",
    "bố gan",
    "bố huyết",
    "thanh nhiệt",
    "tiêu độc",
    "dưỡng tâm",
    "an thần",
}
FORMULATION_WORD_RE = re.compile(
    r"\b(?:tab|tabs|tablet|tablets|capsule|capsules|cap|caps|film|coated|mr|xr|sr|cr|od)\b",
    re.IGNORECASE,
)
STRENGTH_TOKEN_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|ml|mcg|µg|ui|iu)\b",
    re.IGNORECASE,
)


def clean_candidate_name(text: Any) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(text))
    text = normalize_drug_name(text)
    text = re.sub(r"[-_/]+", " ", text)
    text = STRENGTH_TOKEN_RE.sub(" ", text)
    text = re.sub(r"(?<=[a-zà-ỹ])\d+(?:[.,]\d+)?(?:mg|g|ml|mcg|µg|ui|iu)?\b", " ", text, flags=re.IGNORECASE)
    text = STRENGTH_TOKEN_RE.sub(" ", text)
    text = FORMULATION_WORD_RE.sub(" ", text)
    text = re.sub(r"\b(?:mg|g|ml|mcg|µg|ui|iu)\b(?=\s*$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\b(?=\s*$)", " ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\b(?=\s*$)", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _limited_unique(values: list[Any], limit: int = 5) -> str:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text.lower() == "nan" or text in result:
            continue
        result.append(text)
        if len(result) >= limit:
            break
    return " | ".join(result)


def _looks_traditional(name: str) -> bool:
    return any(term in name for term in TRADITIONAL_TERMS)


def _looks_ocr_cleanup(name: str, raw_forms: list[str]) -> bool:
    compact = re.sub(r"\s+", "", name)
    if len(compact) <= 2:
        return True
    if re.search(r"\d", name) and not re.search(r"[a-zà-ỹ]{4,}", name):
        return True
    if any(re.search(r"(?:smg|sng|8ing|\b0mg\b)", str(raw).lower()) for raw in [name, *raw_forms]):
        return True
    if re.search(r"(.)\1{4,}", name):
        return True
    return False


def _suggest_action(row: pd.Series, raw_forms: list[str], frequency: int) -> str:
    name = str(row["candidate_drug"]).lower()
    status = str(row["match_status"])
    confidence = float(row.get("match_confidence", 0.0) or 0.0)

    if _looks_ocr_cleanup(name, raw_forms):
        return "ocr_cleanup_needed"
    if _looks_traditional(name):
        return "traditional_medicine_manual_entry"
    if status == "rejected_ambiguous_match" and frequency >= 1 and confidence >= 70.0:
        return "add_alias"
    if status == "no_kb_match" and frequency >= 1 and len(name) >= 4 and re.search(r"[a-zà-ỹ]", name):
        return "add_alias"
    if frequency == 0:
        return "uncertain_manual_review"
    if len(name) >= 4 and re.search(r"[a-zà-ỹ]", name):
        return "new_generic_drug_needed"
    return "uncertain_manual_review"


def build_review_queue(status_csv: Path = STATUS_CSV, synthetic_csv: Path = SYNTHETIC_CSV) -> pd.DataFrame:
    status_df = pd.read_csv(status_csv, encoding="utf-8-sig")
    synthetic_df = pd.read_csv(synthetic_csv, encoding="utf-8-sig")

    unresolved = status_df[status_df["match_status"].isin(UNRESOLVED_STATUSES)].copy()
    unresolved["candidate_normalized"] = unresolved["candidate_drug"].map(clean_candidate_name)

    synthetic_df["candidate_normalized"] = synthetic_df.apply(
        lambda row: clean_candidate_name(
            row["drug_normalized"] if pd.notna(row.get("drug_normalized")) and str(row.get("drug_normalized")).strip() else row.get("drug_raw", "")
        ),
        axis=1,
    )

    rows: list[dict[str, Any]] = []
    for candidate_normalized, group in unresolved.groupby("candidate_normalized", sort=True):
        if not candidate_normalized:
            continue

        representative = group.sort_values(
            ["match_status", "match_confidence"],
            ascending=[True, False],
        ).iloc[0]
        examples = synthetic_df[synthetic_df["candidate_normalized"] == candidate_normalized]
        raw_forms = examples["drug_raw"].dropna().astype(str).tolist()
        diagnoses = examples["diagnoses"].dropna().astype(str).tolist()
        prescription_ids = examples["prescription_id"].dropna().astype(str).tolist()
        frequency = int(len(examples))

        rows.append(
            {
                "candidate_drug": candidate_normalized,
                "match_status": representative.get("match_status", ""),
                "matched_kb_name": representative.get("matched_kb_name", ""),
                "match_confidence": representative.get("match_confidence", 0.0),
                "frequency_in_synthetic_dataset": frequency,
                "example_raw_forms": _limited_unique(raw_forms),
                "example_diagnoses": _limited_unique(diagnoses),
                "example_prescription_ids": _limited_unique(prescription_ids),
                "suggested_action": _suggest_action(representative, raw_forms, frequency),
            }
        )

    review_df = pd.DataFrame(
        rows,
        columns=[
            "candidate_drug",
            "match_status",
            "matched_kb_name",
            "match_confidence",
            "frequency_in_synthetic_dataset",
            "example_raw_forms",
            "example_diagnoses",
            "example_prescription_ids",
            "suggested_action",
        ],
    )
    return review_df.sort_values(
        ["frequency_in_synthetic_dataset", "candidate_drug"],
        ascending=[False, True],
    ).reset_index(drop=True)


def main() -> None:
    review_df = build_review_queue()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    review_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    print(f"Saved review queue: {OUTPUT_CSV}")
    print(f"Total unresolved unique drugs: {len(review_df)}")
    print("\nTop 30 unresolved by frequency:")
    for index, row in review_df.head(30).iterrows():
        print(
            f"{index + 1:>2}. {row['candidate_drug']:<45} "
            f"{int(row['frequency_in_synthetic_dataset']):>4}  {row['suggested_action']}"
        )

    action_counts = review_df["suggested_action"].value_counts()
    print("\nAction summary:")
    print(f"Alias candidates: {int(action_counts.get('add_alias', 0))}")
    print(f"Traditional medicines: {int(action_counts.get('traditional_medicine_manual_entry', 0))}")
    print(f"OCR cleanup problems: {int(action_counts.get('ocr_cleanup_needed', 0))}")


if __name__ == "__main__":
    main()
