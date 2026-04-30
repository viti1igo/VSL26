"""Detect and recognize Vietnamese prescription text using EasyOCR and VietOCR."""

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from count_drugs import find_vaipe_dataset


_EASYOCR_READER = None
_VIETOCR_ENGINE = None


def _device_name() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _polygon_to_box(points: Any) -> list[int]:
    normalized = points.tolist() if hasattr(points, "tolist") else points
    xs = [point[0] for point in normalized]
    ys = [point[1] for point in normalized]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _clamp_box(box: list[int], width: int, height: int, padding: int = 4) -> list[int]:
    x1, y1, x2, y2 = box
    return [
        max(0, x1 - padding),
        max(0, y1 - padding),
        min(width, x2 + padding),
        min(height, y2 + padding),
    ]


def _init_easyocr() -> Any:
    import easyocr

    print("Loading EasyOCR CRAFT detector; model weights may download on first use...")
    return easyocr.Reader(["vi"], gpu=False, detector=True, recognizer=False)


def _init_vietocr() -> Any:
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor

    device = _device_name()
    print(f"Loading VietOCR vgg_transformer recognizer on {device}; weights may download on first use...")
    config = Cfg.load_config_from_name("vgg_transformer")
    config["device"] = device
    config["predictor"]["beamsearch"] = False
    config["quiet"] = True
    return Predictor(config)


def _get_easyocr_reader() -> Any:
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        _EASYOCR_READER = _init_easyocr()
    return _EASYOCR_READER


def _get_vietocr_engine() -> Any:
    global _VIETOCR_ENGINE
    if _VIETOCR_ENGINE is None:
        _VIETOCR_ENGINE = _init_vietocr()
    return _VIETOCR_ENGINE


def _sort_boxes(boxes: list[list[int]]) -> list[list[int]]:
    if not boxes:
        return []

    heights = [max(1, box[3] - box[1]) for box in boxes]
    line_tolerance = max(10, int(sum(heights) / len(heights) * 0.6))
    return sorted(boxes, key=lambda box: (round(box[1] / line_tolerance), box[0]))


def _flatten_easyocr_boxes(detect_result: Any) -> list[list[int]]:
    if not isinstance(detect_result, tuple) or len(detect_result) < 2:
        return []

    horizontal_list, free_list = detect_result[0], detect_result[1]
    boxes: list[list[int]] = []

    # EasyOCR returns one page for single-image input.
    for page in horizontal_list or []:
        for raw_box in page or []:
            if len(raw_box) < 4:
                continue
            x_min, x_max, y_min, y_max = raw_box[:4]
            boxes.append([int(x_min), int(y_min), int(x_max), int(y_max)])

    for page in free_list or []:
        for polygon in page or []:
            if polygon:
                boxes.append(_polygon_to_box(polygon))

    return boxes


def _recognition_confidence(probabilities: Any) -> float:
    if probabilities is None:
        return 0.0
    if hasattr(probabilities, "detach"):
        probabilities = probabilities.detach().cpu().float().tolist()
    if isinstance(probabilities, (int, float)):
        return float(probabilities)
    if hasattr(probabilities, "item"):
        try:
            return float(probabilities.item())
        except ValueError:
            pass
    values = [float(value) for value in probabilities if float(value) > 0]
    if not values:
        return 0.0
    return sum(values) / len(values)


def run_ocr(image_path: str) -> list[dict]:
    """
    Returns list of {"text": str, "box": [x1, y1, x2, y2], "confidence": float}.
    Boxes are raw pixel coordinates. NER inference normalizes boxes to [0, 1000].
    """
    reader = _get_easyocr_reader()
    recognizer = _get_vietocr_engine()

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    detection = reader.detect(str(image_path))
    boxes = [_clamp_box(box, width, height) for box in _flatten_easyocr_boxes(detection)]

    results = []
    for box in _sort_boxes(boxes):
        if box[2] <= box[0] or box[3] <= box[1]:
            continue

        crop = image.crop(tuple(box))
        text, probabilities = recognizer.predict(crop, return_prob=True)
        text = str(text).strip()
        if not text:
            continue

        results.append(
            {
                "text": text,
                "confidence": _recognition_confidence(probabilities),
                "box": box,
            }
        )

    return results


def run_ocr_batch(image_paths: list[str]) -> list[list[dict]]:
    return [run_ocr(image_path) for image_path in image_paths]


