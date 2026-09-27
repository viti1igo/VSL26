"""Find VAIPE-P prescriptions eligible for the four-drug pilot evaluation subset."""

import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from count_drugs import DOSAGE_RE, find_vaipe_dataset

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_CSV = REPO_ROOT / "results" / "pilot_eligible_prescriptions.csv"
SUMMARY_MD = REPO_ROOT / "results" / "pilot_subset_summary.md"
LEADING_ENUM_RE = re.compile(r"^[\(\s]*\d+\s*[\)\.\-:]?[\s]*")

TARGET_ALIASES = {
    "amlodipine": ["amlodipine", "amlodipin", "kavasdin", "pamlonor", "amcardia", "cardilopin", "norvasc"],
    "enalapril": ["enalapril", "ebitac", "renapril", "renitec", "ednyt"],
    "amoxicillin": ["amoxicillin", "amoxicilin", "fabamox", "ospamox", "flemoxin", "amoxil"],
    "paracetamol": [
        "paracetamol",
        "panactol",
        "partamol",
        "mypara",
        "hapacol",
        "panadol",
        "efferalgan",
        "tydol",
        "stacetam",
        "mezafen",
    ],
}

CANONICAL_LABELS = {
    "amlodipine": "Amlodipine",
    "enalapril": "Enalapril",
    "amoxicillin": "Amoxicillin",
    "paracetamol": "Paracetamol",
}


