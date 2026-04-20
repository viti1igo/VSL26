"""
DESCRIPTION:
    This script preprocesses the VAIPE dataset for training a LayoutLMv3-based GAT model.
    It performs the following steps:
    1. Loads the VAIPE dataset from the specified path.
    2. Splits the dataset into training, validation, and testing sets.
    3. Preprocesses the dataset to extract tokens, bounding boxes, and labels.
    4. Converts the dataset to a format suitable for training a LayoutLMv3-based GAT model.
"""

import os
import json
from datasets import Dataset
from PIL import Image
import numpy as np
import torch
import pytesseract

def merge_words_to_lines(words, bboxes, confs, tolerance_y=10, tolerance_x=30):
    if not words: return [], []
    
    # Filter and Clean
    filtered = []
    for w, b, c in zip(words, bboxes, confs):
        w_clean = w.strip()
        if not w_clean: continue
        # Allow numbers and markers through regardless of confidence if they look vital
        if len(w_clean) < 2 and c < 30 and not w_clean.isdigit(): continue
        
        # Normalize markers during filtering
        w_norm = w_clean
        if any(m in w_clean.upper() for m in ["&L", "§L", "6L", "SOL:"]):
            w_norm = w_clean.upper().replace("&L", "SL").replace("§L", "SL").replace("6L", "SL").replace("SOL:", "SL:")
        
        mid_y = b[1] + (b[3] - b[1]) / 2
        filtered.append({"text": w_norm, "box": b, "mid_y": mid_y, "x1": b[0]})
        
    if not filtered: return [], []
    
    # Group into Rows by MidY (Primary sort by MidY)
    filtered.sort(key=lambda x: x["mid_y"])
    rows = []
    if filtered:
        curr_row = [filtered[0]]
        for i in range(1, len(filtered)):
            # If word is vertically close to the current row's average, group them
            if abs(filtered[i]["mid_y"] - curr_row[0]["mid_y"]) < tolerance_y:
                curr_row.append(filtered[i])
            else:
                rows.append(curr_row)
                curr_row = [filtered[i]]
        rows.append(curr_row)
        
    # Sort strictly by X and Merge with Marker Awareness
    merged_lines = []
    for row in rows:
        # Sort words in this row from Left to Right
        row.sort(key=lambda x: x["x1"])
        
        curr_text = row[0]["text"]
        curr_box = list(row[0]["box"])
        
        for i in range(1, len(row)):
            w = row[i]["text"]
            b = row[i]["box"]
            
            close_x = (b[0] - curr_box[2]) < tolerance_x
            # Explicit split if it looks like a Quantity marker
            is_qty_marker = any(w.upper().startswith(m) for m in ["SL", "§L", "&L", "6L", "SOL:"])
            
            if close_x and not is_qty_marker:
                curr_text += " " + w
                curr_box[0] = min(curr_box[0], b[0])
                curr_box[1] = min(curr_box[1], b[1])
                curr_box[2] = max(curr_box[2], b[2])
                curr_box[3] = max(curr_box[3], b[3])
            else:
                merged_lines.append((curr_text, curr_box))
                curr_text, curr_box = w, list(b)
        
        merged_lines.append((curr_text, curr_box))
        
    return list(zip(*merged_lines))

def get_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)
    return interArea / float(boxAArea + boxBArea - interArea)

def load_vaipe_p_dataset(base_path, use_ocr=True):
    data = []
    img_dir = os.path.join(base_path, "prescription/image")
    ann_dir = os.path.join(base_path, "prescription/label")
    
    if not os.path.exists(ann_dir):
        print(f"Error: {ann_dir} not found.")
        return Dataset.from_list([])

    json_files = [f for f in os.listdir(ann_dir) if f.endswith(".json")]
    print(f"Loading {len(json_files)} samples from {base_path} (OCR={use_ocr})...")
    
    for idx, f in enumerate(json_files):
        img_p = os.path.join(img_dir, f.replace(".json", ".jpg"))
        if not os.path.exists(img_p):
             img_p = os.path.join(img_dir, f.replace(".json", ".png"))
        
        if os.path.exists(img_p):
            with open(os.path.join(ann_dir, f), 'r', encoding='utf-8') as file:
                gt_ann = json.load(file)
            
            if use_ocr:
                image = Image.open(img_p).convert("RGB")
                custom_config = r'--oem 3 --psm 6'
                ocr_data = pytesseract.image_to_data(image, lang='vie', config=custom_config, output_type=pytesseract.Output.DICT)
                raw_words, raw_boxes, raw_confs = [], [], []
                for j in range(len(ocr_data['text'])):
                    txt = ocr_data['text'][j].strip()
                    if txt:
                        l, t, w, h = ocr_data['left'][j], ocr_data['top'][j], ocr_data['width'][j], ocr_data['height'][j]
                        raw_words.append(txt)
                        raw_boxes.append([l, t, l + w, t + h])
                        raw_confs.append(ocr_data['conf'][j])
                
                line_texts, line_boxes = merge_words_to_lines(raw_words, raw_boxes, raw_confs)
                
                # 🎯 Spatial Label Matcher (IoU)
                mapped_labels = []
                # Ground truth entries
                gt_entries = gt_ann if isinstance(gt_ann, list) else [] 
                
                for obox in line_boxes:
                    best_iou = 0
                    best_label = "other"
                    for gt in gt_entries:
                        # Normalize check
                        gt_box = gt.get("box", gt.get("bbox", []))
                        iou = get_iou(obox, gt_box)
                        if iou > best_iou:
                            best_iou = iou
                            best_label = gt.get("label", gt.get("ner_tags", "other"))
                    
                    # If it's a Drugname, but overlap is Low, we still label it if it hits the center
                    if best_iou < 0.1: best_label = "other"
                    mapped_labels.append(best_label)

                data.append({
                    "image_path": img_p,
                    "tokens": list(line_texts),
                    "bboxes": list(line_boxes),
                    "ner_tags": mapped_labels
                })
            else:
                # Fallback to pure JSON loaders
                if isinstance(gt_ann, list):
                    data.append({
                        "image_path": img_p,
                        "tokens": [item["text"] for item in gt_ann],
                        "bboxes": [item["box"] for item in gt_ann],
                        "ner_tags": [item["label"] for item in gt_ann]
                    })
                else:
                    data.append({
                        "image_path": img_p,
                        "tokens": gt_ann.get("words", []),
                        "bboxes": gt_ann.get("bboxes", []),
                        "ner_tags": gt_ann.get("ner_tags", [])
                    })
        
        if (idx+1) % 50 == 0:
            print(f"  Processed {idx+1}/{len(json_files)} samples...")
            
    return Dataset.from_list(data)

