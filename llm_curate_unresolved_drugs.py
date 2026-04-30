"""Generate LLM-assisted curation suggestions for unresolved prescription drugs."""

import csv
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None

from medicine_mapper import _extract_json_object, _extract_openai_output_text


REPO_ROOT = Path(__file__).resolve().parent
INPUT_CSV = REPO_ROOT / "results" / "unresolved_drug_review_queue.csv"
OUTPUT_CSV = REPO_ROOT / "results" / "llm_unresolved_drug_suggestions_top40.csv"
OUTPUT_JSON = REPO_ROOT / "results" / "llm_unresolved_drug_suggestions_top40.json"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
FIELDS = [
    "candidate_drug",
    "likely_generic_name",
    "likely_vietnamese_name",
    "likely_drug_class",
    "likely_indications_vn",
    "likely_is_alias_of_existing_drug",
    "existing_kb_target_if_alias",
    "likely_is_traditional_medicine",
    "likely_is_ocr_error",
    "confidence_note",
    "human_review_required",
]


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _text(value: Any, limit: int | None = None) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if limit and len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def load_kb_search_terms() -> list[dict[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        drug_rows = conn.execute("SELECT drug_id, name_generic, atc_code FROM drugs").fetchall()
        alias_rows = conn.execute(
            """
            SELECT a.alias, d.drug_id, d.name_generic, d.atc_code
            FROM drug_aliases a
            JOIN drugs d ON d.drug_id = a.drug_id
            """
        ).fetchall()
    finally:
        conn.close()

    terms: list[dict[str, str]] = []
    for drug_id, name_generic, atc_code in drug_rows:
        generic = str(name_generic or "").strip()
        if generic:
            terms.append(
                {
                    "match_text": generic.lower(),
                    "name_generic": generic,
                    "atc_code": str(atc_code or ""),
                    "source": "generic",
                }
            )
    for alias, _drug_id, name_generic, atc_code in alias_rows:
        alias_text = str(alias or "").strip()
        generic = str(name_generic or "").strip()
        if alias_text and generic:
            terms.append(
                {
                    "match_text": alias_text.lower(),
                    "name_generic": generic,
                    "atc_code": str(atc_code or ""),
                    "source": f"alias:{alias_text}",
                }
            )
    return terms


def nearest_kb_context(candidate: str, kb_terms: list[dict[str, str]], limit: int = 7) -> str:
    scored: list[tuple[float, dict[str, str]]] = []
    needle = candidate.lower()
    for row in kb_terms:
        if fuzz is not None:
            score = float(fuzz.token_set_ratio(needle, row["match_text"]))
        else:
            score = 100.0 if needle == row["match_text"] else 0.0
        if score >= 55:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)

    parts = []
    seen = set()
    for score, row in scored:
        key = (row["name_generic"], row["atc_code"])
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"{row['name_generic']} ({row['atc_code'] or 'no ATC'}, {score:.0f}, {row['source']})")
        if len(parts) >= limit:
            break
    return "; ".join(parts) if parts else "none"


def build_prompt(row: pd.Series, kb_context: str) -> str:
    schema = {
        "candidate_drug": "copy candidate",
        "likely_generic_name": "generic/ingredient name or empty",
        "likely_vietnamese_name": "Vietnamese common name or empty",
        "likely_drug_class": "short Vietnamese/English class",
        "likely_indications_vn": "short Vietnamese semicolon list",
        "likely_is_alias_of_existing_drug": "yes/no",
        "existing_kb_target_if_alias": "exact KB generic name or empty",
        "likely_is_traditional_medicine": "yes/no",
        "likely_is_ocr_error": "yes/no",
        "confidence_note": "high/medium/low + brief reason",
        "human_review_required": "yes/no",
    }
    return (
        "Bạn là dược sĩ hỗ trợ chuẩn hóa tên thuốc Việt Nam cho KB nghiên cứu. "
        "Không kê đơn. Trả về DUY NHẤT JSON hợp lệ, không markdown.\n"
        f"Schema keys: {json.dumps(schema, ensure_ascii=False)}\n"
        "Quy tắc: nếu là brand/spelling của thuốc đã có trong KB, set alias=yes và existing_kb_target_if_alias đúng tên KB. "
        "Nếu thuốc đông y/thảo dược, traditional=yes. Nếu OCR/rác, ocr_error=yes. "
        "Nếu không chắc, human_review_required=yes.\n"
        f"candidate={_text(row.get('candidate_drug'))}\n"
        f"freq={int(row.get('frequency_in_synthetic_dataset', 0) or 0)}\n"
        f"raw_examples={_text(row.get('example_raw_forms'), 360)}\n"
        f"diagnoses={_text(row.get('example_diagnoses'), 420)}\n"
        f"nearest_existing_kb={kb_context}\n"
    )


