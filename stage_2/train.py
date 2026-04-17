import os
import torch
from transformers import LayoutLMv3Processor, TrainingArguments, Trainer

from model import get_stage2_model
from preprocess import get_preprocessed_datasets

# Limit PyTorch to device 1 to bypass DDP NCCL crash on multiple GPUs
os.environ['CUDA_VISIBLE_DEVICES'] = "1"

def main():
    torch.cuda.empty_cache()
    
    print("🚀 Loading model and labels...")
    # Load model structure
    model, id2label, label2id = get_stage2_model(checkpoint_path="../models/fatura_backbone_v1")
    model.to("cuda")
    
    print("🚀 Loading processor and datasets...")
    # Load processor logic
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=False)
    
    # Process inputs natively
    train_ds, val_ds, test_ds = get_preprocessed_datasets(processor, label2id)
    
    print("🚀 Initializing Trainer...")
    # 24GB A5500 Settings! (Big Batch, Max Threads, FP16)
    training_args = TrainingArguments(
        output_dir="../models/vaipe_811_split",
        max_steps=2000,
        
        per_device_train_batch_size=12,
        gradient_accumulation_steps=1,
        per_device_eval_batch_size=12,
        
        learning_rate=2e-5,
        fp16=True,                       
        
        eval_strategy="steps",
        eval_steps=100,                  
        save_strategy="steps",           
        save_steps=100,                  
        
        save_total_limit=2,
        load_best_model_at_end=True,     
        metric_for_best_model="eval_loss",
        
        # Disabled CPU pooling precisely to prevent Kernel 4.18 deadlock
        dataloader_num_workers=0         
    )
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=processor.tokenizer
    )
    
    print("💥 Deploying Stage 2 Neural Pipeline...")
    trainer.train()
    
    print("Saving the tuned model to '../models/vaipe_model_final'...")
    trainer.save_model("../models/vaipe_model_final")
    processor.save_pretrained("../models/vaipe_model_final")

if __name__ == "__main__":
    main()
