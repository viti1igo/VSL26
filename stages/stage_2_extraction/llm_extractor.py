"""Extract prescription entities directly from an image using a vision LLM."""

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - only needed for live API calls
    requests = None


DEFAULT_VISION_MODEL = "gpt-5.4"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ENV_PATH = REPO_ROOT / ".env"

PRESCRIPTION_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "date",
        "diagnose",
        "drugs",
        "warnings",
        "unreadable_regions",
        "overall_confidence",
    ],
    "properties": {
        "date": {
            "type": "string",
            "description": "Prescription date exactly as visible, or empty string if absent.",
        },
        "diagnose": {
            "type": "string",
            "description": "Diagnosis text exactly as visible, or empty string if absent.",
        },
        "drugs": {
            "type": "array",
            "description": "One item per prescribed medicine.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "strength",
                    "quantity",
                    "usage",
                    "timing",
                    "duration",
                    "evidence_text",
                    "confidence",
                ],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Drug name or brand name exactly as visible.",
                    },
                    "strength": {
                        "type": "string",
                        "description": "Strength/dosage form such as 500mg, 5mg, or empty string.",
                    },
                    "quantity": {
                        "type": "string",
                        "description": "Total quantity dispensed, exactly as visible, or empty string.",
                    },
                    "usage": {
                        "type": "string",
                        "description": "How to take/use the medicine, exactly as visible.",
                    },
                    "timing": {
                        "type": "string",
                        "description": "Timing/frequency summary from visible text, or empty string.",
                    },
                    "duration": {
                        "type": "string",
                        "description": "Treatment duration if visible, or empty string.",
                    },
                    "evidence_text": {
                        "type": "string",
                        "description": "Visible prescription text that supports this drug item.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Model confidence from 0.0 to 1.0.",
                    },
                },
            },
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Visible warning/instruction text, not inferred medical advice.",
        },
        "unreadable_regions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short notes about image regions the model could not read.",
        },
        "overall_confidence": {
            "type": "number",
            "description": "Overall extraction confidence from 0.0 to 1.0.",
        },
    },
}


SYSTEM_PROMPT = """
You extract structured information from Vietnamese medical prescription images.
Only extract text that is visible in the image. Do not infer diagnosis, dosage,
quantity, timing, duration, warnings, or drug purpose from medical knowledge.
Preserve Vietnamese diacritics when visible. If a field is missing or unreadable,
return an empty string for that field and mention the issue in unreadable_regions.
"""


USER_PROMPT = """
Extract the prescription entities needed for a Vietnamese prescription-to-VSL
pipeline. Focus on these labels: date, diagnose, drug name, drug strength,
quantity, usage, timing, duration, and visible warnings.

Rules:
- Return one drug object per medicine line.
- Keep brand names as written; do not convert to generic names.
- Do not add medical explanations or drug purposes.
- evidence_text must quote/summarize the visible text used for that drug item.
- If you are uncertain, keep the field empty and lower confidence.
"""


PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")
LEADING_ENUMERATION_RE = re.compile(r"^\s*\d+\s*[\).\:-]?\s*")


def load_project_env(env_path: str | Path = PROJECT_ENV_PATH) -> None:
    """Load simple KEY=VALUE lines from the project .env without overriding env vars."""
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _clean_drug_name_for_mapper(name: str, strength: str) -> str:
    """Keep a mapper-friendly primary drug name while preserving raw evidence elsewhere."""
    primary = LEADING_ENUMERATION_RE.sub("", name).strip()
    primary = PARENTHETICAL_RE.sub(" ", primary)
    primary = re.sub(r"\bdưới\s+dạng\b", " ", primary, flags=re.IGNORECASE)
    primary = re.sub(r"\s+", " ", primary).strip(" ,.;:-")
    if strength and strength.lower() not in primary.lower():
        primary = f"{primary} {strength}".strip()
    return primary or name.strip()


def _image_data_url(image_path: Path) -> str:
    mime_type, _encoding = mimetypes.guess_type(str(image_path))
    if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        suffix = image_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            mime_type = "image/jpeg"
        elif suffix == ".png":
            mime_type = "image/png"
        elif suffix == ".webp":
            mime_type = "image/webp"
        else:
            raise ValueError(f"Unsupported image type for vision extraction: {image_path}")

    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_openai_output_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])

    parts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts)


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Vision LLM response did not contain a JSON object")
    return stripped[start : end + 1]


