import os
import torch
from transformers import LayoutLMv3ForTokenClassification

def get_stage2_model(checkpoint_path="../models/fatura_backbone_v1"):
    """
    Initializes and returns the LayoutLMv3 model for VAIPE Stage 2.
    """
    prescription_labels = ["date", "diagnose", "usage", "quantity", "drugname", "other"]
    id2label_p = {i: l for i, l in enumerate(prescription_labels)}
    label2id_p = {l: i for i, l in enumerate(prescription_labels)}

    # We load from the Stage 1 backbone where shape size might differ
    model = LayoutLMv3ForTokenClassification.from_pretrained(
        checkpoint_path,
        num_labels=len(prescription_labels), 
        id2label=id2label_p,
        label2id=label2id_p,
        ignore_mismatched_sizes=True 
    )
    
    return model, id2label_p, label2id_p
