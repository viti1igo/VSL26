"""Translate only safe matched KB drugs needed by project prescription datasets."""

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd

from count_drugs import normalize_drug_name
from medicine_mapper import DrugKnowledgeBase, MedicineMapper

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_TRAIN_CSV = REPO_ROOT / "results" / "drug_illness_synthetic.csv"
DEFAULT_REPORT = REPO_ROOT / "results" / "needed_drugs_translation_status.csv"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def clean_candidate_name(text: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(text))
    return normalize_drug_name(text)


def _prefix_plausible(candidate: str, target: str, prefix_len: int = 5) -> bool:
    candidate_compact = re.sub(r"[^a-z0-9à-ỹ]+", "", candidate.lower())
    target_compact = re.sub(r"[^a-z0-9à-ỹ]+", "", target.lower())
    if len(candidate_compact) < prefix_len or len(target_compact) < prefix_len:
        return candidate_compact == target_compact
    return candidate_compact[:prefix_len] == target_compact[:prefix_len]


def _is_nonempty(value: Any) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def extract_candidates_from_csv(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"CSV does not exist: {path}")

    df = pd.read_csv(path, encoding="utf-8-sig")
    candidates: set[str] = set()

    if {"drug_raw", "drug_normalized"}.issubset(df.columns):
        for row in df.to_dict("records"):
            if _is_nonempty(row.get("drug_normalized")):
                name = clean_candidate_name(row["drug_normalized"])
            else:
                name = clean_candidate_name(row.get("drug_raw", ""))
            if name:
                candidates.add(name)
        return candidates

    if {"label", "merged_text"}.issubset(df.columns):
        drug_rows = df[df["label"].astype(str) == "drugname"]
        for value in drug_rows["merged_text"].dropna():
            name = clean_candidate_name(value)
            if name:
                candidates.add(name)
        return candidates

    if {"predicted_label", "text"}.issubset(df.columns):
        drug_rows = df[df["predicted_label"].astype(str) == "drugname"]
        for value in drug_rows["text"].dropna():
            name = clean_candidate_name(value)
            if name:
                candidates.add(name)
        return candidates

    raise ValueError(
        f"Unsupported CSV format for {path}. Expected drug_raw/drug_normalized, label/merged_text, or predicted_label/text."
    )


def extract_candidates(train_csv: Path, test_csv: Path | None) -> set[str]:
    candidates = extract_candidates_from_csv(train_csv)
    if test_csv is not None:
        candidates.update(extract_candidates_from_csv(test_csv))
    return candidates


def _load_kb_candidates(kb: DrugKnowledgeBase) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    with kb._connect() as conn:
        drug_rows = conn.execute(
            "SELECT drug_id, name_generic, name_vn, atc_code FROM drugs"
        ).fetchall()
        alias_rows = conn.execute(
            """
            SELECT a.alias, d.drug_id, d.name_generic, d.name_vn, d.atc_code
            FROM drug_aliases a
            JOIN drugs d ON d.drug_id = a.drug_id
            """
        ).fetchall()

    seen: set[tuple[str, str, str]] = set()
    for drug_id, name_generic, name_vn, atc_code in drug_rows:
        for kind, value in [("generic", name_generic), ("name_vn", name_vn)]:
            normalized = normalize_drug_name(str(value or ""))
            if normalized:
                key = (str(drug_id), kind, normalized)
                if key not in seen:
                    seen.add(key)
                    candidates.append(
                        {
                            "drug_id": str(drug_id),
                            "name_generic": str(name_generic or ""),
                            "name_vn": str(name_vn or ""),
                            "atc_code": str(atc_code or ""),
                            "match_text": normalized,
                            "match_kind": kind,
                        }
                    )

    for alias, drug_id, name_generic, name_vn, atc_code in alias_rows:
        normalized = normalize_drug_name(str(alias or ""))
        key = (str(drug_id), "alias", normalized)
        if normalized and key not in seen:
            seen.add(key)
            candidates.append(
                {
                    "drug_id": str(drug_id),
                    "name_generic": str(name_generic or ""),
                    "name_vn": str(name_vn or ""),
                    "atc_code": str(atc_code or ""),
                    "match_text": normalized,
                    "match_kind": "alias",
                }
            )

    return candidates


