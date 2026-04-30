"""Propose conservative top-30 alias mappings for unresolved drug candidates."""

import csv
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
INPUT_CSV = REPO_ROOT / "results" / "unresolved_drug_review_queue.csv"
OUTPUT_CSV = REPO_ROOT / "results" / "proposed_aliases_top30.csv"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"


# Conservative proposals only. "review" rows are intentionally not safe for DB insertion yet.
PROPOSALS: dict[str, dict[str, str]] = {
    "panactol": {
        "target": "Paracetamol",
        "confidence_note": "high",
        "reason": "Raw forms are PANACTOL 500mg and the strict matcher already suggested Paracetamol; 500mg analgesic/antipyretic context is consistent.",
        "apply_alias": "yes",
    },
    "partamol": {
        "target": "Paracetamol",
        "confidence_note": "high",
        "reason": "PARTAMOL TAB. 500mg is a paracetamol-like brand form; diagnoses include pain/URI/dental inflammation where paracetamol is plausible.",
        "apply_alias": "yes",
    },
    "mypara": {
        "target": "Paracetamol",
        "confidence_note": "high",
        "reason": "MYPARA 500 appears as 500mg tablets across pain/inflammation prescriptions; name and strength strongly indicate paracetamol.",
        "apply_alias": "yes",
    },
    "glucofast": {
        "target": "metformin",
        "confidence_note": "high",
        "reason": "GLUCOFAST 500/850mg appears with E11 diabetes diagnoses; strengths match common metformin dosing and metformin exists in KB.",
        "apply_alias": "yes",
    },
    "dixirein": {
        "target": "carbocisteine",
        "confidence_note": "review",
        "reason": "DIXIREIN 375mg appears mostly with bronchitis/respiratory diagnoses; 375mg fits carbocisteine better than the fuzzy diacerein match, but brand evidence should be manually checked.",
        "apply_alias": "review",
    },
    "hapenxin": {
        "target": "cefalexin",
        "confidence_note": "high",
        "reason": "HAPENXIN CAPSULES 0.5g appears with skin/dental/respiratory infection diagnoses; 0.5g capsule pattern matches cefalexin/cephalexin in the KB.",
        "apply_alias": "yes",
    },
    "kavasdin": {
        "target": "Amlodipine",
        "confidence_note": "high",
        "reason": "KAVASDIN 5 5mg appears repeatedly with hypertension diagnoses; 5mg is a standard amlodipine strength.",
        "apply_alias": "yes",
    },
    "vipredni": {
        "target": "methylprednisolone",
        "confidence_note": "high",
        "reason": "VIPREDNI 16mg appears with respiratory/inflammatory diagnoses; 16mg is a common methylprednisolone tablet strength.",
        "apply_alias": "yes",
    },
    "fabamox": {
        "target": "Amoxicillin",
        "confidence_note": "high",
        "reason": "FABAMOX 500mg appears with respiratory/dental infection diagnoses; name and 500mg strength are consistent with amoxicillin.",
        "apply_alias": "yes",
    },
    "novoxim": {
        "target": "cefuroxime",
        "confidence_note": "medium",
        "reason": "NOVOXIM-500 0.5g appears with infection diagnoses; name suffix and 500mg strength fit cefuroxime, but this should be reviewed if exact brand confirmation is required.",
        "apply_alias": "yes",
    },
    "meglucon": {
        "target": "metformin",
        "confidence_note": "high",
        "reason": "MEGLUCON 1000mg appears with E11 diabetes diagnoses; 1000mg is a standard metformin strength.",
        "apply_alias": "yes",
    },
    "bromhexin actavis": {
        "target": "bromhexine",
        "confidence_note": "high",
        "reason": "BROMHEXIN ACTAVIS 8mg is effectively the generic name plus manufacturer; bronchitis diagnoses support bromhexine.",
        "apply_alias": "yes",
    },
    "lazibet": {
        "target": "gliclazide",
        "confidence_note": "high",
        "reason": "LAZIBET MR 60mg appears with E11 diabetes diagnoses; MR 60mg matches gliclazide modified-release dosing.",
        "apply_alias": "yes",
    },
    "katrypsin": {
        "target": "chymotrypsin",
        "confidence_note": "high",
        "reason": "KATRYPSIN 4.2mg appears with trauma/wound diagnoses; the KB fuzzy match to trypsin is close, but 4.2mg brand pattern indicates chymotrypsin.",
        "apply_alias": "yes",
    },
    "cosyndo b": {
        "target": "",
        "confidence_note": "skip",
        "reason": "Combination strengths 175mg+175mg+125mcg are not enough to identify a single KB generic safely.",
        "apply_alias": "review",
    },
    "sergurop": {
        "target": "",
        "confidence_note": "skip",
        "reason": "SERGUROP 10mg appears in allergy/URI contexts, but the candidate name does not identify cetirizine/loratadine/desloratadine safely.",
        "apply_alias": "review",
    },
    "pamlonor": {
        "target": "Amlodipine",
        "confidence_note": "high",
        "reason": "PAMLONOR 5mg appears with hypertension diagnoses; ignore the bad fuzzy palonosetron match because dose/context fit amlodipine.",
        "apply_alias": "yes",
    },
    "setblood": {
        "target": "",
        "confidence_note": "skip",
        "reason": "SETBLOOD 115mg+100mg+50mcg looks like a vitamin/hematologic combination, but the exact KB target is ambiguous.",
        "apply_alias": "review",
    },
    "chorlatcyn": {
        "target": "",
        "confidence_note": "skip",
        "reason": "CHORLATCYN has a multi-ingredient strength string; no conservative single generic target can be inferred from local evidence.",
        "apply_alias": "review",
    },
    "clorpheniramin": {
        "target": "chlorphenamine",
        "confidence_note": "high",
        "reason": "CLORPHENIRAMIN 4mg is the Vietnamese spelling/OCR form of chlorphenamine; allergy/URI diagnoses are consistent.",
        "apply_alias": "yes",
    },
    "tydol pm": {
        "target": "paracetamol, combinations with psycholeptics",
        "confidence_note": "medium",
        "reason": "TYDOL PM 500mg+25mg fits paracetamol plus sedating antihistamine; KB has the ATC combo Paracetamol combinations with psycholeptics.",
        "apply_alias": "yes",
    },
    "menison": {
        "target": "methylprednisolone",
        "confidence_note": "high",
        "reason": "MENISON 4mg/16mg appears with respiratory/dermatologic inflammatory diagnoses; strengths match methylprednisolone.",
        "apply_alias": "yes",
    },
    "hangitor plus": {
        "target": "telmisartan and diuretics",
        "confidence_note": "high",
        "reason": "HANGITOR PLUS 40mg+12.5mg appears with hypertension diagnoses; 40+12.5 pattern matches telmisartan plus thiazide diuretic combination.",
        "apply_alias": "yes",
    },
    "dromasm fort": {
        "target": "drotaverine",
        "confidence_note": "high",
        "reason": "DROMASM FORT 80mg appears with abdominal/GI diagnoses; 80mg is a standard drotaverine forte strength.",
        "apply_alias": "yes",
    },
    "diamicron 30 s": {
        "target": "gliclazide",
        "confidence_note": "high",
        "reason": "DIAMICRON MR 60mg 30'S appears with E11 diabetes diagnoses; Diamicron MR maps to gliclazide.",
        "apply_alias": "yes",
    },
    "savi prolol": {
        "target": "bisoprolol",
        "confidence_note": "high",
        "reason": "SAVI PROLOL 5mg appears with hypertension/arrhythmia/cardiac diagnoses; 5mg beta-blocker pattern fits bisoprolol.",
        "apply_alias": "yes",
    },
    "amcardia": {
        "target": "Amlodipine",
        "confidence_note": "high",
        "reason": "AMCARDIA-5 5mg appears with hypertension diagnoses; 5mg calcium-channel-blocker pattern fits amlodipine.",
        "apply_alias": "yes",
    },
    "cefacyl": {
        "target": "cefaclor",
        "confidence_note": "review",
        "reason": "CEFACYL 500 0.5g appears with infection diagnoses and resembles a cephalosporin brand, but cefaclor vs other cephalosporins should be manually confirmed.",
        "apply_alias": "review",
    },
    "inbacid": {
        "target": "",
        "confidence_note": "skip",
        "reason": "INBACID 10mg appears in hypertension/hyperlipidemia contexts, but the name does not identify a safe existing KB generic.",
        "apply_alias": "review",
    },
    "vina ad": {
        "target": "",
        "confidence_note": "skip",
        "reason": "VINA-AD 2000ui+400ui looks like a vitamin A/D combination; no exact single KB target is safe from local evidence.",
        "apply_alias": "review",
    },
}


