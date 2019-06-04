from typing import Dict, Optional

import torch
from torch import nn

from updown.modules.attention import LinearAttentionWithProjection


class UpDownCell(nn.Module):
    def __init__(
        self,
        image_feature_size: int,
        embedding_size: int,
        hidden_size: int,
        attention_projection_size: int,
    ):
        super().__init__()

        self.image_feature_size = image_feature_size
        self.embedding_size = embedding_size
        self.hidden_size = hidden_size
        self.attention_projection_size = attention_projection_size

        self._attention_lstm_cell = nn.LSTMCell(
            self.embedding_size + self.image_feature_size + self.hidden_size, self.hidden_size
        )
        self._butd_attention = LinearAttentionWithProjection(
            self.hidden_size, self.image_feature_size, self.attention_projection_size
        )
        self._language_lstm_cell = nn.LSTMCell(
            self.image_feature_size + self.hidden_size, self.hidden_size
        )

    def forward(
        self,
        image_features: torch.FloatTensor,
        token_embedding: torch.FloatTensor,
        states: Optional[Dict[str, torch.FloatTensor]] = None,
    ):

        batch_size = image_features.size(0)

        # shape: (batch_size, image_feature_size)
        average_image_features = torch.mean(image_features, dim=1)

        # Initialize (h1, c1), (h2, c2) is not passed:
        if states is None:
            state = image_features.new_zeros((batch_size, self.hidden_size))
            states = {
                "h1": state.clone(),
                "c1": state.clone(),
                "h2": state.clone(),
                "c2": state.clone(),
            }

        # shape: (batch_size, image_feature_size)
        averaged_image_features = torch.mean(image_features, dim=1)

        # shape: (batch_size, embedding_size + image_feature_size + hidden_size)
        attention_lstm_cell_input = torch.cat(
            [token_embedding, averaged_image_features, states["h2"]], dim=1
        )
        states["h1"], states["c1"] = self._attention_lstm_cell(
            attention_lstm_cell_input, (states["h1"], states["c1"])
        )

        # shape: (batch_size, num_boxes)
        attention_weights = self._butd_attention(
            states["h1"],
            image_features,
            matrix_mask=torch.sum(torch.abs(image_features), dim=-1) != 0,
        )

        # shape: (batch_size, num_boxes, image_feature_size)
        weighted_image_features = attention_weights.unsqueeze(-1) * image_features

        # shape: (batch_size, image_feature_size)
        attended_image_features = torch.sum(weighted_image_features, dim=1)

        # shape: (batch_size, image_feature_size + hidden_size)
        language_lstm_cell_input = torch.cat([attended_image_features, states["h1"]], dim=1)
        states["h2"], states["c2"] = self._language_lstm_cell(
            language_lstm_cell_input, (states["h2"], states["c2"])
        )

        return states["h2"], states