def strict_match_kb(candidate: str, kb_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_candidate = clean_candidate_name(candidate)
    if not normalized_candidate:
        return None

    exact_matches = [
        row for row in kb_candidates
        if row["match_text"] == normalized_candidate and row["match_kind"] in {"generic", "alias"}
    ]
    if exact_matches:
        row = exact_matches[0].copy()
        row["match_confidence"] = 100.0
        row["match_status_detail"] = f"exact_{row['match_kind']}"
        return row

    best_row = None
    best_score = 0.0
    for row in kb_candidates:
        if fuzz is not None:
            score = float(fuzz.token_set_ratio(normalized_candidate, row["match_text"]))
        else:
            score = 100.0 if normalized_candidate == row["match_text"] else 0.0
        if score > best_score:
            best_score = score
            best_row = row

    if best_row is None:
        return None

    best = best_row.copy()
    best["match_confidence"] = round(best_score, 2)
    best["match_status_detail"] = "fuzzy_best"
    if best_score >= 90.0 and _prefix_plausible(normalized_candidate, str(best["match_text"])):
        return best

    if best_score >= 70.0:
        best["rejected"] = True
        best["candidate_normalized"] = normalized_candidate
        return best

    return None


def _current_vietnamese_name(kb: DrugKnowledgeBase, drug_id: str) -> str:
    with kb._connect() as conn:
        row = conn.execute("SELECT data_json FROM drugs WHERE drug_id = ?", (drug_id,)).fetchone()
    if not row:
        return ""
    data = json.loads(row[0])
    return str(data.get("generic_name_vn") or "").strip()


def _update_vietnamese_name(kb: DrugKnowledgeBase, drug_id: str, vi_name: str) -> None:
    with kb._connect() as conn:
        row = conn.execute("SELECT data_json FROM drugs WHERE drug_id = ?", (drug_id,)).fetchone()
        if not row:
            return
        data = json.loads(row[0])
        data["generic_name_vn"] = vi_name
        data["name_vn"] = vi_name or data.get("name_vn", "")
        conn.execute(
            "UPDATE drugs SET name_vn = ?, data_json = ? WHERE drug_id = ?",
            (data["name_vn"], json.dumps(data, ensure_ascii=False), drug_id),
        )


def analyze_candidates(candidates: set[str], kb: DrugKnowledgeBase) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    kb_candidates = _load_kb_candidates(kb)
    for candidate in sorted(candidates):
        match = strict_match_kb(candidate, kb_candidates)
        rejected = bool(match and match.get("rejected"))
        drug_id = str(match["drug_id"]) if match and not rejected else None
        vi_name = _current_vietnamese_name(kb, drug_id) if drug_id else ""
        if rejected:
            match_status = "rejected_ambiguous_match"
        elif drug_id and vi_name:
            match_status = "already_translated"
        elif drug_id:
            match_status = "matched_untranslated"
        else:
            match_status = "no_kb_match"

        rows.append(
            {
                "candidate_drug": candidate,
                "kb_drug_id": drug_id or "",
                "matched_kb_name": str(match.get("name_generic", "")) if match else "",
                "kb_name_generic": str(match.get("name_generic", "")) if match else "",
                "kb_atc_code": str(match.get("atc_code", "")) if match else "",
                "match_confidence": float(match.get("match_confidence", 0.0)) if match else 0.0,
                "match_status": match_status,
                "match_detail": str(match.get("match_status_detail", "")) if match else "",
                "translated": match_status == "already_translated",
                "generic_name_vn": vi_name,
            }
        )
    return rows


def write_report(rows: list[dict[str, Any]], path: Path = DEFAULT_REPORT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "candidate_drug",
        "kb_drug_id",
        "matched_kb_name",
        "kb_name_generic",
        "kb_atc_code",
        "match_confidence",
        "match_status",
        "match_detail",
        "translated",
        "generic_name_vn",
    ]
    pd.DataFrame(rows, columns=columns).to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
    )


