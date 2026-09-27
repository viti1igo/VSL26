# Research Protocol

## Working Title

Vision-Language Extraction for Vietnamese Prescription-to-Sign-Language Gloss
Generation: An Expert Evaluation Study

## Research Question

Can a vision-language model extraction front end produce more expert-usable VSL
glosses from diverse Vietnamese prescription images than an OCR plus LayoutLMv3
NER baseline when both methods use the same medication mapping and gloss
generation pipeline?

## Contribution

The paper should not claim that VLM OCR is the main novelty. The defensible
contribution is an evaluation-first accessibility pipeline:

1. A prescription-image to VSL-gloss pipeline for Vietnamese medication
   instructions.
2. A fair comparison between a classical document-AI front end and a VLM front
   end under layout variation.
3. A shared KB-backed mapping layer that converts extracted medication rows into
   safety-aware gloss sections.
4. An expert evaluation protocol for gloss quality, correctness, safety, and
   usability.
5. An error analysis showing where layout-dependent extraction fails and where
   VLM extraction helps.

## Dataset Mix

The expert evaluation set should remain small but diverse:

- VAIPE-style prescriptions
- printed/archive prescriptions
- real-world prescription photos

The current survey package uses 30 images. For a method comparison survey, the
recommended design is 15 images evaluated under two methods, randomized and
method-blinded where possible.

## Methods

### Baseline

OCR plus LayoutLMv3 NER:

- OCR extracts text and bounding boxes.
- LayoutLMv3 labels date, diagnosis, usage, quantity, and drug name.
- Spatial association links drug rows to quantity and usage fields.
- Parsed output feeds `MedicineMapper`.

### Proposed Method

VLM direct structured extraction:

- The prescription image is sent to a configured vision model.
- The model returns strict structured JSON.
- The JSON is converted to the same mapper input shape as the baseline.
- No inferred medical advice is allowed in the extraction step.

### Shared Mapper

Both methods use:

- the same SQLite medication KB
- the same alias and fuzzy matching logic
- the same gloss templates
- the same VSL token lookup

## Expert Evaluation

Each survey item should show:

- prescription image
- generated gloss only
- required 1-5 score
- optional text comment
- respondent code only

Do not ask for personal information.

Recommended scoring dimensions for a stronger paper:

- correctness of medication information
- completeness of dosage and usage
- safety of warnings
- VSL gloss naturalness
- overall usability

The current simple form uses one overall score to minimize expert burden. If the
paper targets a stronger venue, split the score into these dimensions and report
inter-rater reliability.

## Analysis Plan

Minimum analysis:

- mean and median score per method
- score distribution per source group
- comment-based error taxonomy
- qualitative examples of high and low scoring outputs

Stronger analysis:

- paired comparison on the same images
- Wilcoxon signed-rank test or paired t-test depending on score distribution
- inter-rater reliability with ICC or Krippendorff's alpha
- error categories for extraction, KB mapping, gloss grammar, and safety omission

## Current Limitations

- 30 examples is a pilot-scale evaluation.
- Expert gloss quality does not directly prove patient comprehension.
- Synthetic or LLM-assisted KB expansion must be disclosed and separated from
  human-validated KB entries.
- VLM outputs must be audited because they can structure text incorrectly even
  when OCR-like reading looks plausible.

## Paper Positioning

Current evidence is suitable for a pilot or applied research paper. To position
for a stronger Q1-style submission, add more raters, inter-rater reliability,
multi-dimensional scoring, a paired method design, and a rigorous error taxonomy.
