# Operations

This file collects reproducible commands for local runs, survey export, and
iHPC/Venus13 training.

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` locally. Never commit it.

## Method Comparison

Baseline only:

```bash
python compare_extraction_methods.py \
  --image /path/to/prescription.png \
  --method layoutlmv3
```

VLM only:

```bash
python compare_extraction_methods.py \
  --image /path/to/prescription.png \
  --method vlm
```

Both methods:

```bash
python compare_extraction_methods.py \
  --image /path/to/prescription.png \
  --method both
```

The output JSON defaults to `results/extraction_method_comparison_<image>.json`.

## Expert Survey Export

```bash
python export_expert_survey.py
```

Useful options:

```bash
python export_expert_survey.py --refresh
python export_expert_survey.py --model gpt-5.4
python export_expert_survey.py --no-auto-enrich
```

The command uses manifests from:

- `survey_input/vaipe_10/sample_manifest.csv`
- `survey_input/archive_mix_10/sample_manifest.csv`
- `survey_input/real_world_10/sample_manifest.csv`

## VAIPE Sampling

```bash
python prepare_vaipe_sample.py \
  --source /path/to/vaipepill2022.zip \
  --output-dir survey_input/vaipe_10 \
  --count 10 \
  --seed 26
```

## LayoutLMv3 Retraining on Venus13

Read the full runbook:

```text
training/README_venus13_retrain.md
```

One-command overnight run from the project root on the server:

```bash
bash training/start_overnight_venus13.sh
```

Submit directly with PBS:

```bash
qsub training/run_venus13_layoutlmv3.pbs
```

Monitor:

```bash
qstat -u "$USER"
tail -f logs/vsl26_layoutlmv3.*.log
tail -f logs/overnight_layoutlmv3_*.log
```

## Local Functional Check

After copying a trained checkpoint locally:

```bash
bash training/run_local_30_survey_check.sh \
  models/layoutlmv3_vaipe_retrain_YYYYMMDD_HHMMSS/final
```

This writes ignored result files under `results/` and `logs/`.

## Pre-Commit Checks

Run Python syntax checks:

```bash
python3 -m py_compile \
  compare_extraction_methods.py \
  export_expert_survey.py \
  inference.py \
  layoutlmv3_gat_model.py \
  llm_extractor.py \
  medicine_mapper.py \
  prepare_vaipe_sample.py \
  stages/stage_1_ocr/ocr_engine.py \
  stages/stage_2_extraction/*.py \
  stages/stage_3_mapping/medicine_mapper.py \
  stages/stage_4_evaluation/*.py \
  training/*.py
```

Check git scope before committing:

```bash
git status --short
git diff --stat
```

Expected commit scope:

- source code
- reusable scripts
- markdown docs
- small reference CSV/XLSX files already intentionally tracked

Excluded commit scope:

- `.env`
- model checkpoints
- downloaded datasets
- virtualenvs
- logs
- generated survey images/results
