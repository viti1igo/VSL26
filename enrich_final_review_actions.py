"""Add lookup helpers and reviewer guidance to the final drug review action sheet."""

import csv
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


REPO_ROOT = Path(__file__).resolve().parent
ACTION_CSV = REPO_ROOT / "results" / "final_drug_review_actions.csv"
GUIDE_MD = REPO_ROOT / "results" / "final_drug_review_guide.md"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"

HELPER_COLUMNS = [
    "google_search_url",
    "drugbank_vn_search_url",
    "closest_kb_candidates",
    "suggested_category_hint",
]


def text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def token_set_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if fuzz is not None:
        return float(fuzz.token_set_ratio(left, right))

    left_tokens = set(left.lower().split())
    right_tokens = set(right.lower().split())
    if not left_tokens or not right_tokens:
        return 0.0
    return 100.0 * len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def load_kb_candidates() -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        drug_rows = conn.execute(
            "SELECT drug_id, name_generic, name_vn FROM drugs ORDER BY drug_id"
        ).fetchall()
        alias_rows = conn.execute("SELECT alias, drug_id FROM drug_aliases").fetchall()

    aliases_by_drug_id: dict[str, list[str]] = {}
    for alias, drug_id in alias_rows:
        aliases_by_drug_id.setdefault(text(drug_id), []).append(text(alias))

    candidates = []
    for drug_id, name_generic, name_vn in drug_rows:
        candidate_terms = [
            text(drug_id).replace("_", " "),
            text(name_generic),
            text(name_vn),
            *aliases_by_drug_id.get(text(drug_id), []),
        ]
        candidates.append(
            {
                "drug_id": text(drug_id),
                "terms": [term for term in candidate_terms if term],
            }
        )
    return candidates


def closest_kb_candidates(drug_name: str, kb_candidates: list[dict[str, Any]]) -> str:
    scored = []
    for candidate in kb_candidates:
        score = max(token_set_ratio(drug_name, term) for term in candidate["terms"])
        scored.append((candidate["drug_id"], score))

    scored.sort(key=lambda item: (-item[1], item[0]))
    top3 = scored[:3]
    return " | ".join(f"{drug_id} ({score:.0f})" for drug_id, score in top3)


def search_urls(drug_name: str) -> tuple[str, str]:
    google_query = quote_plus(f"thuốc {drug_name} Việt Nam hoạt chất")
    drugbank_query = quote_plus(drug_name)
    return (
        f"https://www.google.com/search?q={google_query}",
        f"https://drugbank.vn/search?q={drugbank_query}",
    )


def suggested_category_hint(drug_name: str) -> str:
    lower = drug_name.lower()
    compact = "".join(ch for ch in lower if ch.isalnum())

    if compact.endswith("olol") or compact.endswith("ol"):
        return "likely beta-blocker"
    if "cef" in lower or "cil" in lower:
        return "likely antibiotic"
    if "artan" in lower or "pril" in lower:
        return "likely cardiovascular"
    if "statin" in lower:
        return "statin"
    if "prazol" in lower:
        return "PPI"
    if any(marker in lower for marker in ("vitamin", "b1", "b6", "b12")):
        return "vitamin"
    return ""


def enrich_action_csv() -> pd.DataFrame:
    if not ACTION_CSV.exists():
        raise SystemExit(f"Missing input file: {ACTION_CSV}")

    df = pd.read_csv(ACTION_CSV, encoding="utf-8-sig")
    for column in HELPER_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    kb_candidates = load_kb_candidates()
    needs_review = df["category"].astype(str).eq("needs_human_review")

    for idx, row in df[needs_review].iterrows():
        drug_name = text(row.get("drug_name_extracted"))
        google_url, drugbank_url = search_urls(drug_name)
        df.at[idx, "google_search_url"] = google_url
        df.at[idx, "drugbank_vn_search_url"] = drugbank_url
        df.at[idx, "closest_kb_candidates"] = closest_kb_candidates(drug_name, kb_candidates)
        df.at[idx, "suggested_category_hint"] = suggested_category_hint(drug_name)

    df.to_csv(ACTION_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
    return df


def write_guide(needs_review_count: int) -> None:
    GUIDE_MD.parent.mkdir(parents=True, exist_ok=True)
    GUIDE_MD.write_text(
        f"""# Final Drug Review Guide

Use `{ACTION_CSV.name}` as the human approval sheet. Review only rows where `category == needs_human_review` first.

## How to Use the CSV

Fill the `human_decision` column with exactly one of:

- `alias` - the extracted name is a brand name or spelling variant of an existing KB drug.
- `new_entry` - DrugBank.vn or another reliable source shows a clear single active ingredient that should become a new KB entry.
- `drop` - the extracted name is OCR noise or too garbled to recover.
- `traditional` - the extracted name is a traditional/herbal medicine that needs manual entry.
- `still_uncertain` - not enough evidence; keep it for second-pass review.

Use `google_search_url` and `drugbank_vn_search_url` for fast lookup. Use `closest_kb_candidates` only as a hint, not proof.

## Decision Flowchart

1. Does the drug name match any `closest_kb_candidates` with high confidence? Mark `alias`.
2. Does Google or DrugBank.vn show a clear single active ingredient? Mark `new_entry` and note the ingredient in `notes` or an added reviewer note column.
3. Is it obviously a traditional/herbal medicine? Mark `traditional`.
4. Is it garbled beyond recognition? Mark `drop`.
5. Still unclear? Mark `still_uncertain`; it goes into second-pass review.

## Quick Vietnamese Pharmacy References

- `drugbank.vn` - primary Vietnamese drug database.
- `thuocvadongiayphep.vn` - Vietnamese government drug registry.
- `vnras.com` - pharmacy news and drug information.

## Multi-Compound Reminder

For multi-compound drugs such as `telmisartan hydroclorothiazid`, decide based on the primary ingredient if your KB design stores one primary drug per row. If both ingredients matter clinically, mark as separate entries or keep as `still_uncertain` for second-pass review.

## Time Estimate

There are currently {needs_review_count} `needs_human_review` rows. Estimate about 2 minutes per row, or roughly 2.5 hours total.
""",
        encoding="utf-8",
    )


def main() -> None:
    df = enrich_action_csv()
    needs_review_count = int(df["category"].astype(str).eq("needs_human_review").sum())
    write_guide(needs_review_count)

    print(f"Updated CSV in-place: {ACTION_CSV}")
    print(f"Created review guide: {GUIDE_MD}")
    print(f"Rows enriched with lookup helpers: {needs_review_count}")
    print("\nSuggested category hint counts for needs_human_review:")
    hints = df.loc[df["category"].astype(str).eq("needs_human_review"), "suggested_category_hint"]
    for hint, count in hints.value_counts().items():
        label = hint if hint else "(blank)"
        print(f"- {label}: {count}")


if __name__ == "__main__":
    main()
