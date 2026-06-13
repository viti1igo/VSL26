"""Map extracted prescription drugs to KB entries and structured VSL gloss sections."""

import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - fallback for minimal local envs
    fuzz = None

try:
    import requests
except ImportError:  # pragma: no cover - enrichment is optional
    requests = None


VSL_FOOTAGE = {
    "bác sĩ kê thuốc": "VSL_DOCTOR_PRESCRIBE",
    "số 1": "VSL_008_so1",
    "số 2": "VSL_008_so2",
    "số 3": "VSL_008_so3",
    "số 4": "VSL_008_so4",
    "số 5": "VSL_035_so5",
    "giảm": "VSL_004_giam",
    "nguy cơ": "VSL_NGUYEN_CO",
    "cao huyết áp": "VSL_027_cao_huyet_ap",
    "đau họng": "VSL_019_dau_hong",
    "giúp bạn": "VSL_008_giup_ban",
    "cảm thấy": "VSL_CAM_THAY",
    "dễ chịu hơn": "VSL_008_de_chiu_hon",
    "dị ứng": "VSL_DI_UNG",
    "dạ dày": "VSL_DA_DAY",
    "nhiễm khuẩn": "VSL_NHIEM_KHUAN",
    "uống": "VSL_UONG",
    "viên": "VSL_VIEN",
    "1 viên": "VSL_617_1__VSL_VIEN",
    "2 viên": "VSL_618_2__VSL_VIEN",
    "3 viên": "VSL_619_3__VSL_VIEN",
    "4 viên": "VSL_620_4__VSL_VIEN",
    "buổi sáng": "VSL_BUOI_SANG",
    "buổi tối": "VSL_971_buoi_toi",
    "buổi trưa": "VSL_973_buoi_trua",
    "buổi chiều": "VSL_967_buoi_chieu",
    "mỗi ngày": "VSL_229_moi_ngay",
    "hàng ngày": "VSL_232_hang_ngay",
    "đau đầu": "VSL_019_dau_dau",
    "đau bụng": "VSL_434_dau_bung",
    "buồn nôn": "VSL_039_buon_non",
    "tiêu chảy": "VSL_039_tieu_chay",
    "buồn ngủ": "VSL_039_buon_ngu",
    "mệt mỏi": "VSL_444_met_moi",
    "mề đay": "VSL_052_me_day",
    "phù mặt": "VSL_052_phu_mat",
    "khó thở": "VSL_TBD_kho_tho",
    "và": "VSL_VA",
    "một là": "VSL_191_mot_la",
    "hai là": "VSL_192_hai_la",
    "ba là": "VSL_193_ba_la",
    "bắt buộc": "VSL_BAT_BUOC",
    "uống hết đơn thuốc": "VSL_UONG_HET_DON_THUOC",
    "không được dừng thuốc sớm": "VSL_KHONG_DUNG_THUOC_SOM",
    "đều đặn": "VSL_TBD_deu_dan",
    "không": "VSL_TBD_khong",
    "tự ý": "VSL_TBD_tu_y",
    "ngừng thuốc": "VSL_TBD_ngung_thuoc",
    "BẮT BUỘC": "VSL_TBD_bat_buoc",
    "KHÔNG": "VSL_TBD_khong_upper",
    "uống hết": "VSL_TBD_uong_het",
    "đơn thuốc": "VSL_TBD_don_thuoc",
    "dừng thuốc sớm": "VSL_TBD_dung_thuoc_som",
    "có thể": "VSL_TBD_co_the",
    "mỗi lần uống": "VSL_TBD_moi_lan_uong",
    "cách nhau": "VSL_TBD_cach_nhau",
    "4-6 tiếng": "VSL_TBD_4_6_tieng",
    "không quá": "VSL_TBD_khong_qua",
    "uống nhiều": "VSL_TBD_uong_nhieu",
    "hại gan": "VSL_TBD_hai_gan",
    "trong quá trình": "VSL_TBD_trong_qua_trinh",
    "sử dụng thuốc": "VSL_TBD_su_dung_thuoc",
    "tác dụng phụ": "VSL_TBD_tac_dung_phu",
    "nốt đỏ": "VSL_TBD_not_do",
    "nguy hiểm": "VSL_TBD_nguy_hiem",
    "tính mạng": "VSL_TBD_tinh_mang",
    "nếu gặp": "VSL_TBD_neu_gap",
    "1 trong 3": "VSL_TBD_1_trong_3",
    "triệu chứng trên": "VSL_TBD_trieu_chung_tren",
    "1 là": "VSL_TBD_1_la",
    "2 là": "VSL_TBD_2_la",
    "3 là": "VSL_TBD_3_la",
    "dừng thuốc": "VSL_TBD_dung_thuoc",
    "ngay lập tức": "VSL_TBD_ngay_lap_tuc",
    "mang theo": "VSL_TBD_mang_theo",
    "vỏ hộp thuốc": "VSL_TBD_vo_hop_thuoc",
    "đi cấp cứu": "VSL_TBD_di_cap_cuu",
    "không chắc chắn": "VSL_TBD_khong_chac_chan",
    "hỏi": "VSL_TBD_hoi",
    "Dược sĩ": "VSL_TBD_duoc_si",
    "Bác sĩ": "VSL_TBD_bac_si",
}


