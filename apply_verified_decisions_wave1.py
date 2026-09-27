"""Apply verified Wave 1 human-review decisions to the local drug knowledge base."""

import json
import re
import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
SOURCE_CSV = REPO_ROOT / "results" / "final_drug_review_actions.csv"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"
BACKUP_PATH = REPO_ROOT / "vaipe_drugs.db.backup_wave1"
REPORT_PATH = REPO_ROOT / "results" / "wave1_apply_report.md"

ELIGIBLE_DECISIONS = {"alias", "traditional", "drop"}

NOTE_SYNONYMS = {
    "acyclovir": "aciclovir",
    "cefpodoxime proxetil": "cefpodoxime",
    "loxoprofen sodium": "loxoprofen",
    "doxazosin mesylate": "doxazosin",
    "alverine citrate": "alverine",
    "alphachymotrypsin": "chymotrypsin",
    "nifedipin": "nifedipine",
    "vitamin c": "ascorbic acid",
}


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9à-ỹ]+", " ", clean_text(value).lower()).strip()


def word_boundary_contains(haystack: str, needle: str) -> bool:
    haystack_norm = f" {normalized(haystack)} "
    needle_norm = normalized(needle)
    if not needle_norm:
        return False
    return f" {needle_norm} " in haystack_norm


def alias_value(value: Any) -> str:
    return clean_text(value).lower()


