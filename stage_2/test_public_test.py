"""
DESCRIPTION:
    This script tests the trained LayoutLMv3GAT model on the public test set.
    It performs the following steps:
    1. Loads the trained LayoutLMv3GAT model from the specified path.
    2. Loads the public test set.
    3. Runs inference on the public test set.
    4. Saves the results to a CSV file.
"""
import os
import torch
import pandas as pd
from PIL import Image
from transformers import LayoutLMv3Processor

from gat_model import LayoutLMv3GATForTokenClassification
from preprocess import load_vaipe_p_dataset
from graph_collator import GraphDataCollator

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
        
    return zip(*merged_lines)

def main():
    print("Initializing inference pipeline with High-Granularity OCR (lang=vie)...")
    # apply_ocr=False (run Tesseract manually to control merging)
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=False)
    
    prescription_labels = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
    id2label = {i: l for i, l in enumerate(prescription_labels)}
    
    model_path = "../models/layoutlmv3_gatv5"
    if not os.path.exists(model_path):
        print(f"Warning: {model_path} missing.")
        model_path = "microsoft/layoutlmv3-base"
        
    model = LayoutLMv3GATForTokenClassification.from_pretrained(
        model_path, 
        num_labels=len(prescription_labels),
        ignore_mismatched_sizes=True
    )
    model.to("cuda")
    model.eval()

    print("\nLoading public test images...")
    img_dir = "../public_test/prescription/image"
    image_files = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    print(f"Found {len(image_files)} images.")

    all_predictions = []

    print("Running Graphical Inference with Refined Line Blender...")
    for i, img_path in enumerate(image_files):
        image = Image.open(img_path).convert("RGB")
        width, height = image.size
        
        # Manual OCR + Tesseract Optimization
        custom_config = r'--oem 3 --psm 6'
        ocr_data = pytesseract.image_to_data(image, lang='vie', config=custom_config, output_type=pytesseract.Output.DICT)
        raw_words = []
        raw_boxes = []
        raw_confs = []
        
        for j in range(len(ocr_data['text'])):
            txt = ocr_data['text'][j].strip()
            if txt:
                l, t, w, h = ocr_data['left'][j], ocr_data['top'][j], ocr_data['width'][j], ocr_data['height'][j]
                raw_words.append(txt)
                raw_boxes.append([l, t, l + w, t + h])
                raw_confs.append(ocr_data['conf'][j])
        
        # Merge Words into Entities
        line_texts, line_boxes = merge_words_to_lines(raw_words, raw_boxes, raw_confs)
        
        if not line_texts:
            print(f"  Warning: No text found in {img_path}")
            continue

        line_texts = list(line_texts)
        line_boxes = list(line_boxes)

        # Spatial Guard (0-1000) for LayoutLMv3
        safe_boxes = []
        for box in line_boxes:
            box_1000 = [
                int(1000 * (box[0] / width)),
                int(1000 * (box[1] / height)),
                int(1000 * (box[2] / width)),
                int(1000 * (box[3] / height))
            ]
            safe_boxes.append([max(0, min(1000, c)) for c in box_1000])

        # Standard Processor call (using merged lines as nodes)
        encoding = processor(
            images=image, 
            text=line_texts,
            boxes=safe_boxes,
            truncation=True, 
            padding="max_length", 
            max_length=512,
            return_tensors="pt"
        )
        
        batch = dict(encoding)
        
        # Manual Graph Spatial Vectorizer
        sz = batch["input_ids"].shape[1]
        spatial_feats = torch.zeros((1, sz, 8), dtype=torch.float32)
        edges = []
        mask = batch["attention_mask"][0] == 1
        valid_nodes = torch.nonzero(mask).squeeze(-1)
        
        if valid_nodes.numel() > 0:
            bboxes = batch["bbox"][0]
            bbox_norm = bboxes.float() / 1000.0
            spatial_feats[0, :sz, :4] = bbox_norm
            cx = bboxes[:, 0] + (bboxes[:, 2] - bboxes[:, 0]) / 2.0
            cy = bboxes[:, 1] + (bboxes[:, 3] - bboxes[:, 1]) / 2.0
            dx = cx.unsqueeze(1) - cx.unsqueeze(0)
            dy = cy.unsqueeze(1) - cy.unsqueeze(0)
            dist = torch.sqrt(dx**2 + dy**2)
            angle = torch.atan2(dy, dx) * (180.0 / 3.14159)
            dist.fill_diagonal_(float('inf'))
            d_up = torch.where((angle >= -135) & (angle < -45), dist, float('inf')).min(dim=1)
            d_down = torch.where((angle >= 45) & (angle < 135), dist, float('inf')).min(dim=1)
            d_left = torch.where((angle >= 135) | (angle < -135), dist, float('inf')).min(dim=1)
            d_right = torch.where((angle >= -45) & (angle < 45), dist, float('inf')).min(dim=1)
            for j, d_tuple in enumerate([d_up, d_down, d_left, d_right]):
                m_val = d_tuple[0] != float('inf')
                spatial_feats[0, valid_nodes, 4 + j] = torch.where(m_val[valid_nodes], d_tuple[0][valid_nodes], torch.tensor(1000.0)) / 1000.0
                valid_m = m_val[valid_nodes]
                if valid_m.any():
                    sources = valid_nodes[valid_m]
                    targets = d_tuple[1][valid_nodes][valid_m]
                    edges.append(torch.stack([sources, targets], dim=0))
                    
        batch["spatial_features"] = spatial_feats
        batch["edge_index"] = torch.cat(edges, dim=1) if len(edges) > 0 else torch.empty((2,0), dtype=torch.long)
        batch = {k: v.to("cuda") for k, v in batch.items()}
        
        with torch.no_grad():
            outputs = model(**batch)
            logits = outputs["logits"]
            preds = logits.argmax(-1).squeeze().tolist()
            
        word_ids = encoding.word_ids(batch_index=0)
        filename = os.path.basename(img_path)
        
        # Entity Merging: Consolidation logic
        predicted_word_labels = []
        previous_word_idx = None
        for idx, word_idx in enumerate(word_ids):
            if word_idx is None: continue
            if word_idx != previous_word_idx:
                predicted_word_labels.append(preds[idx])
            previous_word_idx = word_idx
            
        num_preds = min(len(line_texts), len(predicted_word_labels))
        
        for j in range(num_preds):
            box = line_boxes[j]
            all_predictions.append({
                "file_name": filename,
                "item_id": j + 1,
                "text_token": line_texts[j],
                "ner_label": id2label.get(predicted_word_labels[j], "other"),
                "xmin": box[0],
                "ymin": box[1],
                "xmax": box[2],
                "ymax": box[3]
            })
            
        if (i+1) % 10 == 0 or (i+1) == len(image_files):
            print(f"  Processed {i+1}/{len(image_files)} prescriptions...")

    df = pd.DataFrame(all_predictions)
    output_csv = "../public_test/prescription/gat_v6.csv"
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\n🎉 Graphic Inference complete! Line-merged results saved to '{output_csv}'")


if __name__ == "__main__":
    main()
