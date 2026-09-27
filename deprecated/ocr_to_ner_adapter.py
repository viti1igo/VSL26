"""Deprecated OCR word-splitting adapter; phrase-level OCR is used by the pipeline."""

def split_ocr_into_words(ocr_results: list[dict]) -> tuple[list[str], list[list[int]]]:
    """
    Convert phrase-level OCR regions into word-level tokens for LayoutLMv3 NER.

    Each OCR region is split on whitespace. The original x-span is divided across
    words in proportion to character count, including one following space for
    every word except the last. Y coordinates are preserved.
    """
    words: list[str] = []
    boxes: list[list[int]] = []

    for item in ocr_results:
        text = str(item.get("text", ""))
        box = item.get("box", [0, 0, 0, 0])
        tokens = [token for token in text.split() if token]
        if not tokens or len(box) != 4:
            continue

        x1, y1, x2, y2 = [int(coord) for coord in box]
        width = max(0, x2 - x1)
        weighted_lengths = [
            len(token) + (1 if index < len(tokens) - 1 else 0)
            for index, token in enumerate(tokens)
        ]
        total_weight = max(1, sum(weighted_lengths))

        cursor = x1
        for index, (token, weight) in enumerate(zip(tokens, weighted_lengths)):
            if index == len(tokens) - 1:
                next_x = x2
            else:
                next_x = x1 + round(width * sum(weighted_lengths[: index + 1]) / total_weight)

            words.append(token)
            boxes.append([int(cursor), y1, int(next_x), y2])
            cursor = next_x

    return words, boxes
