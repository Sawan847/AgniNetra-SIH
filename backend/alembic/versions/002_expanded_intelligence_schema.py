"""Expanded intelligence schema: event_id, raw_data, 35+ features, two-stage predictions, analyst feedback fields

Revision ID: 002_expanded_intelligence_schema
Revises: 001_initial_schema
Create Date: 2024-09-10 18:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_expanded_intelligence_schema"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Hotspots: add event_id and raw_data
    op.add_column("hotspots", sa.Column("event_id", sa.String(100), nullable=True))
    op.create_index("idx_hotspots_event_id", "hotspots", ["event_id"], unique=True)
    op.add_column("hotspots", sa.Column("raw_data", sa.JSON(), nullable=True))

    # 2. Hotspot Features: add spatial proximity, temporal recurrence, cluster, and spectral columns
    op.add_column("hotspot_features", sa.Column("is_inside_facility", sa.Boolean(), server_default="false", nullable=True))
    op.add_column("hotspot_features", sa.Column("nearby_facility_count_1km", sa.Integer(), server_default="0", nullable=True))
    op.add_column("hotspot_features", sa.Column("nearby_facility_count_5km", sa.Integer(), server_default="0", nullable=True))
    op.add_column("hotspot_features", sa.Column("dist_nearest_cropland", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("dist_nearest_mine", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("dist_nearest_settlement", sa.Float(), nullable=True))

    op.add_column("hotspot_features", sa.Column("nearby_hotspot_count_30d", sa.Integer(), server_default="0", nullable=True))
    op.add_column("hotspot_features", sa.Column("nearby_hotspot_count_90d", sa.Integer(), server_default="0", nullable=True))
    op.add_column("hotspot_features", sa.Column("persistence_score_30d", sa.Float(), server_default="0.0", nullable=True))
    op.add_column("hotspot_features", sa.Column("recurrence_rate", sa.Float(), server_default="0.0", nullable=True))

    op.add_column("hotspot_features", sa.Column("historical_median_frp", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("historical_max_frp", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("frp_to_historical_ratio", sa.Float(), nullable=True))

    op.add_column("hotspot_features", sa.Column("cluster_size", sa.Integer(), server_default="1", nullable=True))
    op.add_column("hotspot_features", sa.Column("cluster_spread_km", sa.Float(), server_default="0.0", nullable=True))
    op.add_column("hotspot_features", sa.Column("cluster_direction_deg", sa.Float(), server_default="0.0", nullable=True))
    op.add_column("hotspot_features", sa.Column("spatial_density_5km", sa.Float(), server_default="0.0", nullable=True))

    op.add_column("hotspot_features", sa.Column("nbr_value", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("ndmi_value", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("delta_nbr", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("cloud_cover_fraction", sa.Float(), nullable=True))
    op.add_column("hotspot_features", sa.Column("imagery_available", sa.Boolean(), server_default="true", nullable=True))

    # 3. Predictions: add stage1, stage2, and explanation columns
    op.add_column("predictions", sa.Column("stage1_class", sa.String(100), nullable=True))
    op.add_column("predictions", sa.Column("stage1_probabilities", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("stage2_class", sa.String(100), nullable=True))
    op.add_column("predictions", sa.Column("stage2_probabilities", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("explanation", sa.JSON(), nullable=True))

    # 4. Analyst Feedback: add hotspot_id, suggested_class, verified_class, reviewer_name, label_source, evidence
    op.add_column("analyst_feedback", sa.Column("hotspot_id", sa.Uuid(), sa.ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=True))
    op.add_column("analyst_feedback", sa.Column("suggested_class", sa.String(100), nullable=True))
    op.add_column("analyst_feedback", sa.Column("verified_class", sa.String(100), nullable=True))
    op.add_column("analyst_feedback", sa.Column("reviewer_name", sa.String(255), nullable=True))
    op.add_column("analyst_feedback", sa.Column("label_source", sa.String(50), server_default="analyst_verified", nullable=False))
    op.add_column("analyst_feedback", sa.Column("evidence", sa.JSON(), nullable=True))
    op.alter_column("analyst_feedback", "prediction_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("analyst_feedback", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.create_index("idx_analyst_feedback_hotspot_id", "analyst_feedback", ["hotspot_id"])
    op.create_index("idx_analyst_feedback_verified_class", "analyst_feedback", ["verified_class"])


def downgrade() -> None:
    op.drop_index("idx_analyst_feedback_verified_class", "analyst_feedback")
    op.drop_index("idx_analyst_feedback_hotspot_id", "analyst_feedback")
    op.drop_column("analyst_feedback", "evidence")
    op.drop_column("analyst_feedback", "label_source")
    op.drop_column("analyst_feedback", "reviewer_name")
    op.drop_column("analyst_feedback", "verified_class")
    op.drop_column("analyst_feedback", "suggested_class")
    op.drop_column("analyst_feedback", "hotspot_id")

    op.drop_column("predictions", "explanation")
    op.drop_column("predictions", "stage2_probabilities")
    op.drop_column("predictions", "stage2_class")
    op.drop_column("predictions", "stage1_probabilities")
    op.drop_column("predictions", "stage1_class")

    op.drop_column("hotspot_features", "imagery_available")
    op.drop_column("hotspot_features", "cloud_cover_fraction")
    op.drop_column("hotspot_features", "delta_nbr")
    op.drop_column("hotspot_features", "ndmi_value")
    op.drop_column("hotspot_features", "nbr_value")
    op.drop_column("hotspot_features", "spatial_density_5km")
    op.drop_column("hotspot_features", "cluster_direction_deg")
    op.drop_column("hotspot_features", "cluster_spread_km")
    op.drop_column("hotspot_features", "cluster_size")
    op.drop_column("hotspot_features", "frp_to_historical_ratio")
    op.drop_column("hotspot_features", "historical_max_frp")
    op.drop_column("hotspot_features", "historical_median_frp")
    op.drop_column("hotspot_features", "recurrence_rate")
    op.drop_column("hotspot_features", "persistence_score_30d")
    op.drop_column("hotspot_features", "nearby_hotspot_count_90d")
    op.drop_column("hotspot_features", "nearby_hotspot_count_30d")
    op.drop_column("hotspot_features", "dist_nearest_settlement")
    op.drop_column("hotspot_features", "dist_nearest_mine")
    op.drop_column("hotspot_features", "dist_nearest_cropland")
    op.drop_column("hotspot_features", "nearby_facility_count_5km")
    op.drop_column("hotspot_features", "nearby_facility_count_1km")
    op.drop_column("hotspot_features", "is_inside_facility")

    op.drop_index("idx_hotspots_event_id", "hotspots")
    op.drop_column("hotspots", "raw_data")
    op.drop_column("hotspots", "event_id")