def _find_sample_image() -> Path:
    label_dir = find_vaipe_dataset()
    if label_dir is not None:
        image_dir = label_dir.parent / "image"
        if image_dir.exists():
            for extension in ("*.jpg", "*.jpeg", "*.png"):
                first = next(image_dir.glob(extension), None)
                if first:
                    return first

    repo_root = Path(__file__).resolve().parent
    for candidate_root in [
        repo_root / "public_train" / "prescription" / "image",
        repo_root / "data" / "public_train" / "prescription" / "image",
        repo_root.parent / "vaipepill2022" / "public_train" / "prescription" / "image",
    ]:
        if candidate_root.exists():
            for extension in ("*.jpg", "*.jpeg", "*.png"):
                first = next(candidate_root.glob(extension), None)
                if first:
                    return first

    raise FileNotFoundError(
        "Không tìm thấy ảnh toa thuốc mẫu. Hãy truyền đường dẫn bằng --image."
    )


def _matching_label_path(image_path: Path) -> Path | None:
    label_path = image_path.parent.parent / "label" / f"{image_path.stem}.json"
    return label_path if label_path.exists() else None


def _load_drug_terms(label_path: Path) -> list[str]:
    data = json.loads(label_path.read_text(encoding="utf-8"))
    terms: set[str] = set()

    def add_terms(text: str) -> None:
        for token in re.findall(r"[\wÀ-ỹ]+(?:[-+][\wÀ-ỹ]+)?", text, flags=re.UNICODE):
            token = token.strip()
            if len(token) >= 2 and not token.isdigit():
                terms.add(token)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("label") == "drugname":
                add_terms(str(item.get("text", "")))
    elif isinstance(data, dict):
        words = data.get("words") or data.get("tokens") or []
        labels = data.get("ner_tags") or data.get("labels") or []
        for word, label in zip(words, labels):
            if label == "drugname":
                add_terms(str(word))

    return sorted(terms, key=lambda value: _normalize_for_match(value))


def _normalize_for_match(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", without_marks.upper())


def _compare_drug_terms(results: list[dict], label_path: Path | None) -> tuple[list[str], list[str]]:
    if label_path is None:
        return [], []

    terms = _load_drug_terms(label_path)
    ocr_text = " ".join(item["text"] for item in results)
    normalized_ocr = _normalize_for_match(ocr_text)
    matched = [term for term in terms if _normalize_for_match(term) in normalized_ocr]
    missing = [term for term in terms if term not in matched]
    return matched, missing


def _save_results(image_path: Path, results: list[dict]) -> Path:
    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{image_path.stem}_ocr.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _contains_phrase(results: list[dict], phrase: str) -> bool:
    normalized_text = _normalize_for_match(" ".join(item["text"] for item in results))
    return _normalize_for_match(phrase) in normalized_text


def _contains_exact_phrase(results: list[dict], phrase: str) -> bool:
    return phrase in " ".join(item["text"] for item in results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy VietOCR cho ảnh toa thuốc VAIPE-P.")
    parser.add_argument("--image", help="Đường dẫn ảnh toa thuốc cần OCR.")
    parser.add_argument("--limit", type=int, default=30, help="Số dòng OCR đầu tiên cần in.")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser() if args.image else _find_sample_image()
    results = run_ocr(str(image_path))
    output_path = _save_results(image_path, results)
    label_path = _matching_label_path(image_path)
    matched_terms, missing_terms = _compare_drug_terms(results, label_path)

    print(f"Ảnh: {image_path}")
    print(f"Tổng số vùng chữ phát hiện: {len(results)}")
    print(f"Lưu OCR đầy đủ: {output_path}")
    print(f"{args.limit} kết quả OCR đầu tiên:")
    for item in results[: args.limit]:
        print(f"- text={item['text']} | confidence={item['confidence']:.4f} | box={item['box']}")

    print("Kiểm tra cụm tiếng Việt:")
    for phrase in ["Tăng huyết áp", "HOẠT HUYẾT DƯỠNG"]:
        exact = "có" if _contains_exact_phrase(results, phrase) else "không"
        normalized = "có" if _contains_phrase(results, phrase) else "không"
        print(f"- {phrase}: exact={exact}, normalized={normalized}")

    if label_path is not None:
        total_terms = len(matched_terms) + len(missing_terms)
        print("So khớp thuật ngữ thuốc từ ground-truth:")
        print(f"- Khớp: {len(matched_terms)}/{total_terms}")
        print(f"- Tìm thấy: {', '.join(matched_terms) if matched_terms else '(không có)'}")
        print(f"- Thiếu: {', '.join(missing_terms) if missing_terms else '(không có)'}")
    else:
        print("Không tìm thấy JSON ground-truth tương ứng để so khớp thuật ngữ thuốc.")


if __name__ == "__main__":
    main()
