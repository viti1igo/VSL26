"""Runtime for the recovered LayoutLMv3GAT token-classification checkpoint.

This mirrors the `stage_2/gat_model.py` architecture in the GitHub master
branch. The checkpoint contains GATv2 layer weights, but that source disables
the GAT blocks in `forward`; the classifier is trained over a 256-d projection
of LayoutLMv3 token embeddings plus 8 spatial features.
"""

from __future__ import annotations

from typing import Any

import torch
from torch import nn
from torch_geometric.nn import GATv2Conv
from transformers import LayoutLMv3Model, LayoutLMv3PreTrainedModel
from transformers.modeling_outputs import TokenClassifierOutput


class LayoutLMv3GATForTokenClassification(LayoutLMv3PreTrainedModel):
    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.num_labels = int(getattr(config, "num_labels", 6) or 6)
        self.layoutlmv3 = LayoutLMv3Model(config)
        self.dropout = nn.Dropout(float(getattr(config, "hidden_dropout_prob", 0.1)))
        self.spatial_proj = nn.LayerNorm(8)
        self.input_norm = nn.LayerNorm(config.hidden_size + 8)
        self.proj = nn.Linear(config.hidden_size + 8, 256)
        self.proj_norm = nn.LayerNorm(256)
        self.gat1 = GATv2Conv(256, 128, heads=4, concat=True, add_self_loops=True)
        self.norm1 = nn.LayerNorm(512)
        self.gat2 = GATv2Conv(512, 128, heads=4, concat=True, add_self_loops=True)
        self.norm2 = nn.LayerNorm(512)
        self.gat3 = GATv2Conv(512, 128, heads=4, concat=True, add_self_loops=True)
        self.norm3 = nn.LayerNorm(512)
        self.classifier = nn.Linear(256, self.num_labels)
        self.post_init()

    def forward(
        self,
        input_ids: torch.Tensor | None = None,
        bbox: torch.Tensor | None = None,
        attention_mask: torch.Tensor | None = None,
        token_type_ids: torch.Tensor | None = None,
        pixel_values: torch.Tensor | None = None,
        labels: torch.Tensor | None = None,
        edge_index: torch.Tensor | None = None,
        spatial_features: torch.Tensor | None = None,
        **kwargs: Any,
    ) -> TokenClassifierOutput:
        if bbox is not None:
            bbox = bbox.clamp(0, 1000)

        outputs = self.layoutlmv3(
            input_ids=input_ids,
            bbox=bbox,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            pixel_values=pixel_values,
            **kwargs,
        )
        sequence_output = outputs[0][:, : input_ids.shape[1], :]
        sequence_output = self.dropout(sequence_output)
        batch_size, seq_len, hidden_dim = sequence_output.shape
        device = sequence_output.device

        if spatial_features is None:
            spatial_features = torch.zeros((batch_size, seq_len, 8), device=device)
        else:
            spatial_features = spatial_features.to(device)

        h = sequence_output.reshape(-1, hidden_dim)
        s = spatial_features.reshape(-1, 8)
        s = self.spatial_proj(torch.nan_to_num(s, nan=0.0))
        x = torch.cat([h, s], dim=-1)
        x = self.input_norm(x)
        x = self.proj_norm(torch.nn.functional.relu(self.proj(x)))

        # Intentionally matches GitHub `stage_2/gat_model.py`: GAT blocks are
        # defined and checkpointed but disabled in the saved forward path.
        logits = self.classifier(x).view(batch_size, seq_len, self.num_labels)

        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss(ignore_index=-100)
            if torch.isnan(logits).any():
                logits = torch.nan_to_num(logits, nan=0.0)
            if (labels.view(-1) != -100).any():
                loss = loss_fct(logits.view(-1, self.num_labels), labels.view(-1))
            else:
                loss = logits.sum() * 0.0

        return TokenClassifierOutput(
            loss=loss,
            logits=logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )
