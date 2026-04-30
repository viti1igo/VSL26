"""Deprecated WHO ATC importer retained for provenance; use import_atc_dataset.py."""

import argparse
import csv
import sqlite3
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_URL = "https://raw.githubusercontent.com/fabkury/atcd/master/WHO%20ATC-DDD%202024-07-31.csv"
DEFAULT_CSV_PATH = REPO_ROOT / "data" / "WHO_ATC_DDD_2024-07-31.csv"
DEFAULT_DB_PATH = REPO_ROOT / "vaipe_drugs.db"


def download_csv(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=60) as response:
        content = response.read()
    output_path.write_bytes(content)


def init_atc_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS who_atc_ddd")
    conn.execute(
        """
        CREATE TABLE who_atc_ddd (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            atc_code TEXT NOT NULL,
            atc_name TEXT NOT NULL,
            ddd TEXT,
            uom TEXT,
            adm_r TEXT,
            note TEXT,
            is_leaf_drug INTEGER NOT NULL,
            source_url TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_who_atc_ddd_code ON who_atc_ddd(atc_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_who_atc_ddd_name ON who_atc_ddd(atc_name)")


def is_leaf_drug(atc_code: str, ddd: str, uom: str, adm_r: str) -> bool:
    # ATC leaf substance codes are usually 7 characters. Rows above that level
    # are hierarchy/category labels and should not be treated as drug entries.
    return len(atc_code.strip()) == 7 and any(value.strip().upper() != "NA" for value in [ddd, uom, adm_r])


def import_csv(csv_path: Path, db_path: Path, source_url: str) -> tuple[int, int]:
    if not csv_path.exists():
        raise FileNotFoundError(f"ATC/DDD CSV does not exist: {csv_path}")

    with sqlite3.connect(db_path) as conn:
        init_atc_table(conn)
        conn.execute("DELETE FROM who_atc_ddd")

        inserted = 0
        leaf_drugs = 0
        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            expected = {"atc_code", "atc_name", "ddd", "uom", "adm_r", "note"}
            missing = expected - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"ATC/DDD CSV is missing columns: {sorted(missing)}")

            for row in reader:
                atc_code = str(row.get("atc_code", "")).strip()
                atc_name = str(row.get("atc_name", "")).strip()
                if not atc_code or not atc_name:
                    continue

                ddd = str(row.get("ddd", "")).strip()
                uom = str(row.get("uom", "")).strip()
                adm_r = str(row.get("adm_r", "")).strip()
                note = str(row.get("note", "")).strip()
                leaf = int(is_leaf_drug(atc_code, ddd, uom, adm_r))
                leaf_drugs += leaf

                conn.execute(
                    """
                    INSERT INTO who_atc_ddd
                        (atc_code, atc_name, ddd, uom, adm_r, note, is_leaf_drug, source_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (atc_code, atc_name, ddd, uom, adm_r, note, leaf, source_url),
                )
                inserted += 1

    return inserted, leaf_drugs


def print_summary(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM who_atc_ddd").fetchone()[0]
        leaf = conn.execute("SELECT COUNT(*) FROM who_atc_ddd WHERE is_leaf_drug = 1").fetchone()[0]
        examples = conn.execute(
            """
            SELECT atc_code, atc_name, ddd, uom, adm_r
            FROM who_atc_ddd
            WHERE is_leaf_drug = 1
            ORDER BY atc_code
            LIMIT 10
            """
        ).fetchall()

    print(f"Total WHO ATC/DDD rows imported: {total}")
    print(f"Leaf drug rows with DDD/route data: {leaf}")
    print("First 10 leaf drug rows:")
    for atc_code, atc_name, ddd, uom, adm_r in examples:
        print(f"- {atc_code} | {atc_name} | DDD={ddd} {uom} | route={adm_r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import WHO ATC/DDD CSV into vaipe_drugs.db.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Raw WHO ATC/DDD CSV URL.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="Where to save/read the ATC/DDD CSV.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite DB to extend.")
    parser.add_argument("--skip-download", action="store_true", help="Use existing --csv instead of downloading.")
    args = parser.parse_args()

    if not args.skip_download:
        print(f"Downloading WHO ATC/DDD CSV from: {args.url}")
        download_csv(args.url, args.csv)

    inserted, leaf_drugs = import_csv(args.csv, args.db, args.url)
    print(f"Saved CSV: {args.csv}")
    print(f"Updated DB: {args.db}")
    print(f"Imported rows: {inserted}")
    print(f"Leaf drug rows: {leaf_drugs}")
    print_summary(args.db)


if __name__ == "__main__":
    main()