DOSAGE_RE = re.compile(
    r"(?i)\b\d+(?:[.,]\d+)?\s*(?:mg|ml|g|mcg|µg|iu|%|viên|vien|gói|goi|ống|ong|chai)\b"
)


PILOT_GLOSS_SPEC = {
    "amlodipine": {
        "gloss_dung_cho": ["giảm", "nguy cơ", "cao huyết áp"],
        "gloss_luu_y": ["uống", "đều đặn", "mỗi ngày", "không", "tự ý", "ngừng thuốc"],
        "warning_template_id": "hypertension",
    },
    "enalapril": {
        "gloss_dung_cho": ["giảm", "nguy cơ", "cao huyết áp"],
        "gloss_luu_y": ["uống", "đều đặn", "mỗi ngày", "không", "tự ý", "ngừng thuốc"],
        "warning_template_id": "hypertension",
    },
    "amoxicillin": {
        "gloss_dung_cho": ["đau họng", "giảm"],
        "gloss_luu_y": ["BẮT BUỘC", "uống hết", "đơn thuốc", "KHÔNG", "dừng thuốc sớm", "có thể", "tiêu chảy"],
        "warning_template_id": "antibiotic",
    },
    "paracetamol": {
        "gloss_dung_cho": ["giúp bạn", "cảm thấy", "dễ chịu hơn"],
        "gloss_luu_y": [
            "mỗi lần uống",
            "cách nhau",
            "4-6 tiếng",
            "không quá",
            "4 viên",
            "mỗi ngày",
            "uống nhiều",
            "hại gan",
        ],
        "warning_template_id": "paracetamol",
    },
}
PILOT_ALIAS_TO_CANONICAL = {
    _normalize_alias: canonical
    for canonical, aliases in {
        "amlodipine": ["amlodipine", "amlodipin", "kavasdin", "pamlonor", "amcardia", "cardilopin", "norvasc"],
        "enalapril": ["enalapril", "ebitac", "renapril", "renitec", "ednyt"],
        "amoxicillin": ["amoxicilin", "amoxicillin", "fabamox", "ospamox", "flemoxin", "amoxil"],
        "paracetamol": [
            "paracetamol",
            "panactol",
            "partamol",
            "mypara",
            "hapacol",
            "panadol",
            "efferalgan",
            "tydol",
            "stacetam",
            "mezafen",
        ],
    }.items()
    for _normalize_alias in aliases
}


@dataclass
class DrugInfo:
    drug_id: str
    name_vn: str
    name_generic: str
    atc_code: str
    drug_class_vn: str
    illness_vn: list[str]
    illness_short_vn: str
    child_friendly_use_vn: str
    usage_timing: str
    side_effects_common: list[str]
    side_effects_severe: list[str]
    warnings: list[str]
    must_complete_course: bool
    gloss_illness_tokens: list[str]
    notes: str
    generic_name_en: str = ""
    generic_name_vn: str = ""
    contraindications_vn: list[str] | None = None
    typical_co_drugs: list[str] | None = None
    age_min_years: int = 0
    age_max_years: int = 99
    common_usage_patterns_vn: list[str] | None = None
    gloss_dung_cho: list[str] = field(default_factory=list)
    gloss_luu_y: list[str] = field(default_factory=list)
    warning_template_id: str = "default"


@dataclass
class MappingResult:
    drug_number: int
    name_extracted: str
    name_normalized: str
    match_confidence: float
    drug_info: Optional[DrugInfo]
    dosage_extracted: str
    quantity_extracted: str
    usage_extracted: str
    gloss_sections: dict[str, list[str]]
    vsl_footage_ids_by_section: dict[str, list[str]]


@dataclass
class PrescriptionMapping:
    prescription_id: str
    diagnoses_extracted: list[str]
    drugs: list[MappingResult]
    general_warnings: list[str]
    closing_message: str
    universal_closing: dict[str, Any]
    total_gloss_token_count: int
    estimated_video_duration_seconds: int


