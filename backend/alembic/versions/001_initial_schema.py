"""Initial schema with 11 tables and PostGIS spatial columns

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-09-10 14:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from geoalchemy2 import Geometry
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # 2. Ingestion Runs
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # 3. Model Versions
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("algorithm", sa.String(50), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("artifact_path", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("trained_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # 4. Industrial Facilities
    op.create_table(
        "industrial_facilities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("facility_type", sa.String(100), nullable=True),
        sa.Column("osm_id", sa.String(50), nullable=True, unique=True),
        sa.Column("location", Geometry(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("footprint", Geometry(geometry_type="POLYGON", srid=4326), nullable=True),
        sa.Column("source", sa.String(50), nullable=True, server_default="OSM"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_facilities_location", "industrial_facilities", ["location"], postgresql_using="gist")
    op.create_index("idx_facilities_footprint", "industrial_facilities", ["footprint"], postgresql_using="gist")

    # 5. Land Cover
    op.create_table(
        "land_cover",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cover_class", sa.Integer(), nullable=False),
        sa.Column("cover_label", sa.String(100), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True, server_default="ESA"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_land_cover_geom", "land_cover", ["geom"], postgresql_using="gist")

    # 6. Hotspots
    op.create_table(
        "hotspots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("brightness", sa.Float(), nullable=True),
        sa.Column("bright_ti4", sa.Float(), nullable=True),
        sa.Column("bright_ti5", sa.Float(), nullable=True),
        sa.Column("frp", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("satellite", sa.String(50), nullable=True),
        sa.Column("instrument", sa.String(50), nullable=True),
        sa.Column("acq_date", sa.Date(), nullable=True),
        sa.Column("acq_time", sa.Time(), nullable=True),
        sa.Column("daynight", sa.String(1), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("ingestion_run_id", sa.Uuid(), sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_hotspots_geom", "hotspots", ["geom"], postgresql_using="gist")
    op.create_index("idx_hotspots_acq_date", "hotspots", ["acq_date"])
    op.create_index("idx_hotspots_ingestion_run_id", "hotspots", ["ingestion_run_id"])

    # 7. Hotspot Features
    op.create_table(
        "hotspot_features",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("hotspot_id", sa.Uuid(), sa.ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dist_nearest_facility", sa.Float(), nullable=True),
        sa.Column("dist_nearest_road", sa.Float(), nullable=True),
        sa.Column("dist_nearest_forest", sa.Float(), nullable=True),
        sa.Column("nearby_hotspot_count_24h", sa.Integer(), nullable=True),
        sa.Column("nearby_hotspot_count_7d", sa.Integer(), nullable=True),
        sa.Column("persistence_score", sa.Float(), nullable=True),
        sa.Column("land_cover_class", sa.Integer(), nullable=True),
        sa.Column("ndvi_value", sa.Float(), nullable=True),
        sa.Column("lst_delta", sa.Float(), nullable=True),
        sa.Column("is_nighttime", sa.Boolean(), nullable=True),
        sa.Column("day_of_year", sa.Integer(), nullable=True),
        sa.Column("extra_features", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_hotspot_features_hotspot_id", "hotspot_features", ["hotspot_id"])

    # 8. Predictions
    op.create_table(
        "predictions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("hotspot_id", sa.Uuid(), sa.ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), sa.ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("predicted_class", sa.String(100), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("class_probabilities", sa.JSON(), nullable=True),
        sa.Column("feature_importances", sa.JSON(), nullable=True),
        sa.Column("predicted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_predictions_hotspot_id", "predictions", ["hotspot_id"])
    op.create_index("idx_predictions_predicted_class", "predictions", ["predicted_class"])

    # 9. Alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("hotspot_id", sa.Uuid(), sa.ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prediction_id", sa.Uuid(), sa.ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_alerts_status_severity", "alerts", ["status", "severity"])

    # 10. Analyst Feedback
    op.create_table(
        "analyst_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prediction_id", sa.Uuid(), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("corrected_class", sa.String(100), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_analyst_feedback_prediction_id", "analyst_feedback", ["prediction_id"])

    # 11. Audit Logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("analyst_feedback")
    op.drop_table("alerts")
    op.drop_table("predictions")
    op.drop_table("hotspot_features")
    op.drop_table("hotspots")
    op.drop_table("land_cover")
    op.drop_table("industrial_facilities")
    op.drop_table("model_versions")
    op.drop_table("ingestion_runs")
    op.drop_table("users")