def get_preprocessed_datasets(processor, label2id_p, train_path="../public_train"):
    train_raw = load_vaipe_p_dataset(train_path)
    
    # 8-1-1 Split
    train_test_split = train_raw.train_test_split(test_size=0.2, seed=42)
    temp_split = train_test_split['test'].train_test_split(test_size=0.5, seed=42)
    
    train_dataset = train_test_split['train']
    val_dataset = temp_split['train']
    test_dataset = temp_split['test']
    
    print(f"Dataset split: Training: {len(train_dataset)}, Validation: {len(val_dataset)}, Test: {len(test_dataset)}")

    def preprocess_stage2(examples):
        images = [Image.open(path).convert("RGB") for path in examples["image_path"]]
        
        # Label Guard (0-5) ensuring padding resilience
        cleaned_labels = []
        for label_list in examples["ner_tags"]:
            cleaned_labels.append([min(label2id_p.get(l, 5) if isinstance(l, str) else l, 5) for l in label_list])
        
        # Spatial Guard ensuring bounding boxes never exceed [0, 1000]
        cleaned_boxes = []
        for box_list in examples["bboxes"]:
            safe_boxes = []
            for box in box_list:
                safe_box = [max(0, min(1000, int(coord))) for coord in box]
                safe_boxes.append(safe_box)
            cleaned_boxes.append(safe_boxes)
        
        # EXPLICIT KEYWORD ASSIGNMENTS (Fixes token-box mismatch bugs)
        encoded_inputs = processor(
            images=images,
            text=examples['tokens'],
            boxes=cleaned_boxes,
            word_labels=cleaned_labels,
            truncation=True,
            padding="max_length",
            max_length=512,
            return_tensors="pt",
        )

        # Robust conversion to numpy with correct dtypes.
        def _to_np(x, dtype=None):
            if torch.is_tensor(x):
                arr = x.detach().cpu().numpy()
            elif isinstance(x, list) and len(x) > 0 and torch.is_tensor(x[0]):
                arr = torch.stack(x).detach().cpu().numpy()
            else:
                arr = np.asarray(x)
            return arr.astype(dtype) if dtype is not None else arr

        return {
            "input_ids":      _to_np(encoded_inputs["input_ids"],      np.int64),
            "attention_mask": _to_np(encoded_inputs["attention_mask"], np.int64),
            "bbox":           _to_np(encoded_inputs["bbox"],           np.int64),
            "labels":         _to_np(encoded_inputs["labels"],         np.int64),
            "pixel_values":   _to_np(encoded_inputs["pixel_values"],   np.float32),
        }
            
    print("Mapping datasets...")
    # remove_columns drops the raw "image_path" / "tokens" / "bboxes" / "ner_tags"
    # columns — otherwise the collator tries to tensor-ify strings and crashes.
    train_ds = train_dataset.map(preprocess_stage2, batched=True, batch_size=2,
                                 remove_columns=train_dataset.column_names)
    val_ds   = val_dataset.map(preprocess_stage2, batched=True, batch_size=2,
                               remove_columns=val_dataset.column_names)
    test_ds  = test_dataset.map(preprocess_stage2, batched=True, batch_size=2,
                                remove_columns=test_dataset.column_names)

    # Force torch tensors with correct dtypes so the collator receives
    # real float32 pixel_values, not Python lists.
    cols = ["input_ids", "attention_mask", "bbox", "labels", "pixel_values"]
    train_ds = train_ds.with_format("torch", columns=cols)
    val_ds   = val_ds.with_format("torch", columns=cols)
    test_ds  = test_ds.with_format("torch", columns=cols)

    return train_ds, val_ds, test_ds
