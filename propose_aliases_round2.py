"""Propose conservative second-pass alias mappings for unresolved drug candidates."""

import csv
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
INPUT_CSV = REPO_ROOT / "results" / "unresolved_drug_review_queue.csv"
OUTPUT_CSV = REPO_ROOT / "results" / "proposed_aliases_round2.csv"
DB_PATH = REPO_ROOT / "vaipe_drugs.db"


# Proposal-only pass. Rows marked review are intentionally not safe for automatic DB insertion.
PROPOSALS: dict[str, dict[str, str]] = {
    "metronidazol": {
        "target": "metronidazole",
        "confidence_note": "high",
        "reason": "Vietnamese spelling/OCR form of metronidazole; raw forms are METRONIDAZOL 250mg and dental/soft-tissue infection diagnoses are consistent.",
        "apply_alias": "yes",
    },
    "dixirein": {
        "target": "carbocisteine",
        "confidence_note": "review",
        "reason": "DIXIREIN 375mg appears mainly with bronchitis/respiratory diagnoses and fits a mucolytic better than prior fuzzy matches, but exact brand confirmation is needed.",
        "apply_alias": "review",
    },
    "metformin": {
        "target": "metformin",
        "confidence_note": "high",
        "reason": "Raw forms include Metformin 500 and diagnoses are E11 diabetes; this is an exact generic already present in KB.",
        "apply_alias": "yes",
    },
    "cosyndo b": {
        "target": "",
        "confidence_note": "skip",
        "reason": "Multi-ingredient strength string 175mg+175mg+125mcg; no safe single KB target from local evidence.",
        "apply_alias": "review",
    },
    "sergurop": {
        "target": "rupatadine",
        "confidence_note": "review",
        "reason": "SERGUROP 10mg appears in allergy/URI contexts and may be an antihistamine, but rupatadine is only a plausible guess.",
        "apply_alias": "review",
    },
    "setblood": {
        "target": "",
        "confidence_note": "skip",
        "reason": "Combination product with vitamin-like strengths; diagnoses include E51 but no safe single KB target.",
        "apply_alias": "review",
    },
    "chorlatcyn": {
        "target": "",
        "confidence_note": "skip",
        "reason": "Multi-ingredient product with four strengths; no conservative generic target.",
        "apply_alias": "review",
    },
    "telmisartan hydroclorothiazid": {
        "target": "telmisartan and diuretics",
        "confidence_note": "high",
        "reason": "Raw form explicitly says Telmisartan + hydrochlorothiazide 40mg+12.5mg with hypertension diagnoses.",
        "apply_alias": "yes",
    },
    "cefacyl": {
        "target": "cefaclor",
        "confidence_note": "review",
        "reason": "CEFACYL 500 0.5g looks like a cephalosporin brand in infection diagnoses, but cefaclor vs another cephalosporin needs manual confirmation.",
        "apply_alias": "review",
    },
    "inbacid": {
        "target": "",
        "confidence_note": "skip",
        "reason": "INBACID 10mg occurs with hypertension/hyperlipidemia, but the name does not identify a safe KB generic.",
        "apply_alias": "review",
    },
    "vina ad": {
        "target": "",
        "confidence_note": "skip",
        "reason": "VINA-AD 2000ui+400ui appears to be vitamin A/D, but no exact single KB target is safe.",
        "apply_alias": "review",
    },
    "droxicef": {
        "target": "cefadroxil",
        "confidence_note": "high",
        "reason": "DROXICEF 0.5g name and strength strongly indicate cefadroxil; diagnoses are infection-related.",
        "apply_alias": "yes",
    },
    "bloza": {
        "target": "losartan",
        "confidence_note": "high",
        "reason": "BLOZA 50mg appears repeatedly with hypertension diagnoses; 50mg is a standard losartan strength.",
        "apply_alias": "yes",
    },
    "savilosartan": {
        "target": "losartan",
        "confidence_note": "high",
        "reason": "Candidate contains losartan and raw form is SAVILOSARTAN 50mg with hypertension diagnoses.",
        "apply_alias": "yes",
    },
    "stacetam": {
        "target": "piracetam",
        "confidence_note": "high",
        "reason": "STACETAM 800mg is consistent with piracetam 800mg; diagnoses include vascular/neurologic contexts.",
        "apply_alias": "yes",
    },
    "statripsine": {
        "target": "chymotrypsin",
        "confidence_note": "high",
        "reason": "STATRIPSINE 4.2mg appears with trauma/wound diagnoses; 4.2mg enzyme pattern matches chymotrypsin products.",
        "apply_alias": "yes",
    },
    "ebitac": {
        "target": "enalapril and diuretics",
        "confidence_note": "high",
        "reason": "EBITAC 12.5 is 10mg+12.5mg in hypertension prescriptions, fitting enalapril plus thiazide diuretic.",
        "apply_alias": "yes",
    },
    "ingaron 200 dst": {
        "target": "acetylcysteine",
        "confidence_note": "medium",
        "reason": "INGARON 200 DST 200mg appears in bronchitis/respiratory diagnoses; 200mg dispersible mucolytic pattern fits acetylcysteine.",
        "apply_alias": "yes",
    },
    "atoris": {
        "target": "atorvastatin",
        "confidence_note": "high",
        "reason": "ATORIS 20mg appears with hyperlipidemia/cardiovascular diagnoses; name and strength fit atorvastatin.",
        "apply_alias": "yes",
    },
    "kagasdine": {
        "target": "omeprazole",
        "confidence_note": "high",
        "reason": "KAGASDINE 20mg appears with reflux/gastritis diagnoses; 20mg PPI pattern fits omeprazole.",
        "apply_alias": "yes",
    },
    "leninarto": {
        "target": "atorvastatin",
        "confidence_note": "medium",
        "reason": "LENINARTO 10mg appears with hyperlipidemia/hypertension diagnoses and the name suggests an atorvastatin brand.",
        "apply_alias": "yes",
    },
    "diamicron 60 s": {
        "target": "gliclazide",
        "confidence_note": "high",
        "reason": "DIAMICRON MR 30mg/60'S appears with E11 diabetes diagnoses; Diamicron maps to gliclazide.",
        "apply_alias": "yes",
    },
    "drotaverin clohydrat": {
        "target": "drotaverine",
        "confidence_note": "high",
        "reason": "Raw form explicitly names Drotaverin clohydrat 80mg; KB generic is drotaverine.",
        "apply_alias": "yes",
    },
    "methyl prednisolon": {
        "target": "methylprednisolone",
        "confidence_note": "high",
        "reason": "Raw form explicitly names methyl prednisolon 4mg; KB generic is methylprednisolone.",
        "apply_alias": "yes",
    },
    "cardilopin": {
        "target": "Amlodipine",
        "confidence_note": "high",
        "reason": "CARDILOPIN 5mg appears with hypertension diagnoses; 5mg calcium-channel-blocker pattern fits amlodipine.",
        "apply_alias": "yes",
    },
    "cephalexin pmp": {
        "target": "cefalexin",
        "confidence_note": "high",
        "reason": "Raw form explicitly says CEPHALEXIN PMP 500 0.5g; KB stores this ATC generic as cefalexin.",
        "apply_alias": "yes",
    },
    "mezafen": {
        "target": "etoricoxib",
        "confidence_note": "review",
        "reason": "MEZAFEN 60mg appears with arthritis/joint diagnoses and could be etoricoxib 60mg, but name evidence is not strong enough for automatic aliasing.",
        "apply_alias": "review",
    },
    "pyme diapro": {
        "target": "gliclazide",
        "confidence_note": "high",
        "reason": "PYME DIAPRO MR 30mg appears with E11 diabetes diagnoses; MR 30mg matches gliclazide modified-release.",
        "apply_alias": "yes",
    },
    "troysar am": {
        "target": "losartan and amlodipine",
        "confidence_note": "high",
        "reason": "TROYSAR AM 5mg+50mg appears with hypertension diagnoses; strengths match amlodipine plus losartan.",
        "apply_alias": "yes",
    },
    "xitoran": {
        "target": "",
        "confidence_note": "skip",
        "reason": "XITORAN 0.5g is likely an antibiotic but local evidence does not distinguish cefuroxime/cefixime/other cephalosporins safely.",
        "apply_alias": "review",
    },
    "c floode": {
        "target": "ascorbic acid (vit C)",
        "confidence_note": "high",
        "reason": "Raw form is C1000 FLOODE 1g; name/strength indicate vitamin C.",
        "apply_alias": "yes",
    },
    "venrutine": {
        "target": "rutoside, combinations",
        "confidence_note": "medium",
        "reason": "VENRUTINE 100mg+500mg appears with bruising/bleeding contexts; name and combination strength fit rutoside plus vitamin C.",
        "apply_alias": "yes",
    },
    "alfachim": {
        "target": "chymotrypsin",
        "confidence_note": "high",
        "reason": "ALFACHIM 4.2mg appears with trauma/wound/inflammation diagnoses; 4.2mg enzyme pattern matches chymotrypsin.",
        "apply_alias": "yes",
    },
    "fudcime": {
        "target": "cefixime",
        "confidence_note": "high",
        "reason": "FUDCIME 200mg appears with infection diagnoses; name suffix and 200mg strength fit cefixime.",
        "apply_alias": "yes",
    },
    "golddicron": {
        "target": "gliclazide",
        "confidence_note": "high",
        "reason": "GOLDDICRON 30mg appears with E11 diabetes diagnoses; name resembles gliclazide/Diacron MR brand pattern.",
        "apply_alias": "yes",
    },
    "livonic": {
        "target": "",
        "confidence_note": "skip",
        "reason": "LIVONIC is a multi-ingredient liver/vitamin-like product; no safe single KB target.",
        "apply_alias": "review",
    },
    "saviprolol": {
        "target": "bisoprolol",
        "confidence_note": "high",
        "reason": "SAVIPROLOL 2.5mg appears with hypertension/arrhythmia diagnoses; name and strength fit bisoprolol.",
        "apply_alias": "yes",
    },
    "prazopro": {
        "target": "pantoprazole",
        "confidence_note": "high",
        "reason": "PRAZOPRO 40mg appears with gastritis diagnoses; 40mg PPI pattern fits pantoprazole.",
        "apply_alias": "yes",
    },
    "carudxan": {
        "target": "doxazosin",
        "confidence_note": "high",
        "reason": "CARUDXAN 2mg appears with BPH/urinary diagnoses; 2mg alpha-blocker pattern fits doxazosin.",
        "apply_alias": "yes",
    },
    "famogast": {
        "target": "famotidine",
        "confidence_note": "high",
        "reason": "FAMOGAST 40mg appears with reflux/gastritis diagnoses; name and strength fit famotidine.",
        "apply_alias": "yes",
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
        .head(40)
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
        confidence_note = proposal["confidence_note"]
        reason = proposal["reason"]

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


def print_table(df: pd.DataFrame) -> None:
    headers = ["candidate_drug", "proposed_generic_name", "confidence_note", "apply_alias"]
    widths = {
        "candidate_drug": 32,
        "proposed_generic_name": 34,
        "confidence_note": 15,
        "apply_alias": 11,
    }
    print(" | ".join(header.ljust(widths[header]) for header in headers))
    print("-|-".join("-" * widths[header] for header in headers))
    for row in df.itertuples(index=False):
        values = {
            "candidate_drug": row.candidate_drug,
            "proposed_generic_name": row.proposed_generic_name,
            "confidence_note": row.confidence_note,
            "apply_alias": row.apply_alias,
        }
        print(" | ".join(str(values[header]).ljust(widths[header]) for header in headers))


def main() -> None:
    proposal_df = build_proposals()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    proposal_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    safe_count = int((proposal_df["apply_alias"] == "yes").sum())
    review_count = int((proposal_df["apply_alias"] == "review").sum())
    print(f"Saved round-2 proposed aliases: {OUTPUT_CSV}")
    print(f"Total reviewed: {len(proposal_df)}")
    print(f"Safe to apply: {safe_count}")
    print(f"Needs review: {review_count}")
    print("\nRound-2 alias proposals:")
    print_table(proposal_df)


if __name__ == "__main__":
    main()
