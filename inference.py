"""Run LayoutLMv3 prescription NER inference and parse entities for mapping."""

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
os.environ.setdefault("TORCH_DISABLE_DYNAMO", "1")

import torch
from PIL import Image

# In this macOS venv, importlib.metadata.packages_distributions() can hang
# scanning package metadata after OCR dependency installs. Transformers only uses
# this for optional package origin checks, so disable the expensive scan.
try:
    import importlib.metadata as _importlib_metadata

    _importlib_metadata.packages_distributions = lambda: {}
except Exception:
    pass

from transformers import LayoutLMv3ForTokenClassification, LayoutLMv3Processor


PRESCRIPTION_LABELS = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
ID2LABEL = {i: label for i, label in enumerate(PRESCRIPTION_LABELS)}
LABEL2ID = {label: i for i, label in enumerate(PRESCRIPTION_LABELS)}

REPO_ROOT = Path(__file__).resolve().parent
CHECKPOINT_PATH = REPO_ROOT / "models"
MAX_LENGTH = 224
DEFAULT_WINDOW_SIZE = 192
DEFAULT_STRIDE = 128
ROW_TOLERANCE_PX = 50
ENUMERATION_PREFIX_RE = re.compile(r"^[\(\s]*\d+\s*[\)\.\-:][\s]*")
PURE_ENUMERATION_RE = re.compile(r"^[\(\s]*\d+\s*[\)\.\-:]?[\s]*$")
PURE_DOSAGE_RE = re.compile(
    r"^\s*\d+(?:[\.,]\d+)?\s*(?:mg|g|ml|mcg|iu|%|viên|gói|ống)\s*$",
    re.IGNORECASE,
)
ALPHA_RE = re.compile(r"[A-Za-zÀ-ỹ]", re.UNICODE)
DIGIT_RE = re.compile(r"\d")


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _clamp_box(box: list[int]) -> list[int]:
    return [max(0, min(1000, int(coord))) for coord in box]


def _normalize_box(box: list[int], width: int, height: int) -> list[int]:
    """Normalize raw pixel boxes to LayoutLM's [0, 1000] coordinate space."""
    if len(box) != 4:
        raise ValueError(f"Bounding box must have 4 coordinates, got: {box}")

    width = max(width, 1)
    height = max(height, 1)
    return _clamp_box(
        [
            int(box[0] * 1000 / width),
            int(box[1] * 1000 / height),
            int(box[2] * 1000 / width),
            int(box[3] * 1000 / height),
        ]
    )


def _prepare_boxes(boxes: list[list[int]], width: int, height: int) -> list[list[int]]:
    """
    Accept raw pixel boxes and normalize them to [0, 1000].

    If annotations already look normalized and exceed the image dimensions, clamp
    rather than scale again. This preserves VAIPE/LayoutLM-style annotation files.
    """
    prepared = []
    for box in boxes:
        looks_layoutlm_normalized = (
            all(0 <= int(coord) <= 1000 for coord in box)
            and (int(box[2]) > width or int(box[3]) > height)
        )
        if looks_layoutlm_normalized:
            prepared.append(_clamp_box(box))
        else:
            prepared.append(_normalize_box(box, width, height))
    return prepared