def slugify(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug or "traditional_drug"


def parse_top_closest_candidate(value: str) -> tuple[str, float]:
    first = clean_text(value).split("|", 1)[0].strip()
    match = re.match(r"(.+?)\s+\((\d+(?:\.\d+)?)\)\s*$", first)
    if not match:
        return "", 0.0
    return match.group(1).strip(), float(match.group(2))


def load_kb_terms(conn: sqlite3.Connection) -> tuple[dict[str, str], list[tuple[str, str]]]:
    rows = conn.execute("SELECT drug_id, name_generic, name_vn FROM drugs").fetchall()
    alias_rows = conn.execute("SELECT alias, drug_id FROM drug_aliases").fetchall()

    exact: dict[str, str] = {}
    terms: list[tuple[str, str]] = []

    for drug_id, name_generic, name_vn in rows:
        for term in {drug_id, name_generic, name_vn}:
            term_clean = clean_text(term)
            term_norm = normalized(term_clean)
            if len(term_norm) >= 4:
                exact[term_norm] = drug_id
                terms.append((term_clean, drug_id))

    for alias, drug_id in alias_rows:
        alias_norm = normalized(alias)
        if len(alias_norm) >= 4:
            exact[alias_norm] = drug_id
            terms.append((clean_text(alias), drug_id))

    terms.sort(key=lambda item: len(normalized(item[0])), reverse=True)
    return exact, terms


def resolve_alias_target(row: pd.Series, conn: sqlite3.Connection) -> tuple[str, str]:
    notes = clean_text(row.get("notes"))
    closest = clean_text(row.get("closest_kb_candidates"))
    exact_terms, searchable_terms = load_kb_terms(conn)

    notes_norm = normalized(notes)
    for source, target_name in NOTE_SYNONYMS.items():
        if word_boundary_contains(notes_norm, source):
            target_id = exact_terms.get(normalized(target_name))
            if target_id:
                return target_id, f"matched note synonym '{source}' -> '{target_name}'"

    for term, drug_id in searchable_terms:
        term_norm = normalized(term)
        if len(term_norm) >= 4 and word_boundary_contains(notes_norm, term_norm):
            return drug_id, f"matched KB term in VERIFIED notes: '{term}'"

    top_candidate, top_score = parse_top_closest_candidate(closest)
    if top_candidate and top_score >= 70:
        target_id = top_candidate
        if conn.execute("SELECT 1 FROM drugs WHERE drug_id = ?", (target_id,)).fetchone():
            return target_id, f"fallback to closest_kb_candidates top entry at score {top_score:.0f}"

    return "", "no KB target found in VERIFIED notes and closest candidate score < 70"


def create_ignore_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drug_ignore_list (
            name TEXT PRIMARY KEY,
            reason TEXT,
            added_at TIMESTAMP
        )
        """
    )


def get_drugs_columns(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        row[1]: {
            "cid": row[0],
            "type": row[2],
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        }
        for row in conn.execute("PRAGMA table_info(drugs)").fetchall()
    }


def rebuild_drugs_table_nullable(conn: sqlite3.Connection) -> list[str]:
    changes: list[str] = []
    columns = get_drugs_columns(conn)
    name_generic_notnull = columns.get("name_generic", {}).get("notnull", False)
    atc_notnull = columns.get("atc_code", {}).get("notnull", False)
    has_is_traditional = "is_traditional" in columns

    if not name_generic_notnull and not atc_notnull and has_is_traditional:
        changes.append("drugs.name_generic already nullable")
        changes.append("drugs.atc_code already nullable")
        changes.append("drugs.is_traditional already exists")
        return changes

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("BEGIN")
    conn.execute(
        """
        CREATE TABLE drugs_new (
            drug_id TEXT PRIMARY KEY,
            name_vn TEXT NOT NULL,
            name_generic TEXT,
            atc_code TEXT,
            data_json TEXT NOT NULL,
            is_traditional BOOLEAN DEFAULT FALSE
        )
        """
    )
    if has_is_traditional:
        conn.execute(
            """
            INSERT INTO drugs_new (drug_id, name_vn, name_generic, atc_code, data_json, is_traditional)
            SELECT drug_id, name_vn, name_generic, atc_code, data_json, is_traditional
            FROM drugs
            """
        )
    else:
        conn.execute(
            """
            INSERT INTO drugs_new (drug_id, name_vn, name_generic, atc_code, data_json, is_traditional)
            SELECT drug_id, name_vn, name_generic, atc_code, data_json, FALSE
            FROM drugs
            """
        )
    conn.execute("DROP TABLE drugs")
    conn.execute("ALTER TABLE drugs_new RENAME TO drugs")
    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys=ON")

    changes.append(
        "drugs.name_generic rebuilt as nullable"
        if name_generic_notnull
        else "drugs.name_generic already nullable"
    )
    changes.append(
        "drugs.atc_code rebuilt as nullable" if atc_notnull else "drugs.atc_code already nullable"
    )
    changes.append(
        "drugs.is_traditional added during rebuild"
        if not has_is_traditional
        else "drugs.is_traditional preserved"
    )
    return changes


def derive_illness(name: str, notes: str) -> tuple[list[str], str]:
    source = f"{name} {notes}".lower()
    illnesses: list[str] = []

    if any(marker in source for marker in ("gan", "liver", "mật", "actiso", "diệp hạ châu")):
        illnesses.extend(["Bổ gan", "Hỗ trợ chức năng gan"])
    if any(marker in source for marker in ("hoạt huyết", "dưỡng não", "bạch quả", "đinh lăng")):
        illnesses.extend(["Hoạt huyết", "Hỗ trợ tuần hoàn não"])
    if "mề đay" in source:
        illnesses.append("Mề đay")
    if not illnesses:
        illnesses.append("Hỗ trợ sức khỏe")

    unique = list(dict.fromkeys(illnesses))
    return unique, unique[0]


def build_traditional_data(drug_id: str, name_vn: str, notes: str) -> dict[str, Any]:
    illness_vn, illness_short = derive_illness(name_vn, notes)
    return {
        "drug_id": drug_id,
        "name_vn": name_vn,
        "name_generic": None,
        "atc_code": None,
        "drug_class_vn": "Thuốc đông y / thảo dược",
        "illness_vn": illness_vn,
        "illness_short_vn": illness_short,
        "child_friendly_use_vn": "Thuốc đông y giúp hỗ trợ sức khỏe",
        "usage_timing": "sau ăn",
        "side_effects_common": [],
        "side_effects_severe": [],
        "warnings": [],
        "must_complete_course": False,
        "gloss_illness_tokens": ["thuốc", "đông y"],
        "notes": notes,
        "generic_name_en": "",
        "generic_name_vn": "",
        "contraindications_vn": [],
        "typical_co_drugs": [],
        "age_min_years": 0,
        "age_max_years": 99,
        "common_usage_patterns_vn": [],
    }


def unique_drug_id(conn: sqlite3.Connection, base: str) -> str:
    candidate = base
    suffix = 2
    while conn.execute("SELECT 1 FROM drugs WHERE drug_id = ?", (candidate,)).fetchone():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def add_alias(conn: sqlite3.Connection, alias: str, target_drug_id: str) -> tuple[str, str]:
    if not alias:
        return "error", "empty alias"
    existing = conn.execute("SELECT drug_id FROM drug_aliases WHERE alias = ?", (alias,)).fetchone()
    if existing:
        return "skipped", f"alias already exists -> {existing[0]}"
    if not conn.execute("SELECT 1 FROM drugs WHERE drug_id = ?", (target_drug_id,)).fetchone():
        return "error", f"target drug_id does not exist: {target_drug_id}"
    conn.execute("INSERT INTO drug_aliases (alias, drug_id) VALUES (?, ?)", (alias, target_drug_id))
    return "added", f"alias added -> {target_drug_id}"


def add_traditional_entry(conn: sqlite3.Connection, name: str, notes: str) -> tuple[str, str]:
    base_slug = slugify(name)
    existing_alias = conn.execute(
        "SELECT drug_id FROM drug_aliases WHERE alias = ?",
        (alias_value(name),),
    ).fetchone()
    if existing_alias:
        return "skipped", f"alias already exists -> {existing_alias[0]}"

    drug_id = unique_drug_id(conn, base_slug)
    data = build_traditional_data(drug_id, name, notes)
    conn.execute(
        """
        INSERT INTO drugs (
            drug_id, name_vn, name_generic, atc_code, data_json, is_traditional
        )
        VALUES (?, ?, ?, ?, ?, TRUE)
        """,
        (
            drug_id,
            name,
            None,
            None,
            json.dumps(data, ensure_ascii=False),
        ),
    )
    conn.execute("INSERT INTO drug_aliases (alias, drug_id) VALUES (?, ?)", (alias_value(name), drug_id))
    return "added", f"traditional entry added -> {drug_id}"


def add_drop_entry(conn: sqlite3.Connection, name: str, notes: str) -> tuple[str, str]:
    ignore_name = alias_value(name)
    existing = conn.execute("SELECT 1 FROM drug_ignore_list WHERE name = ?", (ignore_name,)).fetchone()
    if existing:
        return "skipped", "ignore-list entry already exists"
    conn.execute(
        """
        INSERT INTO drug_ignore_list (name, reason, added_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (ignore_name, notes),
    )
    return "added", "ignore-list entry added"


def eligible_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        df["category"].fillna("").eq("needs_human_review")
        & df["human_decision"].fillna("").isin(ELIGIBLE_DECISIONS)
        & df["notes"].fillna("").str.contains("VERIFIED:", regex=False)
    ].copy()


