"""Count and normalize drug-name entities across the VAIPE-P prescription labels."""

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent
DATASET_PATH_CACHE = REPO_ROOT / ".dataset_path"
DOSAGE_RE = re.compile(
    r"(?i)\b\d+(?:[.,]\d+)?\s*(?:mg|ml|g|mcg|µg|iu|%|viên|vien|gói|goi|ống|ong|chai)\b"
)
LEADING_ITEM_RE = re.compile(r"^\s*\d+\s*(?:[).:\-]+)?\s*")


def _has_json_files(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.glob("*.json"))


def _limited_recursive_label_dirs(base: Path, pattern: str, max_depth: int = 6) -> Iterable[Path]:
    if not base.exists():
        return

    target_parts = tuple(part for part in Path(pattern).parts if part != "**")
    base_depth = len(base.resolve().parts)
    for root, dirs, _files in os.walk(base):
        root_path = Path(root)
        depth = len(root_path.resolve().parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []

        if tuple(root_path.parts[-len(target_parts) :]) == target_parts:
            yield root_path


def _kaggle_cache_candidates() -> Iterable[Path]:
    cache_root = Path.home() / ".cache" / "kagglehub" / "datasets"
    if not cache_root.exists():
        return

    yield from _limited_recursive_label_dirs(
        cache_root,
        "**/public_train/prescription/label",
        max_depth=8,
    )


def find_vaipe_dataset() -> Path | None:
    """
    Find VAIPE-P prescription label JSONs and cache the discovered path.

    Returns the first existing public_train/prescription/label directory that
    contains at least one .json file. If not found, prints searched locations
    and returns None.
    """
    searched: list[str] = []

    if DATASET_PATH_CACHE.exists():
        cached = Path(DATASET_PATH_CACHE.read_text(encoding="utf-8").strip()).expanduser()
        searched.append(f"cache: {cached}")
        if _has_json_files(cached):
            return cached

    fixed_candidates = [
        REPO_ROOT / "public_train" / "prescription" / "label",
        REPO_ROOT / "data" / "public_train" / "prescription" / "label",
        Path.home() / "Downloads" / "vaipepill2022" / "public_train" / "prescription" / "label",
    ]

    for candidate in fixed_candidates:
        searched.append(str(candidate))
        if _has_json_files(candidate):
            DATASET_PATH_CACHE.write_text(str(candidate), encoding="utf-8")
            return candidate

    downloads = Path.home() / "Downloads"
    recursive_groups = [
        (
            "~/Downloads/**/public_train/prescription/label/",
            _limited_recursive_label_dirs(downloads, "**/public_train/prescription/label", max_depth=8),
        ),
        (
            "~/**/vaipepill*/public_train/prescription/label/",
            _limited_recursive_label_dirs(Path.home(), "**/vaipepill*/public_train/prescription/label", max_depth=6),
        ),
        (
            "~/.cache/kagglehub/datasets/**/public_train/prescription/label/",
            _kaggle_cache_candidates(),
        ),
    ]

    for description, candidates in recursive_groups:
        searched.append(description)
        for candidate in candidates or []:
            searched.append(str(candidate))
            if _has_json_files(candidate):
                DATASET_PATH_CACHE.write_text(str(candidate), encoding="utf-8")
                return candidate

    print("Không tìm thấy thư mục nhãn VAIPE-P có file .json.")
    print("Đã kiểm tra các vị trí:")
    for item in searched:
        print(f"- {item}")
    return None


def normalize_drug_name(text: str) -> str:
    text = LEADING_ITEM_RE.sub(" ", text)
    text = DOSAGE_RE.sub(" ", text)
    text = re.sub(r"[^\w\sÀ-ỹ-]", " ", text, flags=re.UNICODE)
    text = LEADING_ITEM_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _extract_drug_entities(annotation_path: Path) -> list[str]:
    with annotation_path.open("r", encoding="utf-8") as file:
        annotation = json.load(file)

    if isinstance(annotation, list):
        entities = []
        current_tokens = []
        for item in annotation:
            label = item.get("label")
            text = str(item.get("text", "")).strip()
            if label == "drugname" and text:
                current_tokens.append(text)
            elif current_tokens:
                entities.append(" ".join(current_tokens))
                current_tokens = []
        if current_tokens:
            entities.append(" ".join(current_tokens))
        return entities

    if isinstance(annotation, dict):
        words = annotation.get("words", [])
        labels = annotation.get("ner_tags", [])
        entities = []
        current_tokens = []
        for word, label in zip(words, labels):
            text = str(word).strip()
            if label == "drugname" and text:
                current_tokens.append(text)
            elif current_tokens:
                entities.append(" ".join(current_tokens))
                current_tokens = []
        if current_tokens:
            entities.append(" ".join(current_tokens))
        return entities

    return []


def count_drugs(label_dir: Path) -> Counter[str]:
    counter: Counter[str] = Counter()
    for annotation_path in sorted(label_dir.glob("*.json")):
        for entity in _extract_drug_entities(annotation_path):
            normalized = normalize_drug_name(entity)
            if normalized:
                counter[normalized] += 1
    return counter


def main() -> None:
    label_dir = find_vaipe_dataset()
    if label_dir is None:
        return

    counter = count_drugs(label_dir)
    print(f"Dataset: {label_dir}")
    print(f"Số thuốc khác nhau: {len(counter)}")
    print("\nTop thuốc theo tần suất:")
    for rank, (drug_name, count) in enumerate(counter.most_common(), start=1):
        print(f"{rank:>3}. {drug_name:<40} {count}")


if __name__ == "__main__":
    main()