def _load_model_and_processor() -> tuple[LayoutLMv3Processor, LayoutLMv3ForTokenClassification, torch.device]:
    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy checkpoint tại {CHECKPOINT_PATH}. "
            "Hãy đặt checkpoint fine-tuned Stage 2 trong ./stage_2/."
        )

    processor = LayoutLMv3Processor.from_pretrained(
        str(CHECKPOINT_PATH),
        apply_ocr=False,
    )
    model = LayoutLMv3ForTokenClassification.from_pretrained(
        str(CHECKPOINT_PATH),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    device = _device()
    model.to(device)
    model.eval()
    return processor, model, device


_PROCESSOR: LayoutLMv3Processor | None = None
_MODEL: LayoutLMv3ForTokenClassification | None = None
_DEVICE: torch.device | None = None


def _get_runtime() -> tuple[LayoutLMv3Processor, LayoutLMv3ForTokenClassification, torch.device]:
    global _PROCESSOR, _MODEL, _DEVICE
    if _PROCESSOR is None or _MODEL is None or _DEVICE is None:
        _PROCESSOR, _MODEL, _DEVICE = _load_model_and_processor()
    return _PROCESSOR, _MODEL, _DEVICE


def _word_subword_spans(
    processor: LayoutLMv3Processor,
    words: list[str],
) -> tuple[list[tuple[int, int]], int]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for word in words:
        tokenized = processor.tokenizer(
            [word],
            boxes=[[0, 0, 0, 0]],
            add_special_tokens=False,
            truncation=False,
        )
        input_ids = tokenized.get("input_ids", [])
        if input_ids and isinstance(input_ids[0], list):
            count = len(input_ids[0])
        else:
            count = len(input_ids)
        count = max(1, count)
        spans.append((cursor, cursor + count))
        cursor += count

    return spans, cursor


def _build_word_windows(
    spans: list[tuple[int, int]],
    total_subwords: int,
    window_size: int,
    stride: int,
) -> list[list[int]]:
    if total_subwords <= window_size:
        return [list(range(len(spans)))]

    step = max(1, window_size - stride)
    windows: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()

    start = 0
    while start < total_subwords:
        end = start + window_size
        word_indices = [
            index
            for index, (word_start, _word_end) in enumerate(spans)
            if start <= word_start < end
        ]
        key = tuple(word_indices)
        if word_indices and key not in seen:
            windows.append(word_indices)
            seen.add(key)
        start += step

    return windows


def _run_inference_single(image_path: str, words: list[str], boxes: list[list[int]]) -> list[dict]:
    if len(words) != len(boxes):
        raise ValueError(f"Số lượng words ({len(words)}) khác số lượng boxes ({len(boxes)}).")

    if not words:
        return []

    processor, model, device = _get_runtime()
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    normalized_boxes = _prepare_boxes(boxes, width, height)

    encoding = processor(
        images=image,
        text=words,
        boxes=normalized_boxes,
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in encoding.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    raw_predictions = outputs.logits.argmax(dim=-1)[0].detach().cpu().tolist()
    word_ids = encoding.word_ids(batch_index=0)

    word_predictions: dict[int, int] = {}
    for token_idx, word_idx in enumerate(word_ids):
        if word_idx is None:
            continue
        if word_idx not in word_predictions:
            word_predictions[word_idx] = raw_predictions[token_idx]

    return [
        {
            "word": words[word_idx],
            "label": ID2LABEL[word_predictions[word_idx]],
            "box": boxes[word_idx],
        }
        for word_idx in sorted(word_predictions)
        if word_idx < len(words)
    ]


def run_inference_sliding(
    image_path: str,
    words: list[str],
    boxes: list[list[int]],
    window_size: int = DEFAULT_WINDOW_SIZE,
    stride: int = DEFAULT_STRIDE,
) -> list[dict]:
    """
    Run LayoutLMv3 NER over long documents with overlapping word windows.

    The same full-page image is used for every window; only the text/box sequence
    is windowed to keep LayoutLM's text token budget under control.
    """
    if len(words) != len(boxes):
        raise ValueError(f"Số lượng words ({len(words)}) khác số lượng boxes ({len(boxes)}).")

    if not words:
        return []

    processor, _model, _device = _get_runtime()
    spans, total_subwords = _word_subword_spans(processor, words)
    windows = _build_word_windows(spans, total_subwords, window_size, stride)
    votes: dict[int, Counter[str]] = defaultdict(Counter)

    for window_indices in windows:
        window_words = [words[index] for index in window_indices]
        window_boxes = [boxes[index] for index in window_indices]
        window_predictions = _run_inference_single(image_path, window_words, window_boxes)

        for local_index, prediction in enumerate(window_predictions):
            if local_index >= len(window_indices):
                continue
            global_index = window_indices[local_index]
            votes[global_index][str(prediction["label"])] += 1

    predictions = []
    for index, word in enumerate(words):
        if votes[index]:
            label = votes[index].most_common(1)[0][0]
        else:
            label = "other"
        predictions.append({"word": word, "label": label, "box": boxes[index]})

    return predictions


def run_inference(image_path: str, words: list[str], boxes: list[list[int]]) -> list[dict]:
    """
    Run LayoutLMv3 prescription NER and return one prediction per input word.

    Args:
        image_path: prescription image path.
        words: OCR word tokens.
        boxes: raw pixel boxes or already-normalized LayoutLM boxes.

    Returns:
        [{"word": str, "label": str}, ...]
    """
    if len(words) != len(boxes):
        raise ValueError(f"Số lượng words ({len(words)}) khác số lượng boxes ({len(boxes)}).")

    processor, _model, _device = _get_runtime()
    _spans, total_subwords = _word_subword_spans(processor, words)
    if total_subwords > DEFAULT_WINDOW_SIZE:
        return run_inference_sliding(
            image_path,
            words,
            boxes,
            window_size=DEFAULT_WINDOW_SIZE,
            stride=DEFAULT_STRIDE,
        )

    return _run_inference_single(image_path, words, boxes)


def _safe_box(box: Any) -> list[int] | None:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        return [int(coord) for coord in box]
    except (TypeError, ValueError):
        return None


def _merge_boxes(boxes: list[Any]) -> list[int] | None:
    safe_boxes = [_safe_box(box) for box in boxes]
    safe_boxes = [box for box in safe_boxes if box is not None]
    if not safe_boxes:
        return None
    return [
        min(box[0] for box in safe_boxes),
        min(box[1] for box in safe_boxes),
        max(box[2] for box in safe_boxes),
        max(box[3] for box in safe_boxes),
    ]


def _entity_y_center(entity: dict[str, Any]) -> float | None:
    box = _safe_box(entity.get("box"))
    if box is None:
        return None
    return (box[1] + box[3]) / 2


def _entity_sort_key(entity: dict[str, Any]) -> tuple[float, float, str]:
    box = _safe_box(entity.get("box"))
    if box is None:
        return (float("inf"), float("inf"), entity.get("text", ""))
    return (box[1], box[0], entity.get("text", ""))


def _nearest_same_row_entity(
    drug_entity: dict[str, Any],
    candidates: list[dict[str, Any]],
    row_tolerance_px: int = ROW_TOLERANCE_PX,
) -> dict[str, Any] | None:
    drug_center = _entity_y_center(drug_entity)
    if drug_center is None:
        return None

    scored = []
    for candidate in candidates:
        candidate_center = _entity_y_center(candidate)
        if candidate_center is None:
            continue
        distance = abs(candidate_center - drug_center)
        if distance <= row_tolerance_px:
            scored.append((distance, candidate))

    if not scored:
        return None
    return min(scored, key=lambda item: item[0])[1]


def _same_entity_row(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_center = _entity_y_center(left)
    right_center = _entity_y_center(right)
    if left_center is None or right_center is None:
        return True
    return abs(left_center - right_center) <= ROW_TOLERANCE_PX


def parse_ner_output(predictions: list[dict]) -> dict:
    """
    Group consecutive same-label word predictions into Stage 3 mapper input.
    """
    raw_groups: dict[str, list[str]] = {
        "date": [],
        "diagnose": [],
        "usage": [],
        "quantity": [],
        "drugname": [],
    }
    entities: list[dict[str, Any]] = []
    current_label: str | None = None
    current_items: list[dict[str, Any]] = []

    def flush_current() -> None:
        nonlocal current_label, current_items
        if current_label and current_items and current_label in raw_groups:
            text = " ".join(str(item.get("word", "")).strip() for item in current_items).strip()
            if text:
                box = _merge_boxes([item.get("box") for item in current_items])
                raw_groups[current_label].append(text)
                entities.append({"label": current_label, "text": text, "box": box})
        current_label = None
        current_items = []

    for prediction in predictions:
        label = str(prediction.get("label", "other"))
        word = str(prediction.get("word", "")).strip()
        if not word:
            continue

        if label == "other":
            flush_current()
            continue

        if label == current_label and current_items and _same_entity_row(current_items[-1], prediction):
            current_items.append(prediction)
        else:
            flush_current()
            current_label = label
            current_items = [prediction]

    flush_current()
    raw_groups_pre_cleanup = {label: list(values) for label, values in raw_groups.items()}
    raw_entities_pre_cleanup = [dict(entity) for entity in entities]
    cleanup_applied: list[dict[str, str]] = []

    cleaned_entities: list[dict[str, Any]] = []
    for entity in entities:
        if entity["label"] != "drugname":
            cleaned_entities.append(entity)
            continue

        original_name = str(entity["text"])
        text = original_name.strip()
        if not text:
            cleanup_applied.append({"action": "rejected_empty_drug", "text": original_name})
            continue

        if PURE_DOSAGE_RE.fullmatch(text):
            cleaned_entities.append({"label": "quantity", "text": text, "box": entity.get("box")})
            cleanup_applied.append({"action": "rejected_pure_dosage", "text": text})
            cleanup_applied.append({"action": "rerouted_to_quantity", "text": text})
            continue

        if PURE_ENUMERATION_RE.fullmatch(text):
            cleanup_applied.append({"action": "rejected_enumeration", "text": text})
            continue

        if len(text.strip()) <= 2 and not ALPHA_RE.search(text):
            cleanup_applied.append({"action": "rejected_punctuation_or_single_char", "text": text})
            continue

        stripped = ENUMERATION_PREFIX_RE.sub("", text).strip()
        if stripped != text:
            cleanup_applied.append(
                {
                    "action": "stripped_enumeration",
                    "before": text,
                    "after": stripped,
                }
            )
        text = stripped

        if PURE_DOSAGE_RE.fullmatch(text):
            cleaned_entities.append({"label": "quantity", "text": text, "box": entity.get("box")})
            cleanup_applied.append({"action": "rejected_pure_dosage", "text": text})
            cleanup_applied.append({"action": "rerouted_to_quantity", "text": text})
            continue

        if PURE_ENUMERATION_RE.fullmatch(text):
            cleanup_applied.append({"action": "rejected_enumeration", "text": text})
            continue

        if not text:
            cleanup_applied.append({"action": "rejected_empty_after_cleanup", "text": original_name})
            continue

        has_letters = bool(ALPHA_RE.search(text))
        has_digits = bool(DIGIT_RE.search(text))
        if len(text.strip()) < 3 and not (has_letters and has_digits):
            cleanup_applied.append({"action": "rejected_short_drug", "text": text})
            continue

        cleaned_entity = dict(entity)
        cleaned_entity["text"] = text
        cleaned_entities.append(cleaned_entity)

    cleaned_entities.sort(key=lambda item: _entity_sort_key(item))
    groups: dict[str, list[str]] = {
        "date": [],
        "diagnose": [],
        "usage": [],
        "quantity": [],
        "drugname": [],
    }
    for entity in cleaned_entities:
        if entity["label"] in groups:
            groups[entity["label"]].append(entity["text"])

    drug_entities = [entity for entity in cleaned_entities if entity["label"] == "drugname"]
    quantity_entities = [entity for entity in cleaned_entities if entity["label"] == "quantity"]
    usage_entities = [entity for entity in cleaned_entities if entity["label"] == "usage"]

    drugs = []
    spatial_associations = []
    for drug in drug_entities:
        quantity = _nearest_same_row_entity(drug, quantity_entities)
        usage = _nearest_same_row_entity(drug, usage_entities)
        drugs.append(
            {
                "name": drug["text"],
                "quantity": quantity["text"] if quantity else "",
                "usage": usage["text"] if usage else "",
            }
        )
        spatial_associations.append(
            {
                "drug": drug["text"],
                "drug_box": drug.get("box"),
                "quantity": quantity["text"] if quantity else "",
                "quantity_box": quantity.get("box") if quantity else None,
                "usage": usage["text"] if usage else "",
                "usage_box": usage.get("box") if usage else None,
            }
        )

    return {
        "diagnoses": groups["diagnose"],
        "drugs": drugs,
        "raw_groups": groups,
        "raw_groups_pre_cleanup": raw_groups_pre_cleanup,
        "raw_entities_pre_cleanup": raw_entities_pre_cleanup,
        "entities": cleaned_entities,
        "spatial_associations": spatial_associations,
        "cleanup_applied": cleanup_applied,
    }


def _load_annotation(annotation_path: Path) -> tuple[list[str], list[list[int]], list[str]]:
    with annotation_path.open("r", encoding="utf-8") as file:
        annotation: Any = json.load(file)

    if isinstance(annotation, list):
        words = [str(item.get("text", "")) for item in annotation]
        boxes = [item.get("box", [0, 0, 0, 0]) for item in annotation]
        labels = [str(item.get("label", "other")) for item in annotation]
        return words, boxes, labels

    if isinstance(annotation, dict):
        words = [str(word) for word in annotation.get("words", [])]
        boxes = annotation.get("bboxes", [])
        labels = [str(label) for label in annotation.get("ner_tags", [])]
        return words, boxes, labels

    raise ValueError(f"Định dạng annotation không hợp lệ: {annotation_path}")


def _find_sample() -> tuple[Path, Path]:
    label_dir = REPO_ROOT / "public_train" / "prescription" / "label"
    image_dir = REPO_ROOT / "public_train" / "prescription" / "image"
    if not label_dir.exists() or not image_dir.exists():
        raise FileNotFoundError(
            "Không tìm thấy public_train/prescription/. "
            "Hãy tải dataset VAIPE-P trước khi chạy demo."
        )

    for annotation_path in sorted(label_dir.glob("*.json")):
        stem = annotation_path.stem
        for extension in (".jpg", ".png", ".jpeg"):
            image_path = image_dir / f"{stem}{extension}"
            if image_path.exists():
                return image_path, annotation_path

    raise FileNotFoundError("Không tìm thấy cặp image/label mẫu trong public_train/prescription/.")


def main() -> None:
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    image_path, annotation_path = _find_sample()
    words, boxes, gold_labels = _load_annotation(annotation_path)

    predictions = run_inference(str(image_path), words, boxes)
    parsed = parse_ner_output(predictions)

    print(f"Ảnh mẫu: {image_path}")
    print(f"Nhãn mẫu: {annotation_path}")
    if gold_labels:
        print("Dự đoán 20 token đầu:")
        for prediction, gold_label in zip(predictions[:20], gold_labels[:20]):
            print(f"- {prediction['word']}: dự đoán={prediction['label']} | nhãn_gốc={gold_label}")
    else:
        print("Dự đoán 20 token đầu:")
        for prediction in predictions[:20]:
            print(f"- {prediction['word']}: {prediction['label']}")

    print("\nNER output cho Stage 3:")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