def _normalize_text(text: str) -> str:
    text = DOSAGE_RE.sub(" ", text)
    text = re.sub(r"[^\w\sÀ-ỹ-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _first_5_consistent(left: str, right: str) -> bool:
    left_compact = re.sub(r"[^a-z0-9à-ỹ]+", "", left.lower())
    right_compact = re.sub(r"[^a-z0-9à-ỹ]+", "", right.lower())
    if len(left_compact) < 5 or len(right_compact) < 5:
        return left_compact == right_compact
    return left_compact[:5] == right_compact[:5]


def _match_pilot_alias(normalized_name: str) -> tuple[str, float]:
    if normalized_name in PILOT_ALIAS_TO_CANONICAL:
        return PILOT_ALIAS_TO_CANONICAL[normalized_name], 100.0

    best_canonical = ""
    best_score = 0.0
    for alias, canonical in PILOT_ALIAS_TO_CANONICAL.items():
        if fuzz is not None:
            score = float(fuzz.token_set_ratio(normalized_name, alias))
        else:
            score = 100.0 if normalized_name == alias else 0.0
        if score > best_score and _first_5_consistent(normalized_name, alias):
            best_canonical = canonical
            best_score = score

    if best_score >= 85.0:
        return best_canonical, best_score
    return "", 0.0


def _extract_dosage(text: str) -> str:
    return " ".join(match.group(0).strip() for match in DOSAGE_RE.finditer(text))


def _canonical_pilot_drug_key(raw: dict[str, Any]) -> str | None:
    candidates = [
        str(raw.get("drug_id", "")),
        str(raw.get("name_generic", "")),
        str(raw.get("generic_name_en", "")),
        str(raw.get("name_vn", "")),
    ]
    normalized_candidates = {_normalize_text(candidate) for candidate in candidates if candidate}
    for canonical in PILOT_GLOSS_SPEC:
        if canonical in normalized_candidates:
            return canonical
    return None


def _apply_pilot_gloss_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    raw = dict(raw)
    canonical = _canonical_pilot_drug_key(raw)
    if canonical:
        raw.update(PILOT_GLOSS_SPEC[canonical])
    else:
        raw.setdefault("gloss_dung_cho", list(raw.get("gloss_illness_tokens") or ["giúp bạn"]))
        raw.setdefault("gloss_luu_y", list(raw.get("warnings") or []))
        raw.setdefault("warning_template_id", "default")
    return raw


LIST_TEXT_FIELDS = {
    "illness_vn",
    "side_effects_common",
    "side_effects_severe",
    "warnings",
    "gloss_illness_tokens",
    "contraindications_vn",
    "typical_co_drugs",
    "common_usage_patterns_vn",
    "gloss_dung_cho",
    "gloss_luu_y",
}


def _coerce_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        text = str(value).strip()
        return [text] if text else []

    result = []
    for item in value:
        if isinstance(item, list):
            result.extend(_coerce_text_list(item))
            continue
        if isinstance(item, dict):
            text = next(
                (
                    str(item[key]).strip()
                    for key in ("token", "text", "gloss", "phrase", "name", "label")
                    if item.get(key)
                ),
                "",
            )
            if not text:
                text = json.dumps(item, ensure_ascii=False)
        else:
            text = str(item).strip()
        if text:
            result.append(text)
    return result


def _drug_from_json(data: str | dict[str, Any]) -> DrugInfo:
    raw = json.loads(data) if isinstance(data, str) else data
    raw = _apply_pilot_gloss_defaults(raw)
    for field_name in LIST_TEXT_FIELDS:
        if field_name in raw:
            raw[field_name] = _coerce_text_list(raw[field_name])
    if "must_complete_course" in raw and isinstance(raw["must_complete_course"], str):
        raw["must_complete_course"] = raw["must_complete_course"].strip().lower() in {
            "true",
            "yes",
            "1",
            "có",
        }
    allowed_fields = {item.name for item in fields(DrugInfo)}
    return DrugInfo(**{key: value for key, value in raw.items() if key in allowed_fields})


def build_drug_gloss_sections(
    drug_number: int,
    drug: DrugInfo,
    usage: str,
    quantity: str,
) -> dict[str, list[str]]:
    """
    Build the three drug-specific gloss sections from the pilot spreadsheet template.
    """
    return {
        "dung_cho": ["bác sĩ kê thuốc", f"số {drug_number}", *drug.gloss_dung_cho],
        "dung_nhu_nao": _build_usage_gloss_tokens(usage, quantity),
        "luu_y": list(drug.gloss_luu_y),
    }


def build_universal_closing() -> dict[str, Any]:
    """
    Returns the universal allergy + safety closing tokens.
    """
    return {
        "tac_dung_phu_cluster": [
            "trong quá trình",
            "sử dụng thuốc",
            "có thể",
            "tác dụng phụ",
            "dị ứng",
            "mề đay",
            "nốt đỏ",
            "phù mặt",
            "khó thở",
            "nguy hiểm",
            "tính mạng",
        ],
        "if_one_of_three": ["nếu gặp", "1 trong 3", "triệu chứng trên"],
        "actions": [
            ["1 là", "dừng thuốc", "ngay lập tức"],
            ["2 là", "mang theo", "vỏ hộp thuốc", "đi cấp cứu"],
            ["3 là", "không chắc chắn", "hỏi", "Dược sĩ", "Bác sĩ"],
        ],
    }


def _build_usage_gloss_tokens(usage: str, quantity: str) -> list[str]:
    usage_lower = usage.lower()
    quantity_lower = quantity.lower()
    tokens = ["uống"]
    matches = re.findall(r"(\d+)\s*viên", usage_lower)
    if not matches and _quantity_can_be_per_dose(quantity_lower):
        matches = re.findall(r"(\d+)\s*viên", quantity_lower)
    time_tokens = [
        ("sáng", "buổi sáng"),
        ("trưa", "buổi trưa"),
        ("chiều", "buổi chiều"),
        ("tối", "buổi tối"),
    ]
    present_times = [token for marker, token in time_tokens if marker in usage_lower]
    if not present_times:
        present_times = [token for marker, token in time_tokens if marker in quantity_lower]
    fallback_quantity = f"{quantity.strip()} viên" if quantity.strip().isdigit() else ""

    if present_times:
        for index, time_token in enumerate(present_times):
            if index > 0:
                tokens.append("và")
            dose = f"{matches[index]} viên" if index < len(matches) else fallback_quantity
            if dose:
                tokens.append(dose)
            tokens.append(time_token)
    else:
        dose = f"{matches[0]} viên" if matches else fallback_quantity
        if dose:
            tokens.append(dose)

    tokens.append("mỗi ngày")
    return tokens


def _quantity_can_be_per_dose(quantity_lower: str) -> bool:
    if any(marker in quantity_lower for marker in ("sl", "số lượng", "so luong", "tổng", "tong")):
        return False
    matches = re.findall(r"(\d+)\s*viên", quantity_lower)
    return bool(matches) and int(matches[0]) <= 4


class DrugKnowledgeBase:
    def __init__(self, db_path: str = "vaipe_drugs.db"):
        self.db_path = Path(db_path)
        self._init_db()
        self._seed_if_empty()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drugs (
                    drug_id TEXT PRIMARY KEY,
                    name_vn TEXT NOT NULL,
                    name_generic TEXT NOT NULL,
                    atc_code TEXT,
                    data_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drug_aliases (
                    alias TEXT PRIMARY KEY,
                    drug_id TEXT NOT NULL,
                    FOREIGN KEY (drug_id) REFERENCES drugs(drug_id)
                )
                """
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
        if count:
            return

        for drug, aliases in _seed_drugs():
            self.add_drug(drug, aliases)

    def add_drug(self, drug_info: DrugInfo, aliases: list[str] | None = None) -> None:
        aliases = aliases or []
        data_json = json.dumps(asdict(drug_info), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO drugs (drug_id, name_vn, name_generic, atc_code, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    drug_info.drug_id,
                    drug_info.name_vn,
                    drug_info.name_generic,
                    drug_info.atc_code,
                    data_json,
                ),
            )
            for alias in {drug_info.drug_id, drug_info.name_vn, drug_info.name_generic, *aliases}:
                normalized = _normalize_text(alias)
                if normalized:
                    conn.execute(
                        "INSERT OR REPLACE INTO drug_aliases (alias, drug_id) VALUES (?, ?)",
                        (normalized, drug_info.drug_id),
                    )

    def get_drug(self, drug_id: str) -> Optional[DrugInfo]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM drugs WHERE drug_id = ?",
                (drug_id,),
            ).fetchone()
        return _drug_from_json(row[0]) if row else None

    def match_drug(self, name: str, threshold: float = 70.0) -> tuple[Optional[DrugInfo], str, float]:
        normalized = _normalize_text(name)
        if not normalized:
            return None, "", 0.0

        pilot_drug_id, pilot_score = _match_pilot_alias(normalized)
        if pilot_drug_id:
            drug = self.get_drug(pilot_drug_id)
            if drug:
                return drug, drug.name_vn, pilot_score

        with self._connect() as conn:
            row = conn.execute(
                "SELECT drug_id FROM drug_aliases WHERE alias = ?",
                (normalized,),
            ).fetchone()
            if row:
                drug = self.get_drug(row[0])
                return drug, drug.name_vn if drug else row[0], 100.0

            aliases = conn.execute("SELECT alias, drug_id FROM drug_aliases").fetchall()

        best_alias = ""
        best_drug_id = ""
        best_score = 0.0
        for alias, drug_id in aliases:
            if fuzz is not None:
                score = float(fuzz.token_sort_ratio(normalized, alias))
            else:
                score = 100.0 if normalized == alias else 0.0
            if score > best_score:
                best_alias = alias
                best_drug_id = drug_id
                best_score = score

        if best_score >= threshold and best_drug_id:
            drug = self.get_drug(best_drug_id)
            return drug, drug.name_vn if drug else best_alias, best_score

        return None, normalized, best_score


class MedicineMapper:
    def __init__(
        self,
        db_path: str = "vaipe_drugs.db",
        auto_enrich: bool = False,
        match_threshold: float = 70.0,
    ):
        self.kb = DrugKnowledgeBase(db_path)
        self.auto_enrich = auto_enrich
        self.match_threshold = match_threshold

    def map_prescription(self, prescription_id: str, ner_output: dict[str, Any]) -> PrescriptionMapping:
        diagnoses = list(ner_output.get("diagnoses", []))
        mapped_drugs: list[MappingResult] = []
        general_warnings: list[str] = []
        universal_closing = build_universal_closing()

        for index, drug_item in enumerate(ner_output.get("drugs", []), start=1):
            name = str(drug_item.get("name", "")).strip()
            quantity = str(drug_item.get("quantity", "")).strip()
            usage = str(drug_item.get("usage", "")).strip()
            dosage = _extract_dosage(name)

            drug_info, normalized_name, confidence = self.kb.match_drug(name, self.match_threshold)
            if drug_info is None and self.auto_enrich:
                try:
                    drug_info = self.enrich_drug_with_llm(name)
                except Exception:
                    drug_info = None
                if drug_info:
                    self.kb.add_drug(drug_info, aliases=[name])
                    normalized_name = drug_info.name_vn
                    confidence = 70.0

            if drug_info and drug_info.must_complete_course:
                general_warnings.extend(
                    ["Bắt buộc uống hết đơn thuốc.", "Không được dừng thuốc sớm."]
                )

            gloss_sections = self._build_gloss_sections(index, drug_info, quantity, usage)
            mapped_drugs.append(
                MappingResult(
                    drug_number=index,
                    name_extracted=name,
                    name_normalized=normalized_name,
                    match_confidence=round(confidence, 2),
                    drug_info=drug_info,
                    dosage_extracted=dosage,
                    quantity_extracted=quantity,
                    usage_extracted=usage,
                    gloss_sections=gloss_sections,
                    vsl_footage_ids_by_section=self._lookup_footage_by_section(gloss_sections),
                )
            )

        total_tokens = _count_gloss_tokens(mapped_drugs, universal_closing)
        return PrescriptionMapping(
            prescription_id=prescription_id,
            diagnoses_extracted=diagnoses,
            drugs=mapped_drugs,
            general_warnings=list(dict.fromkeys(general_warnings)),
            closing_message="Con hãy uống thuốc đúng như bác sĩ dặn. Nếu thấy khó chịu, hãy báo cho người lớn.",
            universal_closing=universal_closing,
            total_gloss_token_count=total_tokens,
            estimated_video_duration_seconds=round(total_tokens * 1.2),
        )

    def _build_gloss_sections(
        self,
        drug_number: int,
        drug_info: Optional[DrugInfo],
        quantity: str,
        usage: str,
    ) -> dict[str, list[str]]:
        if drug_info is None:
            fallback = DrugInfo(
                drug_id="unknown",
                name_vn="",
                name_generic="",
                atc_code="",
                drug_class_vn="",
                illness_vn=[],
                illness_short_vn="",
                child_friendly_use_vn="",
                usage_timing="",
                side_effects_common=[],
                side_effects_severe=[],
                warnings=[],
                must_complete_course=False,
                gloss_illness_tokens=["giúp bạn"],
                notes="",
                gloss_dung_cho=["giúp bạn"],
                gloss_luu_y=[],
                warning_template_id="default",
            )
            return build_drug_gloss_sections(drug_number, fallback, usage, quantity)
        return build_drug_gloss_sections(drug_number, drug_info, usage, quantity)

    def _parse_quantity_tokens(self, quantity: str, usage: str) -> list[str]:
        text = f"{quantity} {usage}".lower()
        matches = re.findall(r"(\d+)\s*viên", text)
        if matches:
            return [f"{matches[0]} viên"]
        if quantity.strip().isdigit():
            return [f"{quantity.strip()} viên"]
        return []

    def _parse_usage_tokens(self, usage: str) -> list[str]:
        usage_lower = usage.lower()
        tokens = []
        if "sáng" in usage_lower:
            tokens.append("buổi sáng")
        if "trưa" in usage_lower:
            tokens.append("buổi trưa")
        if "chiều" in usage_lower:
            tokens.append("buổi chiều")
        if "tối" in usage_lower:
            tokens.append("buổi tối")
        return tokens

    def _lookup_footage(self, gloss_sequence: list[str]) -> list[str]:
        return [
            VSL_FOOTAGE.get(str(token), f"VSL_MISSING:{token}")
            for token in gloss_sequence
        ]

    def _lookup_footage_by_section(
        self,
        gloss_sections: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        return {
            section: self._lookup_footage(tokens)
            for section, tokens in gloss_sections.items()
        }

    def enrich_drug_with_llm(
        self,
        drug_name: str | None = None,
        *,
        name_en: str | None = None,
        atc_code: str = "",
        only_translate: bool = False,
    ) -> Optional[DrugInfo] | str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        if only_translate:
            prompt = _drug_translation_prompt(name_en or drug_name or "", atc_code)
            max_tokens = 120
        else:
            prompt = _drug_enrichment_prompt(drug_name or name_en or "")
            max_tokens = 1200

        content = _extract_openai_output_text(
            _post_openai_responses(
                api_key=api_key,
                payload={
                    "model": os.getenv("OPENAI_MODEL", "gpt-5.4"),
                    "input": prompt,
                    "max_output_tokens": max_tokens,
                },
                timeout=60,
            )
        )
        if only_translate:
            return content.strip().strip('"').strip()

        json_text = _extract_json_object(content)
        return _drug_from_json(json.loads(json_text))

    def to_json(self, mapping: PrescriptionMapping) -> str:
        return json.dumps(asdict(mapping), ensure_ascii=False, indent=2)


def _dedupe_preserve_order(tokens: list[str]) -> list[str]:
    result = []
    for token in tokens:
        if token and (not result or result[-1] != token):
            result.append(token)
    return result


def _count_tokens_in_closing(universal_closing: dict[str, Any]) -> int:
    total = 0
    for value in universal_closing.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, list):
                    total += len(item)
                else:
                    total += 1
    return total


def _count_gloss_tokens(
    mapped_drugs: list[MappingResult],
    universal_closing: dict[str, Any],
) -> int:
    drug_tokens = sum(
        len(tokens)
        for drug in mapped_drugs
        for tokens in drug.gloss_sections.values()
    )
    return drug_tokens + _count_tokens_in_closing(universal_closing)


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object")
    return text[start : end + 1]


def _extract_openai_output_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])

    parts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts)


def _post_openai_responses(
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout: int = 60,
) -> dict[str, Any]:
    if requests is not None:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed: {exc.code} {error_body}") from exc


def _drug_enrichment_prompt(drug_name: str) -> str:
    return f"""
Trả về duy nhất một JSON object cho thuốc "{drug_name}" theo schema DrugInfo.
Tất cả trường tiếng Việt phải ngắn, đơn giản, phù hợp cho trẻ khiếm thính.
Các khóa bắt buộc: drug_id, name_vn, name_generic, atc_code, drug_class_vn,
illness_vn, illness_short_vn, child_friendly_use_vn, usage_timing,
side_effects_common, side_effects_severe, warnings, must_complete_course,
gloss_illness_tokens, gloss_dung_cho, gloss_luu_y, warning_template_id, notes.
	"""


def _drug_translation_prompt(name_en: str, atc_code: str = "") -> str:
    return f"""
Dịch tên hoạt chất thuốc sau sang tên tiếng Việt thông dụng nếu có.
Chỉ trả về đúng một dòng là tên tiếng Việt, không giải thích.
Tên tiếng Anh: {name_en}
Mã ATC: {atc_code}
"""


def _seed_drugs() -> list[tuple[DrugInfo, list[str]]]:
    return [
        (
            DrugInfo(
                drug_id="amlodipine",
                name_vn="Amlodipin",
                name_generic="Amlodipine",
                atc_code="C08CA01",
                drug_class_vn="Thuốc hạ huyết áp",
                illness_vn=["Tăng huyết áp", "Cao huyết áp"],
                illness_short_vn="cao huyết áp",
                child_friendly_use_vn="Thuốc giúp giảm nguy cơ do cao huyết áp.",
                usage_timing="bất kỳ lúc nào",
                side_effects_common=["đau đầu", "phù chân", "mệt mỏi"],
                side_effects_severe=["phù mặt", "khó thở"],
                warnings=["Uống đúng giờ mỗi ngày."],
                must_complete_course=False,
                gloss_illness_tokens=["giảm", "nguy cơ", "cao huyết áp"],
                notes="Calcium channel blocker.",
                gloss_dung_cho=["giảm", "nguy cơ", "cao huyết áp"],
                gloss_luu_y=["uống", "đều đặn", "mỗi ngày", "không", "tự ý", "ngừng thuốc"],
                warning_template_id="hypertension",
            ),
            ["amlodipin", "amlodipine", "amlodipin 5mg", "amlodipine 5mg"],
        ),
        (
            DrugInfo(
                drug_id="enalapril",
                name_vn="Enalapril",
                name_generic="Enalapril",
                atc_code="C09AA02",
                drug_class_vn="Thuốc hạ huyết áp",
                illness_vn=["Tăng huyết áp", "Cao huyết áp"],
                illness_short_vn="cao huyết áp",
                child_friendly_use_vn="Thuốc giúp giảm nguy cơ do cao huyết áp.",
                usage_timing="bất kỳ lúc nào",
                side_effects_common=["ho", "chóng mặt", "mệt mỏi"],
                side_effects_severe=["phù mặt", "khó thở"],
                warnings=["Báo người lớn nếu chóng mặt nhiều."],
                must_complete_course=False,
                gloss_illness_tokens=["giảm", "nguy cơ", "cao huyết áp"],
                notes="ACE inhibitor.",
                gloss_dung_cho=["giảm", "nguy cơ", "cao huyết áp"],
                gloss_luu_y=["uống", "đều đặn", "mỗi ngày", "không", "tự ý", "ngừng thuốc"],
                warning_template_id="hypertension",
            ),
            ["enalapril", "enalapril 5mg"],
        ),
        (
            DrugInfo(
                drug_id="amoxicillin",
                name_vn="Amoxicillin",
                name_generic="Amoxicillin",
                atc_code="J01CA04",
                drug_class_vn="Kháng sinh",
                illness_vn=["Viêm họng", "Nhiễm khuẩn"],
                illness_short_vn="đau họng",
                child_friendly_use_vn="Thuốc giúp giảm đau họng do vi khuẩn.",
                usage_timing="sau ăn",
                side_effects_common=["đau bụng", "tiêu chảy", "buồn nôn"],
                side_effects_severe=["mề đay", "phù mặt", "khó thở"],
                warnings=["Uống đủ ngày theo đơn.", "Không tự dừng thuốc sớm."],
                must_complete_course=True,
                gloss_illness_tokens=["đau họng", "giảm"],
                notes="Penicillin antibiotic.",
                gloss_dung_cho=["đau họng", "giảm"],
                gloss_luu_y=["BẮT BUỘC", "uống hết", "đơn thuốc", "KHÔNG", "dừng thuốc sớm", "có thể", "tiêu chảy"],
                warning_template_id="antibiotic",
            ),
            ["amoxicillin", "amoxicilin", "amoxicillin 500mg", "amox"],
        ),
        (
            DrugInfo(
                drug_id="paracetamol",
                name_vn="Paracetamol",
                name_generic="Paracetamol",
                atc_code="N02BE01",
                drug_class_vn="Thuốc giảm đau hạ sốt",
                illness_vn=["Đau", "Sốt"],
                illness_short_vn="đau hoặc sốt",
                child_friendly_use_vn="Thuốc giúp con cảm thấy dễ chịu hơn khi đau hoặc sốt.",
                usage_timing="sau ăn",
                side_effects_common=["buồn nôn", "đau bụng"],
                side_effects_severe=["mẩn ngứa", "khó thở"],
                warnings=["Không uống quá liều."],
                must_complete_course=False,
                gloss_illness_tokens=["giúp bạn", "cảm thấy", "dễ chịu hơn"],
                notes="Analgesic and antipyretic.",
                gloss_dung_cho=["giúp bạn", "cảm thấy", "dễ chịu hơn"],
                gloss_luu_y=[
                    "mỗi lần uống",
                    "cách nhau",
                    "4-6 tiếng",
                    "không quá",
                    "4 viên",
                    "mỗi ngày",
                    "uống nhiều",
                    "hại gan",
                ],
                warning_template_id="paracetamol",
            ),
            ["paracetamol", "acetaminophen", "paracetamol 500mg", "para"],
        ),
        (
            DrugInfo(
                drug_id="cetirizine",
                name_vn="Cetirizin",
                name_generic="Cetirizine",
                atc_code="R06AE07",
                drug_class_vn="Thuốc chống dị ứng",
                illness_vn=["Dị ứng", "Viêm mũi dị ứng"],
                illness_short_vn="dị ứng",
                child_friendly_use_vn="Thuốc giúp giảm ngứa, hắt hơi hoặc chảy mũi do dị ứng.",
                usage_timing="bất kỳ lúc nào",
                side_effects_common=["buồn ngủ", "mệt mỏi", "khô miệng"],
                side_effects_severe=["khó thở", "phù mặt"],
                warnings=["Có thể buồn ngủ."],
                must_complete_course=False,
                gloss_illness_tokens=["dị ứng", "giảm"],
                notes="Second-generation antihistamine.",
            ),
            ["cetirizine", "cetirizin", "zyrtec"],
        ),
        (
            DrugInfo(
                drug_id="loratadine",
                name_vn="Loratadin",
                name_generic="Loratadine",
                atc_code="R06AX13",
                drug_class_vn="Thuốc chống dị ứng",
                illness_vn=["Dị ứng", "Viêm mũi dị ứng"],
                illness_short_vn="dị ứng",
                child_friendly_use_vn="Thuốc giúp giảm triệu chứng dị ứng.",
                usage_timing="bất kỳ lúc nào",
                side_effects_common=["đau đầu", "mệt mỏi"],
                side_effects_severe=["khó thở", "phù mặt"],
                warnings=["Uống đúng liều."],
                must_complete_course=False,
                gloss_illness_tokens=["dị ứng", "giảm"],
                notes="Second-generation antihistamine.",
            ),
            ["loratadine", "loratadin", "claritin"],
        ),
        (
            DrugInfo(
                drug_id="omeprazole",
                name_vn="Omeprazol",
                name_generic="Omeprazole",
                atc_code="A02BC01",
                drug_class_vn="Thuốc dạ dày",
                illness_vn=["Đau dạ dày", "Trào ngược"],
                illness_short_vn="đau dạ dày",
                child_friendly_use_vn="Thuốc giúp bụng và dạ dày dễ chịu hơn.",
                usage_timing="trước ăn",
                side_effects_common=["đau bụng", "buồn nôn", "đau đầu"],
                side_effects_severe=["tiêu chảy nặng", "mẩn ngứa"],
                warnings=["Thường uống trước khi ăn."],
                must_complete_course=False,
                gloss_illness_tokens=["dạ dày", "dễ chịu hơn"],
                notes="Proton pump inhibitor.",
            ),
            ["omeprazole", "omeprazol", "losec"],
        ),
        (
            DrugInfo(
                drug_id="azithromycin",
                name_vn="Azithromycin",
                name_generic="Azithromycin",
                atc_code="J01FA10",
                drug_class_vn="Kháng sinh",
                illness_vn=["Nhiễm khuẩn", "Viêm họng"],
                illness_short_vn="nhiễm khuẩn",
                child_friendly_use_vn="Thuốc giúp giảm bệnh do vi khuẩn.",
                usage_timing="bất kỳ lúc nào",
                side_effects_common=["đau bụng", "tiêu chảy", "buồn nôn"],
                side_effects_severe=["mề đay", "phù mặt", "khó thở"],
                warnings=["Uống đủ ngày theo đơn.", "Không tự dừng thuốc sớm."],
                must_complete_course=True,
                gloss_illness_tokens=["nhiễm khuẩn", "giảm"],
                notes="Macrolide antibiotic.",
            ),
            ["azithromycin", "azithromycine", "zithromax"],
        ),
    ]


def _sample_ner_output() -> dict[str, Any]:
    return {
        "diagnoses": ["Tăng huyết áp", "Viêm họng cấp"],
        "drugs": [
            {"name": "Amlodipin 5mg", "quantity": "1", "usage": "Uống mỗi ngày 1 viên vào buổi sáng"},
            {"name": "Enalapril 5mg", "quantity": "1", "usage": "Uống mỗi ngày 1 viên vào buổi tối"},
            {
                "name": "Amoxicillin 500mg",
                "quantity": "4",
                "usage": "Uống mỗi ngày 2 viên vào buổi sáng và 2 viên vào buổi tối",
            },
            {
                "name": "Paracetamol 500mg",
                "quantity": "2",
                "usage": "Uống mỗi ngày 1 viên vào buổi sáng và 1 viên vào buổi tối",
            },
        ],
    }


def main() -> None:
    mapper = MedicineMapper(db_path="vaipe_drugs.db", auto_enrich=False)
    result = mapper.map_prescription("rx_demo_001", _sample_ner_output())
    print(mapper.to_json(result))


if __name__ == "__main__":
    main()
