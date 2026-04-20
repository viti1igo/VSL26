"""
DESCRIPTION:
    This script implements a custom data collator for the LayoutLMv3GAT model.
    It performs the following steps:
    1. Converts batch layouts into Sparse Directed Graphs per document.
    2. Computes spatial features for each node in the graph.
    3. Appends edges to the graph based on the spatial features.
    4. Returns the batch with the added graph features.
"""
import torch
import math
from transformers import DataCollatorForTokenClassification

class GraphDataCollator(DataCollatorForTokenClassification):
    def __call__(self, features, return_tensors=None):
        # 1. Base HuggingFace sequence padding processing
        batch = super().__call__(features, return_tensors="pt")
        bz, seq_len, _ = batch["bbox"].shape
        edge_index_list = []
        spatial_features_list = []
        
        # 2. Convert batch layouts into Sparse Directed Graphs per document
        # --- BLAZING FAST VECTORIZED TENSOR GRAPH ASSEMBLER ---
        for i in range(bz):
            bboxes = batch["bbox"][i].float()
            
            centers_x = (bboxes[:, 0] + bboxes[:, 2]) / 2.0
            centers_y = (bboxes[:, 1] + bboxes[:, 3]) / 2.0
            widths = bboxes[:, 2] - bboxes[:, 0]
            heights = bboxes[:, 3] - bboxes[:, 1]
            
            spatial_feats = torch.zeros((seq_len, 8))
            edges = []
            
            mask = batch["attention_mask"][i] == 1
            valid_nodes = torch.nonzero(mask).squeeze(-1)
            n = valid_nodes.size(0)
            
            if n > 1:
                cx = centers_x[valid_nodes]
                cy = centers_y[valid_nodes]
                
                # Vectorized distance and angle computation (O(1) in PyTorch vs O(N^2) in Python)
                dx = cx.unsqueeze(1) - cx.unsqueeze(0)
                dy = cy.unsqueeze(1) - cy.unsqueeze(0)
                
                dist = torch.sqrt(dx**2 + dy**2)
                angle = torch.atan2(dy, dx) * (180.0 / math.pi)
                
                dist.fill_diagonal_(float('inf'))
                
                # Boolean Masks for specific direction flows
                right_mask = (angle >= -45) & (angle < 45)
                down_mask = (angle >= 45) & (angle < 135)
                up_mask = (angle >= -135) & (angle < -45)
                left_mask = ~(right_mask | down_mask | up_mask) & (dist != float('inf'))
                
                def get_nearest(mask):
                    d = torch.where(mask, dist, float('inf'))
                    min_dist, min_idx = d.min(dim=1)
                    return min_dist, min_idx, (min_dist != float('inf'))
                
                d_right, i_right, m_right = get_nearest(right_mask)
                d_down, i_down, m_down = get_nearest(down_mask)
                d_up, i_up, m_up = get_nearest(up_mask)
                d_left, i_left, m_left = get_nearest(left_mask)

                d_up = torch.where(torch.isinf(d_up), torch.tensor(1000.0).to(d_up.device), d_up)
                d_down = torch.where(torch.isinf(d_down), torch.tensor(1000.0).to(d_down.device), d_down)
                d_left = torch.where(torch.isinf(d_left), torch.tensor(1000.0).to(d_left.device), d_left)
                d_right = torch.where(torch.isinf(d_right), torch.tensor(1000.0).to(d_right.device), d_right)
                
                # Append connections securely via global offset for PyG Batching
                global_offset = i * seq_len
                global_valid_nodes = global_offset + valid_nodes
                
                def append_edges(m, tgt_idx):
                    if m.any():
                        sources = global_valid_nodes[m]
                        targets = global_valid_nodes[tgt_idx[m]]
                        edges.append(torch.stack([sources, targets], dim=0))
                        
                append_edges(m_right, i_right)
                append_edges(m_down, i_down)
                append_edges(m_up, i_up)
                append_edges(m_left, i_left)
                
                # Vectorized Structural Priors (s_v in R^8)
                v_cpu = valid_nodes.cpu()
                spatial_feats[v_cpu, 0] = widths[v_cpu] / 1000.0
                spatial_feats[v_cpu, 1] = heights[v_cpu] / 1000.0
                spatial_feats[v_cpu, 2] = cy.cpu() / 1000.0 
                spatial_feats[v_cpu, 3] = cx.cpu() / 1000.0 
                spatial_feats[v_cpu, 4] = torch.where(m_up, d_up, torch.tensor(1000.0)).cpu() / 1000.0
                spatial_feats[v_cpu, 5] = torch.where(m_down, d_down, torch.tensor(1000.0)).cpu() / 1000.0
                spatial_feats[v_cpu, 6] = torch.where(m_left, d_left, torch.tensor(1000.0)).cpu() / 1000.0
                spatial_feats[v_cpu, 7] = torch.where(m_right, d_right, torch.tensor(1000.0)).cpu() / 1000.0
                
            if edges:
                edge_index_list.append(torch.cat(edges, dim=1))
            else:
                edge_index_list.append(torch.empty((2, 0), dtype=torch.long))
            spatial_features_list.append(spatial_feats)
            
        batch["edge_index"] = torch.cat(edge_index_list, dim=1) if edge_index_list else torch.empty((2, 0), dtype=torch.long)
        batch["spatial_features"] = torch.stack(spatial_features_list, dim=0)
        
        return batch
