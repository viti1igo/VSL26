# VSL26 LayoutLMv3 Retraining on UTS Venus13

This runbook retrains the LayoutLMv3 prescription NER baseline on gold VAIPE
labels. Archive and real-world prescriptions are used after training as an
out-of-distribution functional check, not as supervised training data.

## What Gets Trained

- Model: `LayoutLMv3ForTokenClassification`
- Default base: `microsoft/layoutlmv3-base`
- Labels: `date`, `diagnose`, `usage`, `quantity`, `drugname`, `other`
- Data: VAIPE `public_train/prescription/{image,label}`
- Output: `models/layoutlmv3_vaipe_retrain_<timestamp>/final`

The script never overwrites an existing output directory unless
`--overwrite-output-dir` is passed.

## Copy Project to iHPC

From your Mac:

```bash
cd /Users/locnguyen/Desktop/UTS/Research_Proj
rsync -av --exclude '.git' --exclude '.venv' --exclude 'models' \
  VSL26/ YOUR_UTS_USER@hpc.research.uts.edu.au:~/VSL26/
```

If you want to start from the recovered local checkpoint instead of
`microsoft/layoutlmv3-base`, also copy `models/` and submit with
`BASE_MODEL=models`.

## Smoke Test First

On the iHPC login node, request a short interactive GPU session on Venus13:

```bash
qsub -I -q gpuq -l host=venus13 -l select=1:ngpus=1:ncpus=4:mem=24gb -l walltime=00:30:00
```

Inside the interactive session:

```bash
cd ~/VSL26
python3 -m venv .venv-venus13
source .venv-venus13/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r training/requirements-venus13.txt

python training/train_layoutlmv3_vaipe.py \
  --download-kaggle \
  --smoke \
  --output-dir models/layoutlmv3_vaipe_smoke \
  --overwrite-output-dir
```

The smoke test should finish quickly and create:

- `models/layoutlmv3_vaipe_smoke/data_audit.json`
- `models/layoutlmv3_vaipe_smoke/final_metrics.json`
- `models/layoutlmv3_vaipe_smoke/final/`

## Full PBS Run

One-command overnight run from `~/VSL26`:

```bash
bash training/start_overnight_venus13.sh
```

This submits the PBS job when `qsub` is available. The job writes:

- `models/latest_layoutlmv3_vaipe_retrain.txt`
- `models/layoutlmv3_vaipe_retrain_*/final_metrics.json`
- `models/layoutlmv3_vaipe_retrain_*/final/`
- `logs/overnight_layoutlmv3_*.log`

Submit the full job from `~/VSL26`:

```bash
qsub training/run_venus13_layoutlmv3.pbs
```

Useful overrides:

```bash
BASE_MODEL=models MAX_STEPS=2000 TRAIN_BATCH_SIZE=8 qsub training/run_venus13_layoutlmv3.pbs
```

If PBS rejects `#PBS -l host=venus13`, remove that line from the job script and
let `gpuq` choose the GPU node.

Monitor:

```bash
qstat -u "$USER"
tail -f logs/vsl26_layoutlmv3.*.log
```

## Post-Training Functional Check

After the model is saved, run this on the new checkpoint:

```bash
python training/functional_extraction_check.py \
  --checkpoint models/layoutlmv3_vaipe_retrain_YYYYMMDD_HHMMSS/final \
  --image-path survey_input/vaipe_10/images \
  --image-path survey_input/archive_mix_10/images \
  --image-path survey_input/real_world_10/images \
  --output-json results/retrained_functional_check.json \
  --output-csv results/retrained_functional_check.csv
```

This gives a practical answer to: "Does the retrained model produce usable drug
rows on our real survey images?"

## Expected Time

- Smoke test: 10-30 minutes
- Full training on one Venus13 GPU: roughly 1-3 hours if the GPU is modern, up
  to 4-6 hours if I/O or package install is slow
- Functional check on 31 survey images: 30-60 minutes if OCR dependencies are
  installed
