"""Build the final human-review action sheet for unresolved VAIPE-P drug names."""

import csv
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


REPO_ROOT = Path(__file__).resolve().parent
QUEUE_CSV = REPO_ROOT / "results" / "unresolved_drug_review_queue.csv"
LLM_CSV = REPO_ROOT / "results" / "llm_unresolved_drug_suggestions_top40.csv"
OUTPUT_CSV = REPO_ROOT / "results" / "final_drug_review_actions.csv"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"

TRADITIONAL_MARKERS = (
    "hoạt huyết",
    "dưỡng não",
    "đinh lăng",
    "kim tiền",
    "bổ huyết",
    "bố huyết",
    "thanh nhiệt",
    "dưỡng tâm",
    "bạch quả",
)

CATEGORY_ORDER = {
    "safe_alias_to_existing_kb": 0,
    "safe_new_manual_entry": 1,
    "traditional_medicine_manual_entry": 2,
    "ocr_cleanup_or_drop": 3,
    "needs_human_review": 4,
}

OUTPUT_COLUMNS = [
    "drug_name_extracted",
    "frequency_in_dataset",
    "category",
    "llm_suggested_kb_match",
    "llm_suggested_atc_code",
    "fuzzy_score_to_llm_suggestion",
    "first_5_char_match",
    "human_decision",
    "notes",
]


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9à-ỹ]+", " ", _text(value).lower()).strip()


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9à-ỹ]+", "", _text(value).lower())


def _yes(value: Any) -> bool:
    return _text(value).lower() in {"yes", "true", "1", "có", "co"}


def _confidence_level(value: Any) -> str:
    text = _text(value).lower()
    if text.startswith("high"):
        return "high"
    if text.startswith("medium"):
        return "medium"
    if text.startswith("low"):
        return "low"
    return ""


def _llm_uncertain(row: pd.Series) -> bool:
    confidence_note = _text(row.get("confidence_note")).lower()
    return (
        _yes(row.get("human_review_required"))
        or _confidence_level(confidence_note) == "low"
        or "uncertain" in confidence_note
        or "không đủ" in confidence_note
        or "cần xác minh" in confidence_note
    )


def _token_set_ratio(left: str, right: str) -> float:
    left_norm = _norm(left)
    right_norm = _norm(right)
    if not left_norm or not right_norm:
        return 0.0
    if fuzz is not None:
        return float(fuzz.token_set_ratio(left_norm, right_norm))
    return SequenceMatcher(None, left_norm, right_norm).ratio() * 100.0


def _edit_distance(left: str, right: str) -> int:
    left = _compact(left)
    right = _compact(right)
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _first_5_match(left: str, right: str) -> bool:
    left_compact = _compact(left)
    right_compact = _compact(right)
    if len(left_compact) < 5 or len(right_compact) < 5:
        return left_compact == right_compact
    return left_compact[:5] == right_compact[:5]


def _only_digits_or_punctuation(value: str) -> bool:
    text = _text(value)
    return bool(text) and not re.search(r"[A-Za-zÀ-ỹ]", text)


def _llm_category(row: pd.Series) -> str:
    if _yes(row.get("likely_is_ocr_error")):
        return "ocr_error"
    if _yes(row.get("likely_is_traditional_medicine")):
        return "traditional_medicine"
    if _yes(row.get("likely_is_alias_of_existing_drug")):
        return "alias_of_existing_drug"
    return "new_generic_drug_needed"


def _is_single_inn(name: str) -> bool:
    normalized = _norm(name)
    if not normalized:
        return False
    compound_markers = [" + ", " and ", ";", "/", ",", " phối hợp ", " combination", " combinations"]
    lowered = f" {name.lower()} "
    if any(marker in lowered for marker in compound_markers):
        return False
    return True


def _salt_stripped_names(name: str) -> list[str]:
    base = _norm(name)
    variants = [base]
    salt_words = [
        "hydrochloride",
        "hydroclorid",
        "hydrochlorothiazide",
        "hydroclorothiazid",
        "pivoxil",
        "medoxomil",
    ]
    for salt in salt_words:
        stripped = re.sub(rf"\b{salt}\b", " ", base)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if stripped and stripped not in variants:
            variants.append(stripped)
    return variants


def load_reference_maps() -> tuple[dict[str, tuple[str, str]], dict[str, list[str]]]:
    with sqlite3.connect(DB_PATH) as conn:
        drug_rows = conn.execute("SELECT name_generic, atc_code FROM drugs").fetchall()
        atc_rows = conn.execute("SELECT atc_name, atc_code FROM who_atc_ddd").fetchall()

    kb_map = {
        _norm(name): (_text(name), _text(atc_code))
        for name, atc_code in drug_rows
        if _norm(name)
    }
    atc_map: dict[str, list[str]] = {}
    for name, atc_code in atc_rows:
        key = _norm(name)
        if key:
            atc_map.setdefault(key, []).append(_text(atc_code))
    return kb_map, atc_map


def resolve_kb_match(name: str, kb_map: dict[str, tuple[str, str]]) -> tuple[str, str]:
    for variant in _salt_stripped_names(name):
        if variant in kb_map:
            return kb_map[variant]
    return "", ""


def resolve_atc_code(name: str, kb_map: dict[str, tuple[str, str]], atc_map: dict[str, list[str]]) -> str:
    kb_name, kb_atc = resolve_kb_match(name, kb_map)
    if kb_name and kb_atc:
        return kb_atc

    for variant in _salt_stripped_names(name):
        codes = atc_map.get(variant)
        if codes:
            return ";".join(sorted(set(codes))[:5])
    return ""


