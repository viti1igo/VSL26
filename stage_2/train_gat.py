"""
DESCRIPTION:
    This script trains the LayoutLMv3GAT model on the preprocessed VAIPE dataset.
    It performs the following steps:
    1. Loads the preprocessed dataset.
    2. Initializes the LayoutLMv3GAT model.
    3. Trains the model on the dataset.
    4. Evaluates the model on the test set.
    5. Saves the model.
"""
import os
import torch
import numpy as np
from sklearn.metrics import precision_recall_fscore_support
from transformers import LayoutLMv3Processor, TrainingArguments, Trainer, EarlyStoppingCallback
from torch.optim.lr_scheduler import CosineAnnealingLR

from gat_model import LayoutLMv3GATForTokenClassification
from preprocess import get_preprocessed_datasets
from graph_collator import GraphDataCollator

os.environ['CUDA_VISIBLE_DEVICES'] = "0,1"

def compute_metrics(p):
    """
    Computes Precision, Recall, and F1 strictly masking out padding (-100).
    """
    predictions, labels = p
    predictions = np.argmax(predictions, axis=2)
    
    # Target 1D arrays for Sklearn calculations
    true_predictions = [
        [p_i for (p_i, l_i) in zip(prediction, label) if l_i != -100]
        for prediction, label in zip(predictions, labels)
    ]
    true_labels = [
        [l_i for (p_i, l_i) in zip(prediction, label) if l_i != -100]
        for prediction, label in zip(predictions, labels)
    ]
    
    y_pred = [item for sublist in true_predictions for item in sublist]
    y_true = [item for sublist in true_labels for item in sublist]
    
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1
    }

def main():
    torch.cuda.empty_cache()
    
    print("Loading multi-modal GAT processor with OCR-Aware tokens...")
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=False)
    
    prescription_labels = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
    label2id = {l: i for i, l in enumerate(prescription_labels)}
    
    # Process inputs 
    train_ds, val_ds, test_ds = get_preprocessed_datasets(processor, label2id)
    
    print("Initializing Hybrid Graph Model for Dual-GPU...")
    model = LayoutLMv3GATForTokenClassification.from_pretrained(
        "microsoft/layoutlmv3-base", 
        num_labels=len(prescription_labels),
        ignore_mismatched_sizes=True
    )

    # Freeze the backbone 
    for name, param in model.named_parameters():
        if "layoutlmv3" in name:
            param.requires_grad = False
    # The Initialization Shockwave is too extreme even for PyTorch FP32.
    # The only mathematical way to train a deeply randomized GAT on top of a highly 
    # sensitive Vision Transformer is to cleanly sever the backpropagation. 
    optimizer_grouped_parameters = [
        {
            'params': [p for n, p in model.named_parameters() if 'layoutlmv3' in n and p.requires_grad],
            'lr': 2e-5  # Small LR for the pre-trained encoder
        },
        {
            'params': [p for n, p in model.named_parameters() if 'layoutlmv3' not in n and p.requires_grad],
            'lr': 5e-5  
        }
    ]
    optimizer = torch.optim.AdamW(optimizer_grouped_parameters, eps=1e-8)
    
    training_args = TrainingArguments(
        output_dir="../models/vaipe_hybrid_graph",
        num_train_epochs=150,              
        
        per_device_train_batch_size=110,   
        per_device_eval_batch_size=110,
    
        fp16=False,
        bf16=False,
        warmup_ratio=0.1,
        weight_decay=0.01,              
        max_grad_norm=1.0,               
        learning_rate=8e-5,              
        eval_strategy="epoch",           
        logging_strategy="epoch",        
        save_strategy="epoch",                     
        save_total_limit=2,
        load_best_model_at_end=True,     
        metric_for_best_model="f1",      
        greater_is_better=True,
        dataloader_num_workers=16,
        ddp_find_unused_parameters=True         
    )
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,             # Validation Test integrated exactly into the training run!
        compute_metrics=compute_metrics, # Precision, Recall, F1 natively implemented!
        data_collator=GraphDataCollator(processor.tokenizer, pad_to_multiple_of=8), 
        optimizers=(optimizer, None),
        callbacks=[EarlyStoppingCallback(early_stopping_patience=10)] # 🛡️ The Anti-Overfit Shield
    )
    
    print("💥 Firing up GPU-Accelerated End-to-End Graphic Attention Learning...")
    trainer.train()
    
    print("Saving the definitively trained Graph-Vision model...")
    trainer.save_model("../models/layoutlmv3_gatv6")
    
    print("\n=============================================")
    print("Evaluating against the Blind 10% Local Test Split...")
    test_metrics = trainer.evaluate(test_ds, metric_key_prefix="test")
    print(f"  ➜ Test Loss:      {test_metrics['test_loss']:.4f}")
    print(f"  ➜ Test Precision: {test_metrics['test_precision']:.4f}")
    print(f"  ➜ Test Recall:    {test_metrics['test_recall']:.4f}")
    print(f"  ➜ Test F1 Score:  {test_metrics['test_f1']:.4f}")
    print("=============================================\n")

if __name__ == "__main__":
    main()