def update_needed_kb(
    train_csv: Path,
    test_csv: Path | None,
    max_translations: int,
    dry_run: bool,
) -> None:
    load_dotenv()
    candidates = extract_candidates(train_csv, test_csv)
    kb = DrugKnowledgeBase(db_path="vaipe_drugs.db")
    mapper = MedicineMapper(db_path="vaipe_drugs.db", auto_enrich=False)
    rows = analyze_candidates(candidates, kb)

    already_translated = sum(1 for row in rows if row["match_status"] == "already_translated")
    needs_rows = [row for row in rows if row["match_status"] == "matched_untranslated"]
    no_match = sum(1 for row in rows if row["match_status"] == "no_kb_match")
    rejected = [row for row in rows if row["match_status"] == "rejected_ambiguous_match"]

    print(f"Total unique candidate drugs: {len(candidates)}")
    print(f"Already translated: {already_translated}")
    print(f"Matched but untranslated: {len(needs_rows)}")
    print(f"No KB match: {no_match}")
    print(f"Rejected ambiguous matches: {len(rejected)}")

    if dry_run:
        print("\nFirst 20 ambiguous/rejected examples:")
        for row in rejected[:20]:
            print(
                f"- {row['candidate_drug']} -> {row['matched_kb_name']} "
                f"({row['match_confidence']:.1f}, {row['match_detail']})"
            )
        print("\nDry run: names that would be translated:")
        for row in needs_rows[:max_translations]:
            print(f"- {row['matched_kb_name']} ({row['kb_atc_code']}) from candidate '{row['candidate_drug']}'")
        print(f"Names skipped because of max_translations: {max(0, len(needs_rows) - max_translations)}")
        write_report(rows)
        print(f"Saved report: {DEFAULT_REPORT}")
        return

    translated_count = 0
    failed_count = 0
    for row in needs_rows[:max_translations]:
        name = row["kb_name_generic"] or row["candidate_drug"]
        atc_code = row["kb_atc_code"]
        try:
            vi_name = mapper.enrich_drug_with_llm(name_en=name, atc_code=atc_code, only_translate=True)
        except Exception as exc:
            failed_count += 1
            row["match_status"] = f"translation_failed:{type(exc).__name__}"
            print(f"Warning: failed to translate {name}: {type(exc).__name__}: {exc}")
            continue

        vi_name = str(vi_name or "").strip()
        if not vi_name:
            failed_count += 1
            row["match_status"] = "translation_failed:empty"
            print(f"Warning: empty translation for {name}")
            continue

        _update_vietnamese_name(kb, row["kb_drug_id"], vi_name)
        row["generic_name_vn"] = vi_name
        row["translated"] = True
        row["match_status"] = "newly_translated"
        translated_count += 1

        suffix = " (no change)" if vi_name.casefold() == str(name).casefold() else ""
        print(f"Translated {name} → {vi_name}{suffix}")

    remaining = len(needs_rows) - translated_count
    skipped_by_limit = max(0, len(needs_rows) - max_translations)
    print("\n=== SUMMARY ===")
    print(f"Total unique candidate drugs: {len(candidates)}")
    print(f"Already translated: {already_translated}")
    print(f"Newly translated: {translated_count}")
    print(f"Translation failures: {failed_count}")
    print(f"Remaining untranslated: {remaining}")
    print(f"Rejected ambiguous matches: {len(rejected)}")
    print(f"Names skipped because of max_translations: {skipped_by_limit}")

    write_report(rows)
    print(f"Saved report: {DEFAULT_REPORT}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate only KB drugs that appear in project prescription datasets.")
    parser.add_argument("--train-csv", type=Path, default=DEFAULT_TRAIN_CSV)
    parser.add_argument("--test-csv", type=Path, default=None)
    parser.add_argument("--max-translations", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    update_needed_kb(
        train_csv=args.train_csv,
        test_csv=args.test_csv,
        max_translations=args.max_translations,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
