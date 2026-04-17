import os
import json
from datasets import Dataset
from PIL import Image

def load_vaipe_p_dataset(base_path):
    data = []
    # If starting from 'stage_2' folder, the base path should probably go back one folder
    # but we'll assume base_path provides the correct absolute/relative target.
    img_dir = os.path.join(base_path, "prescription/image")
    ann_dir = os.path.join(base_path, "prescription/label")
    
    if not os.path.exists(ann_dir):
        print(f"Error: {ann_dir} not found.")
        return Dataset.from_list([])

    json_files = [f for f in os.listdir(ann_dir) if f.endswith(".json")]
    
    for f in json_files:
        img_name = f.replace(".json", ".jpg")
        img_p = os.path.join(img_dir, img_name)
        
        # Check both extensions
        if not os.path.exists(img_p):
             img_p = os.path.join(img_dir, f.replace(".json", ".png"))
        
        if os.path.exists(img_p):
            with open(os.path.join(ann_dir, f), 'r', encoding='utf-8') as file:
                ann = json.load(file)
            
            # Handle possible nested list structure in HuggingFace/VAIPE datasets
            if isinstance(ann, list):
                data.append({
                    "image_path": img_p,
                    "tokens": [item["text"] for item in ann],
                    "bboxes": [item["box"] for item in ann],
                    "ner_tags": [item["label"] for item in ann]
                })
            else:
                data.append({
                    "image_path": img_p,
                    "tokens": ann.get("words", []),
                    "bboxes": ann.get("bboxes", []),
                    "ner_tags": ann.get("ner_tags", [])
                })
    return Dataset.from_list(data)

def get_preprocessed_datasets(processor, label2id_p, train_path="../public_train", test_path="../public_test"):
    train_raw = load_vaipe_p_dataset(train_path)
    test_raw = load_vaipe_p_dataset(test_path)
    
    # 8-1-1 Split
    train_test_split = train_raw.train_test_split(test_size=0.2, seed=42)
    temp_split = train_test_split['test'].train_test_split(test_size=0.5, seed=42)
    
    train_dataset = train_test_split['train']
    val_dataset = temp_split['train']
    test_dataset = temp_split['test']
    
    print(f"Dataset split: Training: {len(train_dataset)}, Validation: {len(val_dataset)}, Test: {len(test_dataset)}")

    def preprocess_stage2(examples):
        images = [Image.open(path).convert("RGB") for path in examples["image_path"]]
        
        # 1. Label Guard (0-5) ensuring padding resilience
        cleaned_labels = []
        for label_list in examples["ner_tags"]:
            cleaned_labels.append([min(label2id_p.get(l, 5) if isinstance(l, str) else l, 5) for l in label_list])
        
        # 2. Spatial Guard ensuring bounding boxes never exceed [0, 1000]
        cleaned_boxes = []
        for box_list in examples["bboxes"]:
            safe_boxes = []
            for box in box_list:
                safe_box = [max(0, min(1000, int(coord))) for coord in box]
                safe_boxes.append(safe_box)
            cleaned_boxes.append(safe_boxes)
        
        # EXPLICIT KEYWORD ASSIGNMENTS (Fixes token-box mismatch bugs)
        return processor(
            images=images, 
            text=examples["tokens"], 
            boxes=cleaned_boxes, 
            word_labels=cleaned_labels, 
            truncation=True, 
            padding="max_length", 
            max_length=512
        )
        
    print("Mapping datasets...")
    train_ds = train_dataset.map(preprocess_stage2, batched=True, batch_size=2)
    val_ds = val_dataset.map(preprocess_stage2, batched=True, batch_size=2)
    test_ds = test_dataset.map(preprocess_stage2, batched=True, batch_size=2)
    
    return train_ds, val_ds, test_ds
