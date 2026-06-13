"""Extract a small VAIPE prescription-image sample for expert survey prep."""

import argparse
import csv
import random
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "survey_input" / "vaipe_30"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VAIPE_IMAGE_DIR_CANDIDATES = (
    "public_test/prescription/image/",
    "public_train/prescription/image/",
    "public_test/images/",
    "public_train/images/",
)


@dataclass(frozen=True)
class ImageEntry:
    source: str
    prescription_id: str
    filename: str


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def _prescription_id(path: str) -> str:
    return Path(path).stem


def _iter_zip_images(zip_path: Path) -> list[ImageEntry]:
    with zipfile.ZipFile(zip_path) as archive:
        names = [
            item.filename
            for item in archive.infolist()
            if not item.is_dir() and _is_image(item.filename)
        ]

    for prefix in VAIPE_IMAGE_DIR_CANDIDATES:
        matching = [name for name in names if prefix in name]
        if matching:
            return [
                ImageEntry(source=name, prescription_id=_prescription_id(name), filename=Path(name).name)
                for name in sorted(matching)
            ]

    matching = [name for name in names if "prescription" in name.lower()]
    return [
        ImageEntry(source=name, prescription_id=_prescription_id(name), filename=Path(name).name)
        for name in sorted(matching)
    ]


def _iter_dir_images(dataset_dir: Path) -> list[ImageEntry]:
    for candidate in VAIPE_IMAGE_DIR_CANDIDATES:
        image_dir = dataset_dir / candidate
        if image_dir.exists():
            return [
                ImageEntry(source=str(path), prescription_id=path.stem, filename=path.name)
                for path in sorted(image_dir.iterdir())
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ]

    return [
        ImageEntry(source=str(path), prescription_id=path.stem, filename=path.name)
        for path in sorted(dataset_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and "prescription" in str(path).lower()
    ]


def _select_sample(entries: list[ImageEntry], count: int, seed: int) -> list[ImageEntry]:
    if len(entries) < count:
        raise ValueError(f"Only found {len(entries)} prescription images, need {count}.")
    rng = random.Random(seed)
    return sorted(rng.sample(entries, count), key=lambda item: item.prescription_id)


def _safe_output_name(index: int, entry: ImageEntry) -> str:
    suffix = Path(entry.filename).suffix.lower() or ".jpg"
    return f"RX{index:03d}_{entry.prescription_id}{suffix}"


def extract_sample(
    source_path: Path,
    output_dir: Path,
    count: int,
    seed: int,
) -> Path:
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if source_path.is_file() and source_path.suffix.lower() == ".zip":
        entries = _iter_zip_images(source_path)
        selected = _select_sample(entries, count, seed)
        with zipfile.ZipFile(source_path) as archive:
            for index, entry in enumerate(selected, start=1):
                output_name = _safe_output_name(index, entry)
                with archive.open(entry.source) as src, (images_dir / output_name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    elif source_path.is_dir():
        entries = _iter_dir_images(source_path)
        selected = _select_sample(entries, count, seed)
        for index, entry in enumerate(selected, start=1):
            output_name = _safe_output_name(index, entry)
            shutil.copy2(entry.source, images_dir / output_name)
    else:
        raise FileNotFoundError(f"Dataset source not found or unsupported: {source_path}")

    manifest_path = output_dir / "sample_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["sample_id", "prescription_id", "image_file", "source_path"])
        for index, entry in enumerate(selected, start=1):
            writer.writerow(
                [
                    f"RX{index:03d}",
                    entry.prescription_id,
                    str(images_dir / _safe_output_name(index, entry)),
                    entry.source,
                ]
            )

    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a 30-image VAIPE prescription sample without extracting the full dataset."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to VAIPE zip or extracted dataset directory.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument("--count", type=int, default=30, help="Number of images to sample.")
    parser.add_argument("--seed", type=int, default=26, help="Random seed for reproducible sampling.")
    args = parser.parse_args()

    manifest_path = extract_sample(
        Path(args.source).expanduser(),
        Path(args.output_dir).expanduser(),
        args.count,
        args.seed,
    )
    print(f"Created sample manifest: {manifest_path}")
    print(f"Images copied to: {manifest_path.parent / 'images'}")


if __name__ == "__main__":
    main()