def write_report(summary: dict[str, Any], row_logs: list[dict[str, str]], errors: list[str]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Wave 1 Verified Decision Apply Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Source CSV: `{SOURCE_CSV}`",
        f"Database backup: `{BACKUP_PATH}`",
        "",
        "## Summary",
        "",
        f"- Total verified rows processed: {summary['verified_rows_processed']}",
        f"- Aliases added: {summary['aliases_added']}",
        f"- Aliases skipped already exists: {summary['aliases_skipped']}",
        f"- Traditional entries added: {summary['traditional_added']}",
        f"- Traditional entries skipped: {summary['traditional_skipped']}",
        f"- Drop entries added: {summary['drops_added']}",
        f"- Drop entries skipped: {summary['drops_skipped']}",
        f"- Errors: {len(errors)}",
        "",
        "## Schema Changes",
        "",
    ]
    lines.extend(f"- {change}" for change in summary["schema_changes"])
    lines.extend(["", "## Row Log", ""])
    lines.append("| drug_name_extracted | decision | status | detail |")
    lines.append("|---|---|---|---|")
    for log in row_logs:
        lines.append(
            f"| {log['drug']} | {log['decision']} | {log['status']} | {log['detail']} |"
        )
    lines.extend(["", "## Errors", ""])
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- None")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not SOURCE_CSV.exists():
        raise SystemExit(f"Missing source CSV: {SOURCE_CSV}")
    if not DB_PATH.exists():
        raise SystemExit(f"Missing DB: {DB_PATH}")

    shutil.copy2(DB_PATH, BACKUP_PATH)

    df = pd.read_csv(SOURCE_CSV, encoding="utf-8-sig").fillna("")
    rows = eligible_rows(df)

    summary: dict[str, Any] = {
        "schema_changes": [],
        "verified_rows_processed": int(len(rows)),
        "aliases_added": 0,
        "aliases_skipped": 0,
        "traditional_added": 0,
        "traditional_skipped": 0,
        "drops_added": 0,
        "drops_skipped": 0,
    }
    row_logs: list[dict[str, str]] = []
    errors: list[str] = []

    with sqlite3.connect(DB_PATH) as conn:
        summary["schema_changes"] = rebuild_drugs_table_nullable(conn)
        create_ignore_table(conn)

        for _, row in rows.iterrows():
            drug_name = clean_text(row.get("drug_name_extracted"))
            decision = clean_text(row.get("human_decision"))
            notes = clean_text(row.get("notes"))

            try:
                if decision == "alias":
                    target_id, target_detail = resolve_alias_target(row, conn)
                    if not target_id:
                        raise ValueError(target_detail)
                    status, detail = add_alias(conn, alias_value(drug_name), target_id)
                    detail = f"{detail}; target resolution: {target_detail}"
                    if status == "added":
                        summary["aliases_added"] += 1
                    elif status == "skipped":
                        summary["aliases_skipped"] += 1
                    else:
                        raise ValueError(detail)

                elif decision == "traditional":
                    status, detail = add_traditional_entry(conn, drug_name, notes)
                    if status == "added":
                        summary["traditional_added"] += 1
                    elif status == "skipped":
                        summary["traditional_skipped"] += 1
                    else:
                        raise ValueError(detail)

                elif decision == "drop":
                    status, detail = add_drop_entry(conn, drug_name, notes)
                    if status == "added":
                        summary["drops_added"] += 1
                    elif status == "skipped":
                        summary["drops_skipped"] += 1
                    else:
                        raise ValueError(detail)

                else:
                    status, detail = "skipped", f"unsupported decision: {decision}"

                row_logs.append(
                    {
                        "drug": drug_name,
                        "decision": decision,
                        "status": status,
                        "detail": detail,
                    }
                )

            except Exception as exc:  # keep applying safe rows after row-level failures
                message = f"{drug_name} ({decision}): {exc}"
                errors.append(message)
                row_logs.append(
                    {
                        "drug": drug_name,
                        "decision": decision,
                        "status": "error",
                        "detail": str(exc),
                    }
                )

        conn.commit()

    write_report(summary, row_logs, errors)

    print(f"Backed up DB to: {BACKUP_PATH}")
    print("Schema changes applied:")
    for change in summary["schema_changes"]:
        print(f"- {change}")
    print(f"Total verified rows processed: {summary['verified_rows_processed']}")
    print(f"Aliases added: {summary['aliases_added']}")
    print(f"Aliases skipped already exists: {summary['aliases_skipped']}")
    print(f"Traditional entries added: {summary['traditional_added']}")
    print(f"Drop entries added: {summary['drops_added']}")
    print(f"Errors: {len(errors)}")
    for error in errors:
        print(f"- ERROR: {error}")
    print(f"Saved summary report to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
