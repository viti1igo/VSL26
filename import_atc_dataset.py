"""Import WHO ATC/DDD level-5 drug names into the local SQLite knowledge base."""

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

from count_drugs import normalize_drug_name
from medicine_mapper import DrugInfo, DrugKnowledgeBase, MedicineMapper


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_URL = "https://raw.githubusercontent.com/fabkury/atcd/master/WHO%20ATC-DDD%202024-07-31.csv"
DEFAULT_CSV_PATH = REPO_ROOT / "data" / "WHO_ATC_DDD_2024.csv"
DEFAULT_DB_PATH = REPO_ROOT / "vaipe_drugs.db"
SYNTHETIC_PATH = REPO_ROOT / "results" / "drug_illness_synthetic.csv"


def download_atc_csv(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=60) as response:
        output_path.write_bytes(response.read())


def _column(df: pd.DataFrame, *names: str) -> str:
    lowered = {column.lower(): column for column in df.columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    raise ValueError(f"Missing one of required columns: {names}")


def load_level5_atc_entries(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    code_col = _column(df, "Code", "atc_code")
    name_col = _column(df, "Name", "atc_name")
    entries = df[[code_col, name_col]].rename(
        columns={code_col: "atc_code", name_col: "generic_name_en"}
    )
    entries["atc_code"] = entries["atc_code"].fillna("").astype(str).str.strip()
    entries["generic_name_en"] = entries["generic_name_en"].fillna("").astype(str).str.strip()
    entries = entries[
        (entries["atc_code"].str.len() == 7)
        & (entries["generic_name_en"] != "")
        & (~entries["generic_name_en"].str.lower().eq("combinations"))
    ]
    return entries.drop_duplicates(["atc_code", "generic_name_en"]).sort_values(
        ["atc_code", "generic_name_en"]
    )


def _drug_id(atc_code: str, generic_name_en: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", generic_name_en.lower()).strip("_")
    return f"atc_{atc_code.lower()}_{slug}"[:120]


def _alias_exists(conn: sqlite3.Connection, alias: str) -> bool:
    normalized = normalize_drug_name(alias)
    if not normalized:
        return False
    row = conn.execute("SELECT 1 FROM drug_aliases WHERE alias = ?", (normalized,)).fetchone()
    return row is not None


def _atc_exists(conn: sqlite3.Connection, atc_code: str, generic_name_en: str) -> bool:
    normalized = normalize_drug_name(generic_name_en)
    row = conn.execute(
        """
        SELECT 1
        FROM drugs
        WHERE lower(atc_code) = lower(?)
           OR lower(name_generic) = lower(?)
           OR drug_id = ?
        LIMIT 1
        """,
        (atc_code, generic_name_en, _drug_id(atc_code, normalized)),
    ).fetchone()
    return row is not None or _alias_exists(conn, generic_name_en)


def _existing_imported_drug_id(conn: sqlite3.Connection, atc_code: str, generic_name_en: str) -> str | None:
    row = conn.execute(
        """
        SELECT drug_id
        FROM drugs
        WHERE drug_id LIKE 'atc_%'
          AND lower(atc_code) = lower(?)
          AND lower(name_generic) = lower(?)
        LIMIT 1
        """,
        (atc_code, generic_name_en),
    ).fetchone()
    return str(row[0]) if row else None


def _needs_vietnamese_name(conn: sqlite3.Connection, drug_id: str) -> bool:
    row = conn.execute("SELECT data_json FROM drugs WHERE drug_id = ?", (drug_id,)).fetchone()
    if not row:
        return False
    data = json.loads(row[0])
    return not str(data.get("generic_name_vn", "")).strip()


def _update_vietnamese_name(db_path: Path, drug_id: str, vi_name: str) -> None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT data_json FROM drugs WHERE drug_id = ?", (drug_id,)).fetchone()
        if not row:
            return
        data = json.loads(row[0])
        data["generic_name_vn"] = vi_name
        if vi_name:
            data["name_vn"] = vi_name
        conn.execute(
            "UPDATE drugs SET name_vn = ?, data_json = ? WHERE drug_id = ?",
            (data.get("name_vn", vi_name), json.dumps(data, ensure_ascii=False), drug_id),
        )


def _translate_name(mapper: MedicineMapper, generic_name_en: str, atc_code: str) -> str:
    # LLM translation is optional at runtime. If OPENAI_API_KEY is absent,
    # MedicineMapper returns None and we keep the Vietnamese field empty for review.
    translated = mapper.enrich_drug_with_llm(
        name_en=generic_name_en,
        atc_code=atc_code,
        only_translate=True,
    )
    return str(translated or "").strip()


def _drug_info(generic_name_en: str, vi_name: str, atc_code: str) -> DrugInfo:
    return DrugInfo(
        drug_id=_drug_id(atc_code, generic_name_en),
        name_vn=vi_name or generic_name_en,
        name_generic=generic_name_en,
        atc_code=atc_code,
        drug_class_vn="Hoạt chất nhập từ WHO ATC/DDD",
        illness_vn=[],
        illness_short_vn="",
        child_friendly_use_vn="",
        usage_timing="",
        side_effects_common=[],
        side_effects_severe=[],
        warnings=[],
        must_complete_course=False,
        gloss_illness_tokens=[],
        notes="Imported from WHO ATC/DDD CSV via fabkury/atcd; indications require manual review.",
        generic_name_en=generic_name_en,
        generic_name_vn=vi_name,
        contraindications_vn=[],
        typical_co_drugs=[],
        age_min_years=0,
        age_max_years=99,
        common_usage_patterns_vn=[],
    )


def _add_alias(conn: sqlite3.Connection, alias: str, drug_id: str) -> bool:
    normalized = normalize_drug_name(alias)
    if not normalized:
        return False
    cursor = conn.execute(
        "INSERT OR IGNORE INTO drug_aliases (alias, drug_id) VALUES (?, ?)",
        (normalized, drug_id),
    )
    return cursor.rowcount > 0


def import_synthetic_aliases(db_path: Path, synthetic_path: Path) -> int:
    if not synthetic_path.exists():
        return 0

    df = pd.read_csv(synthetic_path, encoding="utf-8-sig")
    required = {"drug_raw", "drug_normalized"}
    if not required.issubset(df.columns):
        return 0

    added = 0
    with sqlite3.connect(db_path) as conn:
        for row in df.dropna(subset=["drug_raw", "drug_normalized"]).to_dict("records"):
            drug_raw = str(row["drug_raw"]).strip()
            generic = str(row["drug_normalized"]).strip()
            if not drug_raw or not generic:
                continue
            match = conn.execute(
                "SELECT drug_id FROM drugs WHERE lower(name_generic) = lower(?) OR lower(name_vn) = lower(?) LIMIT 1",
                (generic, generic),
            ).fetchone()
            if match and _add_alias(conn, drug_raw, match[0]):
                added += 1
    return added


def import_atc_dataset(
    csv_path: Path = DEFAULT_CSV_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    url: str = DEFAULT_URL,
    skip_download: bool = False,
    translate: bool = True,
    alias_from_synthetic: bool = True,
    translation_limit: int | None = None,
) -> None:
    # Source note: the atcd GitHub project documents a full WHO ATC/DDD CSV
    # export for non-commercial use from the WHO ATC/DDD index.
    # https://github.com/fabkury/atcd/blob/master/README.md
    if not skip_download:
        print(f"Downloading ATC/DDD CSV from {url}")
        download_atc_csv(url, csv_path)

    entries = load_level5_atc_entries(csv_path)
    kb = DrugKnowledgeBase(db_path=str(db_path))
    mapper = MedicineMapper(db_path=str(db_path), auto_enrich=False)
    api_available = bool(os.getenv("OPENAI_API_KEY"))

    added = 0
    skipped = 0
    translation_failed = 0
    translation_updated = 0

    total = len(entries)
    for index, row in enumerate(entries.itertuples(index=False), start=1):
        atc_code = str(row.atc_code)
        generic_name_en = str(row.generic_name_en)

        with sqlite3.connect(db_path) as conn:
            exists = _atc_exists(conn, atc_code, generic_name_en)
            existing_drug_id = _existing_imported_drug_id(conn, atc_code, generic_name_en)
            needs_vietnamese_name = (
                existing_drug_id is not None and _needs_vietnamese_name(conn, existing_drug_id)
            )

        if exists:
            skipped += 1
            if (
                translate
                and api_available
                and needs_vietnamese_name
                and existing_drug_id is not None
                and (translation_limit is None or translation_updated < translation_limit)
            ):
                try:
                    vi_name = _translate_name(mapper, generic_name_en, atc_code)
                    if vi_name:
                        _update_vietnamese_name(db_path, existing_drug_id, vi_name)
                        translation_updated += 1
                    else:
                        translation_failed += 1
                except Exception as exc:
                    translation_failed += 1
                    print(
                        f"Warning: translation failed for {generic_name_en} ({atc_code}): "
                        f"{type(exc).__name__}: {exc}"
                    )
        else:
            vi_name = ""
            if translate and api_available:
                try:
                    vi_name = _translate_name(mapper, generic_name_en, atc_code)
                except Exception as exc:
                    translation_failed += 1
                    print(
                        f"Warning: translation failed for {generic_name_en} ({atc_code}): "
                        f"{type(exc).__name__}: {exc}"
                    )
            elif translate:
                translation_failed += 1

            kb.add_drug(_drug_info(generic_name_en, vi_name, atc_code), aliases=[generic_name_en])
            added += 1

        if index % 100 == 0:
            print(
                f"Processed {index} drugs; added {added} new entries; "
                f"skipped {skipped} existing; translated {translation_updated}."
            )

    alias_added = import_synthetic_aliases(db_path, SYNTHETIC_PATH) if alias_from_synthetic else 0

    print("=== ATC IMPORT SUMMARY ===")
    print(f"Total level-5 ATC entries: {len(entries)}")
    print(f"Number added to DB: {added}")
    print(f"Number skipped existing: {skipped}")
    print(f"Number of existing names translated: {translation_updated}")
    print(f"Number of names where Vietnamese translation failed: {translation_failed}")
    print(f"Synthetic aliases added: {alias_added}")
    print(f"CSV path: {csv_path}")
    print(f"DB path: {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import WHO ATC level-5 active ingredients into vaipe_drugs.db.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--no-translate", action="store_true", help="Do not call the LLM translation helper.")
    parser.add_argument("--no-synthetic-aliases", action="store_true")
    parser.add_argument(
        "--translation-limit",
        type=int,
        default=None,
        help="Maximum number of missing Vietnamese names to translate in this run.",
    )
    args = parser.parse_args()

    import_atc_dataset(
        csv_path=args.csv,
        db_path=args.db,
        url=args.url,
        skip_download=args.skip_download,
        translate=not args.no_translate,
        alias_from_synthetic=not args.no_synthetic_aliases,
        translation_limit=args.translation_limit,
    )


if __name__ == "__main__":
    main()
