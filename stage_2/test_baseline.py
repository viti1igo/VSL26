import torch
from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification, Trainer, TrainingArguments
from preprocess import get_preprocessed_datasets
from graph_collator import GraphDataCollator

# Setup device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=False)
prescription_labels = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
label2id = {l: i for i, l in enumerate(prescription_labels)}

# 1. Load data
print("Loading datasets...")
train_ds, val_ds, _ = get_preprocessed_datasets(processor, label2id)
collator = GraphDataCollator(processor.tokenizer, pad_to_multiple_of=8)

# 2. Load standard model
print("Loading standard model...")
model = LayoutLMv3ForTokenClassification.from_pretrained(
    "microsoft/layoutlmv3-base", 
    num_labels=len(prescription_labels),
    ignore_mismatched_sizes=True
).to(device)

# 3. Training args for health check
training_args = TrainingArguments(
    output_dir="./baseline_check",
    max_steps=5,
    per_device_train_batch_size=2,
    logging_steps=1,
    fp16=False,
    remove_unused_columns=False
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_ds,
    data_collator=collator
)

print("Starting baseline training check...")
trainer.train()
print("BASELINE CHECK COMPLETE")
