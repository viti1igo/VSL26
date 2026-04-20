"""
DESCRIPTION:
    This script implements the LayoutLMv3GAT model for token classification.
    It combines the LayoutLMv3 encoder with a Graph Attention Network (GAT) to
    capture both textual and spatial relationships between tokens.
"""
import torch
import torch.nn as nn
from transformers import LayoutLMv3Model, LayoutLMv3PreTrainedModel
from torch_geometric.nn import GATv2Conv
from torch_geometric.utils import add_self_loops, coalesce

_DEBUG_STEPS = {"count": 0, "max": 3}

def _nan_report(name, t):
    if t is None or not torch.is_tensor(t):
        return False
    bad = torch.isnan(t).any().item() or torch.isinf(t).any().item()
    if _DEBUG_STEPS["count"] < _DEBUG_STEPS["max"]:
        print(f"  [nan-check] {name:>22s} shape={tuple(t.shape)} "
              f"min={t.float().min().item():.3e} max={t.float().max().item():.3e} "
              f"nan={torch.isnan(t).any().item()} inf={torch.isinf(t).any().item()}",
              flush=True)
    return bad

class LayoutLMv3GATForTokenClassification(LayoutLMv3PreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels

        self.layoutlmv3 = LayoutLMv3Model(config)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)

        self.spatial_proj = nn.LayerNorm(8)
        self.input_norm = nn.LayerNorm(config.hidden_size + 8)

        # 🔧 Dimension Reduction for Stability
        self.proj = nn.Linear(config.hidden_size + 8, 256)
        self.proj_norm = nn.LayerNorm(256)

        # 🔧 GATv2 Layers (Reduced heads for stability)
        self.gat1 = GATv2Conv(256, 128, heads=4, concat=True, add_self_loops=True)
        self.norm1 = nn.LayerNorm(512)

        self.gat2 = GATv2Conv(512, 128, heads=4, concat=True, add_self_loops=True)
        self.norm2 = nn.LayerNorm(512)

        self.gat3 = GATv2Conv(512, 128, heads=4, concat=True, add_self_loops=True)
        self.norm3 = nn.LayerNorm(512)

        self.classifier = nn.Linear(256, config.num_labels)
        self.post_init()
        
        # 🔨 Initialization Guard: prevents huge random weights
        with torch.no_grad():
            for m in [self.gat1, self.gat2, self.gat3]:
                if hasattr(m, 'lin_l'): nn.init.xavier_uniform_(m.lin_l.weight, gain=0.01)
                if hasattr(m, 'lin_r'): nn.init.xavier_uniform_(m.lin_r.weight, gain=0.01)
                if hasattr(m, 'att'): nn.init.xavier_uniform_(m.att, gain=0.01)

    def forward(self, input_ids=None, bbox=None, attention_mask=None, token_type_ids=None, pixel_values=None,
                labels=None, edge_index=None, spatial_features=None, **kwargs):

        first = _DEBUG_STEPS["count"] < _DEBUG_STEPS["max"]
        if first:
            print(f"\n=== Forward step {_DEBUG_STEPS['count']} ===", flush=True)

        # 1. Base Encoder
        if bbox is not None: bbox = bbox.clamp(0, 1000)
        outputs = self.layoutlmv3(
            input_ids=input_ids, bbox=bbox, attention_mask=attention_mask,
            token_type_ids=token_type_ids, pixel_values=pixel_values,
        )
        sequence_output = outputs[0][:, :input_ids.shape[1], :]
        sequence_output = self.dropout(sequence_output)
        
        bz, seq_len, hidden_dim = sequence_output.shape
        device = sequence_output.device

        # 2. Graph Preparation
        if edge_index is None: edge_index = torch.empty((2, 0), dtype=torch.long, device=device)
        if spatial_features is None: spatial_features = torch.zeros((bz, seq_len, 8), device=device)

        h = sequence_output.reshape(-1, hidden_dim)
        s = spatial_features.reshape(-1, 8).to(device)
        s = self.spatial_proj(torch.nan_to_num(s, nan=0.0))
        
        x = torch.cat([h, s], dim=-1)
        x = self.input_norm(x)
        x = self.proj_norm(torch.nn.functional.relu(self.proj(x)))
        
        if first: _nan_report("x_pre_gat", x)

        # 🔨 Robust Graph Preparation
        num_nodes = x.size(0)
        if edge_index.numel() > 0:
            if edge_index.max() >= num_nodes or edge_index.min() < 0:
                if first: print(f"⚠️ FORCE FIX: edge_index out of range! max={edge_index.max()}, num_nodes={num_nodes}")
                mask = (edge_index[0] < num_nodes) & (edge_index[1] < num_nodes)
                edge_index = edge_index[:, mask]

        edge_index, _ = add_self_loops(edge_index, num_nodes=num_nodes)
        edge_index = coalesce(edge_index)

        # 3. GAT Blocks (Identity Isolation Test)
        # x1 = self.norm1(torch.nn.functional.elu(self.gat1(x, edge_index)))
        # x2 = self.norm2(x1 + torch.nn.functional.elu(self.gat2(x1, edge_index)))
        # x = self.norm3(x2 + torch.nn.functional.elu(self.gat3(x2, edge_index)))
        pass 
        # x is 256 here

        # 4. Classification
        logits = self.classifier(x).view(bz, seq_len, self.num_labels)
        if first:
            _nan_report("final_logits", logits)
            _DEBUG_STEPS["count"] += 1

        # 5. Loss with ignore_index -100
        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss(ignore_index=-100)
            available_labels = labels.view(-1)
            # Filter out NaNs from logits for safety before loss
            if torch.isnan(logits).any():
                logits = torch.nan_to_num(logits, nan=0.0)
                
            if (available_labels != -100).any():
                loss = loss_fct(logits.view(-1, self.num_labels), available_labels)
            else:
                loss = logits.sum() * 0.0

        return {"loss": loss, "logits": logits} if loss is not None else {"logits": logits}