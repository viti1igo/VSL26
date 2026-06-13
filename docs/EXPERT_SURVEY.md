# Expert Survey

The expert survey validates generated VSL glosses from prescription images. It
does not ask experts to run code or inspect intermediate OCR/NER output.

## Survey Item Format

Each item should contain:

1. Question ID, such as `Q001`.
2. Prescription image.
3. Generated gloss.
4. Required 1-5 score.
5. Optional comment field.

Do not include extraction debug fields in the expert-facing form.

## Scoring Prompt

Vietnamese:

```text
Đánh giá chất lượng gloss này theo thang điểm 1-5
(1 = không đạt / sai nghiêm trọng / không an toàn;
5 = rất tốt / có thể sử dụng).
```

English:

```text
Evaluate the quality of this gloss on a 1-5 scale
(1 = unacceptable / seriously wrong / unsafe;
5 = very good / usable).
```

## Comment Prompt

Vietnamese:

```text
Góp ý chỉnh sửa gloss nếu có (không bắt buộc).
```

English:

```text
Optional: suggest gloss corrections or explain the score.
```

## Building Local Survey Files

Prepare the 30-image sample manifests under `survey_input/`, then run:

```bash
python export_expert_survey.py
```

Generated files are written under `expert_survey/` and are ignored by git except
for reusable Google Form builder scripts under `expert_survey/google_form_builder/`.

## Google Forms Builder

Use the scripts under `expert_survey/google_form_builder/` after uploading
`expert_survey/images/` to Google Drive.

Recommended script:

- `Code_no_csv_bilingual_folder_fixed.gs` for creating a new bilingual form.

Updater script:

- `update_existing_form_bilingual.gs` for updating an existing form when the
  Apps Script account has edit access to that form.

Do not commit active edit links, respondent data, or private Drive folder URLs.

## Data Handling

Keep these private:

- respondent codes
- survey response spreadsheets
- active Google Form edit links
- prescription images that should not be publicly distributed

Commit only reusable source scripts and documentation.