def load_kb_names() -> dict[str, dict[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT name_generic, atc_code FROM drugs").fetchall()
    finally:
        conn.close()

    return {
        str(name).strip().lower(): {"name": str(name).strip(), "atc_code": str(atc or "").strip()}
        for name, atc in rows
        if str(name).strip()
    }


def resolve_target(target: str, kb_names: dict[str, dict[str, str]]) -> tuple[str, str]:
    if not target:
        return "", ""
    info = kb_names.get(target.lower())
    if not info:
        return "", ""
    return info["name"], info["atc_code"]


def build_proposals() -> pd.DataFrame:
    queue_df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    top_aliases = (
        queue_df[queue_df["suggested_action"].eq("add_alias")]
        .sort_values(["frequency_in_synthetic_dataset", "candidate_drug"], ascending=[False, True])
        .head(30)
    )
    kb_names = load_kb_names()

    rows: list[dict[str, Any]] = []
    for row in top_aliases.itertuples(index=False):
        candidate = str(row.candidate_drug).strip()
        proposal = PROPOSALS.get(
            candidate,
            {
                "target": "",
                "confidence_note": "skip",
                "reason": "No conservative proposal configured from local evidence.",
                "apply_alias": "review",
            },
        )
        target, atc_code = resolve_target(proposal["target"], kb_names)
        apply_alias = proposal["apply_alias"]
        reason = proposal["reason"]
        confidence_note = proposal["confidence_note"]

        if proposal["target"] and not target:
            apply_alias = "review"
            confidence_note = "target_missing"
            reason = f"{reason} Proposed target '{proposal['target']}' was not found in vaipe_drugs.db."
        elif target:
            reason = f"{reason} Target exists in KB/ATC as '{target}' ({atc_code or 'no ATC code'})."

        rows.append(
            {
                "candidate_drug": candidate,
                "proposed_generic_name": target,
                "confidence_note": confidence_note,
                "reason": reason,
                "apply_alias": apply_alias,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "candidate_drug",
            "proposed_generic_name",
            "confidence_note",
            "reason",
            "apply_alias",
        ],
    )


def main() -> None:
    proposal_df = build_proposals()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    proposal_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    print(f"Saved proposed aliases: {OUTPUT_CSV}")
    print("\nTop 30 alias proposals:")
    headers = ["candidate_drug", "proposed_generic_name", "confidence_note", "apply_alias"]
    widths = {
        "candidate_drug": 20,
        "proposed_generic_name": 42,
        "confidence_note": 15,
        "apply_alias": 11,
    }
    print(
        " | ".join(header.ljust(widths[header]) for header in headers)
    )
    print(
        "-|-".join("-" * widths[header] for header in headers)
    )
    for row in proposal_df.itertuples(index=False):
        values = {
            "candidate_drug": row.candidate_drug,
            "proposed_generic_name": row.proposed_generic_name,
            "confidence_note": row.confidence_note,
            "apply_alias": row.apply_alias,
        }
        print(" | ".join(str(values[header]).ljust(widths[header]) for header in headers))


if __name__ == "__main__":
    main()