def call_openai(prompt: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    request_body = json.dumps(
        {
            "model": os.getenv("OPENAI_MODEL", "gpt-5"),
            "input": prompt,
            "max_output_tokens": 700,
        },
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {body[:500]}") from exc

    content = _extract_openai_output_text(payload)
    return json.loads(_extract_json_object(content))


def _yes_no(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "1", "có", "co"}:
        return "yes"
    if text in {"no", "false", "0", "không", "khong"}:
        return "no"
    return "yes" if "yes" in text or "có" in text else "no"


def normalize_result(candidate: str, payload: dict[str, Any]) -> dict[str, str]:
    row = {field: _text(payload.get(field)) for field in FIELDS}
    row["candidate_drug"] = candidate
    for field in [
        "likely_is_alias_of_existing_drug",
        "likely_is_traditional_medicine",
        "likely_is_ocr_error",
        "human_review_required",
    ]:
        row[field] = _yes_no(row[field])
    return row


def error_result(candidate: str, exc: Exception) -> dict[str, str]:
    return {
        "candidate_drug": candidate,
        "likely_generic_name": "",
        "likely_vietnamese_name": "",
        "likely_drug_class": "",
        "likely_indications_vn": "",
        "likely_is_alias_of_existing_drug": "no",
        "existing_kb_target_if_alias": "",
        "likely_is_traditional_medicine": "no",
        "likely_is_ocr_error": "no",
        "confidence_note": f"API_ERROR: {type(exc).__name__}: {_text(exc, 180)}",
        "human_review_required": "yes",
    }


def category_for(row: dict[str, str]) -> str:
    if row["likely_is_ocr_error"] == "yes":
        return "ocr_error"
    if row["likely_is_traditional_medicine"] == "yes":
        return "traditional_medicine"
    if row["likely_is_alias_of_existing_drug"] == "yes":
        return "alias_of_existing_drug"
    return "new_generic_drug_needed"


def print_table(rows: list[dict[str, str]]) -> None:
    headers = ["candidate_drug", "likely_generic_name", "existing_kb_target_if_alias", "category", "human_review_required"]
    widths = {
        "candidate_drug": 32,
        "likely_generic_name": 30,
        "existing_kb_target_if_alias": 34,
        "category": 26,
        "human_review_required": 21,
    }
    print(" | ".join(header.ljust(widths[header]) for header in headers))
    print("-|-".join("-" * widths[header] for header in headers))
    for row in rows:
        values = {**row, "category": category_for(row)}
        print(" | ".join(_text(values[header], widths[header]).ljust(widths[header]) for header in headers))


def main() -> None:
    load_dotenv()
    queue_df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    selected = queue_df.sort_values(
        ["frequency_in_synthetic_dataset", "candidate_drug"],
        ascending=[False, True],
    ).head(40)
    kb_terms = load_kb_search_terms()

    rows: list[dict[str, str]] = []
    api_calls = 0
    for index, row in enumerate(selected.itertuples(index=False), start=1):
        series = pd.Series(row._asdict())
        candidate = _text(series.get("candidate_drug"))
        print(f"[{index}/{len(selected)}] Curating {candidate}...")
        try:
            prompt = build_prompt(series, nearest_kb_context(candidate, kb_terms))
            api_calls += 1
            payload = call_openai(prompt)
            rows.append(normalize_result(candidate, payload))
        except Exception as exc:
            rows.append(error_result(candidate, exc))
            print(f"  warning: {type(exc).__name__}: {_text(exc, 220)}")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=FIELDS).to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
    )
    OUTPUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    category_counts = {
        "alias_of_existing_drug": 0,
        "traditional_medicine": 0,
        "ocr_error": 0,
        "new_generic_drug_needed": 0,
    }
    for row in rows:
        category_counts[category_for(row)] += 1

    print(f"\nSaved CSV: {OUTPUT_CSV}")
    print(f"Saved JSON: {OUTPUT_JSON}")
    print(f"Total processed: {len(rows)}")
    print(f"Actual API calls made: {api_calls}")
    print("\nCategory counts:")
    for key, value in category_counts.items():
        print(f"- {key}: {value}")
    print("\nAll 40 suggestions:")
    print_table(rows)


if __name__ == "__main__":
    main()