def normalize_for_pilot(text: str) -> str:
    text = LEADING_ENUM_RE.sub(" ", str(text))
    text = DOSAGE_RE.sub(" ", text)
    text = re.sub(r"[^\w\sÀ-ỹ-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def first_5_consistent(left: str, right: str) -> bool:
    left = re.sub(r"[^a-z0-9à-ỹ]+", "", left.lower())
    right = re.sub(r"[^a-z0-9à-ỹ]+", "", right.lower())
    if len(left) < 5 or len(right) < 5:
        return left == right
    return left[:5] == right[:5]


def token_set_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if fuzz is not None:
        return float(fuzz.token_set_ratio(left, right))

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return 100.0 * len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def build_alias_index() -> dict[str, str]:
    alias_index: dict[str, str] = {}
    for canonical, aliases in TARGET_ALIASES.items():
        for alias in aliases:
            normalized_alias = normalize_for_pilot(alias)
            alias_index[normalized_alias] = canonical
    return alias_index


def match_target_drug(normalized_name: str, alias_index: dict[str, str]) -> tuple[str, str, float]:
    if not normalized_name:
        return "UNKNOWN", "", 0.0

    if normalized_name in alias_index:
        return alias_index[normalized_name], normalized_name, 100.0

    best_canonical = "UNKNOWN"
    best_alias = ""
    best_score = 0.0
    for alias, canonical in alias_index.items():
        score = token_set_ratio(normalized_name, alias)
        if score > best_score:
            best_canonical = canonical
            best_alias = alias
            best_score = score

    if best_score >= 85.0 and first_5_consistent(normalized_name, best_alias):
        return best_canonical, best_alias, best_score

    return "UNKNOWN", best_alias, best_score


def load_annotation(annotation_path: Path) -> Any:
    return json.loads(annotation_path.read_text(encoding="utf-8"))


def extract_drug_entities(annotation: Any) -> list[str]:
    if isinstance(annotation, list):
        drugs: list[str] = []
        current_tokens: list[str] = []
        for item in annotation:
            label = item.get("label") if isinstance(item, dict) else None
            text = str(item.get("text", "")).strip() if isinstance(item, dict) else ""
            if label == "drugname" and text:
                current_tokens.append(text)
            elif current_tokens:
                drugs.append(" ".join(current_tokens))
                current_tokens = []
        if current_tokens:
            drugs.append(" ".join(current_tokens))
        return drugs

    if isinstance(annotation, dict):
        words = annotation.get("words") or annotation.get("tokens") or []
        labels = annotation.get("ner_tags") or annotation.get("labels") or []
        drugs = []
        current_tokens = []
        for word, label in zip(words, labels):
            text = str(word).strip()
            if label == "drugname" and text:
                current_tokens.append(text)
            elif current_tokens:
                drugs.append(" ".join(current_tokens))
                current_tokens = []
        if current_tokens:
            drugs.append(" ".join(current_tokens))
        return drugs

    return []


def has_diagnosis(annotation: Any) -> bool:
    if isinstance(annotation, list):
        return any(
            isinstance(item, dict)
            and item.get("label") == "diagnose"
            and str(item.get("text", "")).strip()
            for item in annotation
        )

    if isinstance(annotation, dict):
        words = annotation.get("words") or annotation.get("tokens") or []
        labels = annotation.get("ner_tags") or annotation.get("labels") or []
        return any(label == "diagnose" and str(word).strip() for word, label in zip(words, labels))

    return False


def categorize(matches: list[str]) -> str:
    matched_count = sum(1 for match in matches if match != "UNKNOWN")
    if matches and matched_count == len(matches):
        return "PILOT_ELIGIBLE"
    if matched_count > 0:
        return "PARTIAL_MATCH"
    return "NO_MATCH"


def analyze_dataset(label_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    alias_index = build_alias_index()
    all_rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []

    for annotation_path in sorted(label_dir.glob("*.json")):
        annotation = load_annotation(annotation_path)
        raw_drugs = extract_drug_entities(annotation)
        normalized_drugs = [normalize_for_pilot(drug) for drug in raw_drugs]
        match_details = [match_target_drug(name, alias_index) for name in normalized_drugs]
        canonicals = [canonical for canonical, _alias, _score in match_details]
        category = categorize(canonicals)
        matched_canonicals = [
            canonical for canonical in canonicals if canonical != "UNKNOWN"
        ]

        row = {
            "prescription_id": annotation_path.stem,
            "category": category,
            "matched_drug_canonicals": matched_canonicals,
            "matched_drug_canonicals_unique": sorted(set(matched_canonicals)),
            "num_drugs": len(raw_drugs),
            "num_target_drugs": len(matched_canonicals),
            "has_diagnosis": has_diagnosis(annotation),
            "all_drugs_extracted": raw_drugs,
            "normalized_drugs": normalized_drugs,
            "match_details": match_details,
        }
        all_rows.append(row)
        if category == "PILOT_ELIGIBLE":
            eligible_rows.append(row)

    return all_rows, eligible_rows


def write_eligible_csv(rows: list[dict[str, Any]]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    csv_rows = []
    for row in rows:
        csv_rows.append(
            {
                "prescription_id": row["prescription_id"],
                "matched_drug_canonicals": "; ".join(row["matched_drug_canonicals_unique"]),
                "matched_drug_canonicals_sequence": "; ".join(row["matched_drug_canonicals"]),
                "num_drugs": row["num_drugs"],
                "num_target_drugs": row["num_target_drugs"],
                "has_diagnosis": row["has_diagnosis"],
                "all_drugs_extracted": " | ".join(row["all_drugs_extracted"]),
                "normalized_drugs": " | ".join(row["normalized_drugs"]),
            }
        )

    pd.DataFrame(csv_rows).to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
    )


def percent(count: int, total: int) -> str:
    return f"{count / total:.1%}" if total else "0.0%"


def combination_label(canonicals: list[str]) -> str:
    unique = sorted(set(canonicals))
    return " + ".join(CANONICAL_LABELS[canonical] for canonical in unique)


def build_summary(all_rows: list[dict[str, Any]], eligible_rows: list[dict[str, Any]]) -> str:
    total = len(all_rows)
    category_counts = Counter(row["category"] for row in all_rows)
    target_count_distribution = Counter(row["num_target_drugs"] for row in eligible_rows)
    combination_counts = Counter(combination_label(row["matched_drug_canonicals"]) for row in eligible_rows)

    random.seed(26)
    examples_by_count: dict[int, list[str]] = {}
    grouped_ids: dict[int, list[str]] = defaultdict(list)
    for row in eligible_rows:
        grouped_ids[row["num_target_drugs"]].append(row["prescription_id"])
    for count, ids in sorted(grouped_ids.items()):
        ids = sorted(ids)
        examples_by_count[count] = random.sample(ids, min(5, len(ids)))

    lines = [
        "# Pilot Subset Summary",
        "",
        f"- Total prescriptions: {total}",
        f"- PILOT_ELIGIBLE: {category_counts['PILOT_ELIGIBLE']} ({percent(category_counts['PILOT_ELIGIBLE'], total)})",
        f"- PARTIAL_MATCH: {category_counts['PARTIAL_MATCH']} ({percent(category_counts['PARTIAL_MATCH'], total)})",
        f"- NO_MATCH: {category_counts['NO_MATCH']} ({percent(category_counts['NO_MATCH'], total)})",
        "",
        "## Target-Drug Count Distribution",
        "",
        "| target drug count | prescriptions |",
        "|---:|---:|",
    ]
    for count in range(1, 5):
        lines.append(f"| {count} | {target_count_distribution.get(count, 0)} |")

    overflow_count = sum(
        value for key, value in target_count_distribution.items() if key > 4
    )
    if overflow_count:
        lines.append(f"| >4 | {overflow_count} |")

    lines.extend(
        [
            "",
            "## Most Common Target Combinations",
            "",
            "| combination | prescriptions |",
            "|---|---:|",
        ]
    )
    for combination, count in combination_counts.most_common(30):
        lines.append(f"| {combination} | {count} |")

    lines.extend(
        [
            "",
            "## Random PILOT_ELIGIBLE Examples by Target-Drug Count",
            "",
            "| target drug count | prescription_ids |",
            "|---:|---|",
        ]
    )
    for count in range(1, 5):
        examples = examples_by_count.get(count, [])
        lines.append(f"| {count} | {', '.join(examples) if examples else '(none)'} |")

    if any(key > 4 for key in examples_by_count):
        examples = []
        for count, ids in examples_by_count.items():
            if count > 4:
                examples.extend(ids)
        lines.append(f"| >4 | {', '.join(examples[:5]) if examples else '(none)'} |")

    lines.extend(
        [
            "",
            "## Output Files",
            "",
            f"- Eligible CSV: `{OUTPUT_CSV}`",
            f"- Summary: `{SUMMARY_MD}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    label_dir = find_vaipe_dataset()
    if label_dir is None:
        raise SystemExit("Could not locate VAIPE-P label directory.")

    all_rows, eligible_rows = analyze_dataset(label_dir)
    write_eligible_csv(eligible_rows)

    summary = build_summary(all_rows, eligible_rows)
    SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD.write_text(summary + "\n", encoding="utf-8")

    print(summary)


if __name__ == "__main__":
    main()
