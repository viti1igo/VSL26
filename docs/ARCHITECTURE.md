# Architecture

VSL26 has two extraction front ends and one shared downstream pipeline. This
keeps the research comparison fair: the extraction method changes, but medication
mapping and gloss generation remain constant.

## Extraction Front Ends

### Baseline: OCR + LayoutLMv3

1. `stages/stage_1_ocr/ocr_engine.py` detects and recognizes Vietnamese text regions.
2. `stages/stage_2_extraction/inference.py` normalizes boxes, runs LayoutLMv3 token classification, handles
   long prescriptions with sliding windows, and parses entities.
3. `parse_ner_output()` emits the mapper input shape.

Supported labels:

- `date`
- `diagnose`
- `usage`
- `quantity`
- `drugname`
- `other`

The baseline is useful for VAIPE-style prescriptions and as a classical document
understanding comparator. It is expected to degrade on unseen layouts.

The current retrained checkpoint is tracked through Git LFS at
`models/layoutlmv3_vaipe_retrain_20260611_085133/final/`. If
`VSL_LAYOUTLMV3_CHECKPOINT` is unset, inference reads
`models/latest_layoutlmv3_vaipe_retrain.txt` and loads that checkpoint.

### Proposed Method: VLM Direct Extraction

1. `stages/stage_2_extraction/llm_extractor.py` sends the prescription image to the configured vision
   model.
2. The model returns strict JSON with date, diagnosis, drug fields, warnings,
   unreadable regions, and confidence scores.
3. `vlm_extraction_to_mapper_input()` converts that JSON into the same mapper
   input shape used by the baseline.

The VLM path must not add medical facts that are not visible in the image. Drug
purpose and safety wording are handled later by the KB-backed mapper.

## Shared Mapper Input

Both extraction methods should produce:

```json
{
  "diagnoses": ["..."],
  "drugs": [
    {
      "name": "...",
      "quantity": "...",
      "usage": "...",
      "evidence_text": "...",
      "confidence": 0.0
    }
  ],
  "raw_groups": {},
  "entities": [],
  "source": "layoutlmv3_ocr_ner or vlm_direct_extraction"
}
```

Fields can be empty when the image is unreadable. Do not invent dosage,
duration, or diagnosis values.

## Downstream Pipeline

`MedicineMapper` handles:

- medication name normalization
- fuzzy matching against `vaipe_drugs.db`
- brand alias lookup
- optional LLM-assisted KB enrichment when explicitly enabled
- child-friendly medication purpose text
- VSL gloss section generation
- VSL footage token lookup

The main gloss sections are:

- `dung_cho`: what the medicine is for
- `dung_nhu_nao`: how to take it
- `luu_y`: safety notes
- universal closing: escalation advice for severe symptoms

## Comparison Harness

`stages/stage_4_evaluation/compare_extraction_methods.py` is the common
method-comparison implementation. The root `compare_extraction_methods.py`
wrapper is kept for backwards-compatible CLI usage.
It reports:

- number of extracted diagnoses and drugs
- number of mapped drugs
- completeness of usage instructions
- missing or placeholder VSL tokens
- estimated video duration
- whether the output is video-ready

Use this harness for method comparison rather than writing one-off scripts.

## Main Failure Modes

- OCR misses Vietnamese diacritics or merges drug lines.
- LayoutLMv3 labels degrade on layouts outside VAIPE.
- VLM extracts visible text correctly but structures multi-drug prescriptions
  incorrectly.
- Drug names are brand names absent from the KB.
- Generated gloss contains too many tokens for expert review.
- VSL token lookup contains placeholders that require footage assignment.