def _post_openai_responses(
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    max_retries: int = 3,
) -> dict[str, Any]:
    retryable_statuses = {408, 409, 429, 500, 502, 503, 504, 520}
    last_error: Exception | None = None
    if requests is not None:
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    OPENAI_RESPONSES_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_seconds,
                )
                if response.status_code in retryable_statuses and attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                if attempt >= max_retries:
                    raise
                time.sleep(2**attempt)
        if last_error:
            raise last_error

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"OpenAI API request failed: {exc.code} {error_body}")
            if exc.code not in retryable_statuses or attempt >= max_retries:
                raise last_error from exc
            time.sleep(2**attempt)
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            time.sleep(2**attempt)
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI API request failed for an unknown reason")


def extract_prescription_with_vlm(
    image_path: str | Path,
    *,
    model: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """
    Extract prescription fields directly from an image with a vision LLM.

    Requires OPENAI_API_KEY in the environment. The model can be overridden with
    OPENAI_VISION_MODEL or the model argument.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Prescription image not found: {path}")

    load_project_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it before running the VLM extractor."
        )

    selected_model = model or os.getenv("OPENAI_VISION_MODEL", DEFAULT_VISION_MODEL)
    payload = {
        "model": selected_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT.strip()}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": USER_PROMPT.strip()},
                    {
                        "type": "input_image",
                        "image_url": _image_data_url(path),
                        "detail": "high",
                    },
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "vietnamese_prescription_extraction",
                "schema": PRESCRIPTION_EXTRACTION_SCHEMA,
                "strict": True,
            }
        },
    }
    content = _extract_openai_output_text(
        _post_openai_responses(
            api_key=api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
    )
    extraction = json.loads(_extract_json_object(content))
    extraction["_meta"] = {
        "method": "vlm_direct_extraction",
        "model": selected_model,
        "image_path": str(path),
    }
    return extraction


def vlm_extraction_to_mapper_input(extraction: dict[str, Any]) -> dict[str, Any]:
    """Convert VLM extraction JSON into the mapper input shape."""
    diagnose = str(extraction.get("diagnose", "")).strip()
    drugs = []
    entities = []

    if diagnose:
        entities.append({"label": "diagnose", "text": diagnose, "box": None})

    date = str(extraction.get("date", "")).strip()
    if date:
        entities.append({"label": "date", "text": date, "box": None})

    for item in extraction.get("drugs", []):
        if not isinstance(item, dict):
            continue

        name_parts = [
            _clean_drug_name_for_mapper(
                str(item.get("name", "")).strip(),
                str(item.get("strength", "")).strip(),
            ),
        ]
        name = " ".join(part for part in name_parts if part).strip()
        quantity = str(item.get("quantity", "")).strip()
        usage_parts = [
            str(item.get("usage", "")).strip(),
            str(item.get("timing", "")).strip(),
            str(item.get("duration", "")).strip(),
        ]
        usage = " ".join(part for part in usage_parts if part).strip()

        if not name:
            continue

        drugs.append(
            {
                "name": name,
                "quantity": quantity,
                "usage": usage,
                "evidence_text": str(item.get("evidence_text", "")).strip(),
                "confidence": item.get("confidence", 0.0),
            }
        )
        entities.append({"label": "drugname", "text": name, "box": None})
        if quantity:
            entities.append({"label": "quantity", "text": quantity, "box": None})
        if usage:
            entities.append({"label": "usage", "text": usage, "box": None})

    raw_groups = {
        "date": [date] if date else [],
        "diagnose": [diagnose] if diagnose else [],
        "drugname": [drug["name"] for drug in drugs],
        "quantity": [drug["quantity"] for drug in drugs if drug.get("quantity")],
        "usage": [drug["usage"] for drug in drugs if drug.get("usage")],
    }

    return {
        "diagnoses": [diagnose] if diagnose else [],
        "drugs": drugs,
        "raw_groups": raw_groups,
        "raw_groups_pre_cleanup": raw_groups,
        "raw_entities_pre_cleanup": entities,
        "entities": entities,
        "spatial_associations": [],
        "cleanup_applied": [],
        "source": "vlm_direct_extraction",
        "vlm_meta": extraction.get("_meta", {}),
        "vlm_warnings": extraction.get("warnings", []),
        "vlm_unreadable_regions": extraction.get("unreadable_regions", []),
        "vlm_overall_confidence": extraction.get("overall_confidence", 0.0),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run VLM prescription extraction on one image.")
    parser.add_argument("--image", required=True, help="Path to a prescription image.")
    parser.add_argument("--model", default=None, help="Override OPENAI_VISION_MODEL.")
    args = parser.parse_args()

    extraction = extract_prescription_with_vlm(args.image, model=args.model)
    print(json.dumps(extraction, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