def classify(row: pd.Series, kb_map: dict[str, tuple[str, str]], atc_map: dict[str, list[str]]) -> dict[str, Any]:
    drug_name = _text(row.get("candidate_drug"))
    frequency = int(row.get("frequency_in_synthetic_dataset", 0) or 0)
    likely_generic = _text(row.get("likely_generic_name"))
    explicit_target = _text(row.get("existing_kb_target_if_alias"))
    llm_category = _llm_category(row)
    confidence = _confidence_level(row.get("confidence_note"))
    llm_uncertain = _llm_uncertain(row)
    match_status = _text(row.get("match_status"))

    candidate_canonical = explicit_target or likely_generic
    kb_match, kb_atc = resolve_kb_match(candidate_canonical, kb_map)
    suggested_atc = resolve_atc_code(candidate_canonical, kb_map, atc_map)
    fuzzy_score = round(_token_set_ratio(drug_name, kb_match or candidate_canonical), 2)
    first_5_match = _first_5_match(drug_name, kb_match or candidate_canonical)

    notes: list[str] = []
    category = "needs_human_review"

    # RULE 1: traditional medicine by extracted name, before trusting LLM.
    if any(marker in drug_name.lower() for marker in TRADITIONAL_MARKERS):
        category = "traditional_medicine_manual_entry"
        notes.append("RULE 1: extracted name contains traditional-medicine marker; LLM suggestion skipped.")

    # RULE 2: OCR cleanup/drop.
    elif len(_compact(drug_name)) < 4 or _only_digits_or_punctuation(drug_name):
        category = "ocr_cleanup_or_drop"
        notes.append("RULE 2: extracted name is too short or contains only digits/punctuation.")
    elif llm_category == "ocr_error" and likely_generic and _edit_distance(drug_name, likely_generic) < 3:
        category = "ocr_cleanup_or_drop"
        notes.append("RULE 2: LLM category is ocr_error and correction is within edit distance < 3.")

    # RULE 3: safe alias only if LLM says alias and strict string checks pass.
    elif (
        llm_category == "alias_of_existing_drug"
        and kb_match
        and first_5_match
        and fuzzy_score >= 85.0
        and not llm_uncertain
    ):
        category = "safe_alias_to_existing_kb"
        notes.append("RULE 3: LLM says alias, KB target exists, first-5 chars match, and fuzzy score >= 85.")

    # RULE 4: safe new manual entry only for single-ingredient INN with WHO ATC evidence.
    elif (
        llm_category == "new_generic_drug_needed"
        and suggested_atc
        and _is_single_inn(likely_generic)
        and not llm_uncertain
        and match_status != "rejected_ambiguous_match"
    ):
        category = "safe_new_manual_entry"
        notes.append("RULE 4: LLM says new generic, suggested ATC exists in WHO/KB, and suggestion is single-ingredient.")

    # RULE 5: everything else.
    else:
        category = "needs_human_review"
        if match_status == "rejected_ambiguous_match":
            notes.append("RULE 5: rejected_ambiguous_match must remain human review.")
        elif not suggested_atc:
            notes.append("RULE 5: no clear ATC code found for LLM suggestion.")
        elif not _is_single_inn(likely_generic):
            notes.append("RULE 5: multi-compound or non-single-INN suggestion.")
        elif confidence == "low" or llm_uncertain:
            notes.append("RULE 5: low or uncertain LLM confidence.")
        else:
            notes.append("RULE 5: strict alias/new-entry requirements not met.")

    if _yes(row.get("human_review_required")):
        notes.append("LLM set human_review_required=yes.")
    if likely_generic:
        notes.append(f"LLM suggested generic: {likely_generic}.")
    if kb_match:
        notes.append(f"KB exact/salt-stripped match: {kb_match}.")

    return {
        "drug_name_extracted": drug_name,
        "frequency_in_dataset": frequency,
        "category": category,
        "llm_suggested_kb_match": kb_match,
        "llm_suggested_atc_code": suggested_atc,
        "fuzzy_score_to_llm_suggestion": fuzzy_score,
        "first_5_char_match": bool(first_5_match),
        "human_decision": "",
        "notes": " ".join(notes),
    }


def build_action_sheet() -> pd.DataFrame:
    queue_df = pd.read_csv(QUEUE_CSV, encoding="utf-8-sig")
    llm_df = pd.read_csv(LLM_CSV, encoding="utf-8-sig")
    merged = queue_df.merge(llm_df, on="candidate_drug", how="left")
    kb_map, atc_map = load_reference_maps()

    rows = [classify(pd.Series(row), kb_map, atc_map) for row in merged.to_dict("records")]
    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    result["_category_order"] = result["category"].map(CATEGORY_ORDER).fillna(99)
    result = result.sort_values(
        ["_category_order", "frequency_in_dataset", "drug_name_extracted"],
        ascending=[True, False, True],
    ).drop(columns=["_category_order"])
    return result


def print_top10(df: pd.DataFrame) -> None:
    top = df.sort_values(["frequency_in_dataset", "drug_name_extracted"], ascending=[False, True]).head(10)
    print("\nTop 10 most frequent unresolved drugs:")
    print("drug_name_extracted".ljust(34) + " | " + "freq".rjust(5) + " | category")
    print("-" * 34 + "-|-" + "-" * 5 + "-|-" + "-" * 34)
    for row in top.itertuples(index=False):
        print(f"{row.drug_name_extracted[:34].ljust(34)} | {str(row.frequency_in_dataset).rjust(5)} | {row.category}")


def main() -> None:
    action_df = build_action_sheet()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    action_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    print(f"Saved final action sheet: {OUTPUT_CSV}")
    print("\nCount per category:")
    counts = action_df["category"].value_counts()
    for category in CATEGORY_ORDER:
        print(f"- {category}: {int(counts.get(category, 0))}")
    print_top10(action_df)


if __name__ == "__main__":
    main()
