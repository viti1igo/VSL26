import os
import torch
from transformers import LayoutLMv3Processor, Trainer, TrainingArguments
from gat_model import LayoutLMv3GATForTokenClassification
from preprocess import get_preprocessed_datasets
from graph_collator import GraphDataCollator

os.environ['CUDA_VISIBLE_DEVICES'] = "1"

def main():
    print("Loading processor and splitting datasets...")
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=False)
    
    prescription_labels = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
    label2id = {l: i for i, l in enumerate(prescription_labels)}
    
    # We only care about the testing split here
    _, _, test_ds = get_preprocessed_datasets(processor, label2id)
    
    print("\nLoading Trained GAT Model from your final checkpoint...")
    model_path = "../models/vaipe_hybrid_graph_2"
    if not os.path.exists(model_path):
        print(f"Warning: {model_path} not found! Did training finish? Using base model instead.")
        model_path = "microsoft/layoutlmv3-base"
        
    model = LayoutLMv3GATForTokenClassification.from_pretrained(
        model_path, 
        num_labels=len(prescription_labels),
        ignore_mismatched_sizes=True
    )
    model.to("cuda")
    
    args = TrainingArguments(
        output_dir="./eval_output",
        per_device_eval_batch_size=8,
        dataloader_num_workers=8,
        fp16=False
    )
    
    trainer = Trainer(
        model=model,
        args=args,
        data_collator=GraphDataCollator(processor.tokenizer, pad_to_multiple_of=8), 
    )
    
    print("🚀 Evaluating Local Test Split (the 10% slice of the 8-1-1 split)...")
    results = trainer.evaluate(test_ds)
    print(f"\nLocal Test Metrics: {results}")

if __name__ == "__main__":
    main()
