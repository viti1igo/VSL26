"""Apply manually approved safe alias mappings from the top-30 review sheet."""

import csv
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from count_drugs import normalize_drug_name


REPO_ROOT = Path(__file__).resolve().parent
PROPOSALS_CSV = REPO_ROOT / "results" / "proposed_aliases_top30.csv"
REVIEW_QUEUE_CSV = REPO_ROOT / "results" / "unresolved_drug_review_queue.csv"
STATUS_CSV = REPO_ROOT / "results" / "needed_drugs_translation_status.csv"
LOG_CSV = REPO_ROOT / "results" / "applied_aliases_top30.csv"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _find_drug(conn: sqlite3.Connection, generic_name: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT drug_id, name_generic
        FROM drugs
        WHERE lower(name_generic) = lower(?)
        ORDER BY drug_id
        LIMIT 1
        """,
        (generic_name,),
    ).fetchone()
    if not row:
        return None
    return str(row[0]), str(row[1])


def _load_variant_aliases() -> dict[str, set[str]]:
    if not REVIEW_QUEUE_CSV.exists():
        return {}

    queue_df = pd.read_csv(REVIEW_QUEUE_CSV, encoding="utf-8-sig")
    variants: dict[str, set[str]] = {}
    for row in queue_df.to_dict("records"):
        candidate = _text(row.get("candidate_drug"))
        if not candidate:
            continue

        names = {candidate}
        raw_forms = _text(row.get("example_raw_forms"))
        if raw_forms:
            names.update(part.strip() for part in raw_forms.split("|") if part.strip())

        variants[candidate] = {
            normalized
            for normalized in (normalize_drug_name(name) for name in names)
            if normalized
        }
    return variants


def _load_status_variants() -> dict[str, set[str]]:
    if not STATUS_CSV.exists():
        return {}

    from prepare_unresolved_drug_review import clean_candidate_name

    status_df = pd.read_csv(STATUS_CSV, encoding="utf-8-sig")
    variants: dict[str, set[str]] = {}
    for value in status_df.get("candidate_drug", pd.Series(dtype=str)).dropna():
        raw_name = str(value).strip()
        candidate = clean_candidate_name(raw_name)
        alias = normalize_drug_name(raw_name)
        if candidate and alias:
            variants.setdefault(candidate, set()).add(alias)
    return variants


def apply_aliases() -> pd.DataFrame:
    proposals = pd.read_csv(PROPOSALS_CSV, encoding="utf-8-sig")
    variant_aliases = _load_variant_aliases()
    status_variants = _load_status_variants()
    logs: list[dict[str, str]] = []

    with sqlite3.connect(DB_PATH) as conn:
        for row in proposals.to_dict("records"):
            candidate = _text(row.get("candidate_drug"))
            generic_name = _text(row.get("proposed_generic_name"))
            apply_alias = _text(row.get("apply_alias")).lower()
            confidence = _text(row.get("confidence_note")).lower()

            log_row = {
                "candidate_drug": candidate,
                "proposed_generic_name": generic_name,
                "applied": "no",
                "reason_if_skipped": "",
            }

            if apply_alias != "yes":
                log_row["reason_if_skipped"] = f"apply_alias is '{apply_alias or 'blank'}'"
                logs.append(log_row)
                continue

            if confidence == "review":
                log_row["reason_if_skipped"] = "confidence_note is review"
                logs.append(log_row)
                continue

            if not generic_name:
                log_row["reason_if_skipped"] = "proposed_generic_name is empty"
                logs.append(log_row)
                continue

            drug = _find_drug(conn, generic_name)
            if not drug:
                log_row["reason_if_skipped"] = "proposed_generic_name not found in drugs table"
                logs.append(log_row)
                continue

            drug_id, resolved_generic_name = drug
            aliases_to_apply = set(variant_aliases.get(candidate, set()))
            aliases_to_apply.update(status_variants.get(candidate, set()))
            candidate_alias = normalize_drug_name(candidate)
            if candidate_alias:
                aliases_to_apply.add(candidate_alias)

            if not aliases_to_apply:
                log_row["reason_if_skipped"] = "candidate_drug normalizes to empty alias"
                logs.append(log_row)
                continue

            conflicts = []
            for alias in sorted(aliases_to_apply):
                existing = conn.execute(
                    "SELECT drug_id FROM drug_aliases WHERE alias = ?",
                    (alias,),
                ).fetchone()
                if existing and str(existing[0]) != drug_id:
                    conflicts.append(f"{alias}->{existing[0]}")
                    continue

                conn.execute(
                    "INSERT OR REPLACE INTO drug_aliases (alias, drug_id) VALUES (?, ?)",
                    (alias, drug_id),
                )

            log_row["proposed_generic_name"] = resolved_generic_name
            log_row["applied"] = "yes"
            if conflicts:
                log_row["reason_if_skipped"] = "partial conflicts: " + "; ".join(conflicts)
            logs.append(log_row)

    return pd.DataFrame(
        logs,
        columns=[
            "candidate_drug",
            "proposed_generic_name",
            "applied",
            "reason_if_skipped",
        ],
    )


def main() -> None:
    log_df = apply_aliases()
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(LOG_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    print(f"Saved alias application log: {LOG_CSV}")
    print(f"Applied aliases: {int((log_df['applied'] == 'yes').sum())}")
    print(f"Skipped aliases: {int((log_df['applied'] != 'yes').sum())}")


if __name__ == "__main__":
    main()
