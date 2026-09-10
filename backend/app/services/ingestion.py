"""AgniNetra AI — Ingestion Orchestration Service.

Manages end-to-end ingestion runs from external data providers into the database,
with transaction management, duplicate filtering, and audit logging.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.hotspot import Hotspot
from app.models.ingestion import AuditLog, IngestionRun
from app.services.firms import FIRMSClient, SUPPORTED_FIRMS_SOURCES

logger = logging.getLogger(__name__)


class IngestionService:
    """Service to coordinate data ingestion runs and database persistence."""

    def __init__(self, db: Session):
        self.db = db
        self.firms_client = FIRMSClient()

    def run_firms_ingestion(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: datetime.date,
        end_date: Optional[datetime.date] = None,
        sources: Optional[List[str]] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> IngestionRun:
        """Execute a FIRMS ingestion workflow across specified satellite sources and date ranges."""
        end_date = end_date or start_date
        sources = sources or ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]

        ingestion_run = IngestionRun(
            id=uuid.uuid4(),
            source=",".join(sources),
            status="running",
            records_fetched=0,
            records_inserted=0,
            records_skipped=0,
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.db.add(ingestion_run)
        self.db.commit()
        self.db.refresh(ingestion_run)

        total_fetched = 0
        total_inserted = 0
        total_skipped = 0

        try:
            date_batches = self.firms_client.split_date_range(start_date, end_date, max_batch_days=5)

            for source in sources:
                if source not in SUPPORTED_FIRMS_SOURCES:
                    logger.warning("Skipping unsupported FIRMS source: %s", source)
                    continue

                for batch_start, batch_days in date_batches:
                    logger.info(
                        "Ingesting %s for bbox=%s from %s (%d days)",
                        source, bbox, batch_start, batch_days
                    )
                    csv_data = self.firms_client.fetch_area_csv(
                        source=source,
                        bbox=bbox,
                        start_date=batch_start,
                        day_range=batch_days,
                    )

                    if not csv_data:
                        continue

                    records = self.firms_client.parse_firms_csv(csv_data, source_label=f"FIRMS_{source}")
                    total_fetched += len(records)

                    inserted, skipped = self._insert_hotspot_records(records, ingestion_run.id)
                    total_inserted += inserted
                    total_skipped += skipped

            ingestion_run.status = "completed"
            ingestion_run.records_fetched = total_fetched
            ingestion_run.records_inserted = total_inserted
            ingestion_run.records_skipped = total_skipped
            ingestion_run.completed_at = datetime.datetime.now(datetime.timezone.utc)

            # Record audit log
            audit = AuditLog(
                id=uuid.uuid4(),
                user_id=user_id,
                action="firms_ingestion_run",
                resource_type="ingestion_runs",
                resource_id=ingestion_run.id,
                details={
                    "sources": sources,
                    "bbox": bbox,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "records_inserted": total_inserted,
                },
            )
            self.db.add(audit)
            self.db.commit()
            logger.info("Ingestion run %s completed: %d inserted, %d skipped", ingestion_run.id, total_inserted, total_skipped)

        except Exception as exc:
            self.db.rollback()
            ingestion_run.status = "failed"
            ingestion_run.error_message = str(exc)
            ingestion_run.completed_at = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()
            logger.error("Ingestion run %s failed: %s", ingestion_run.id, exc, exc_info=True)

        self.db.refresh(ingestion_run)
        return ingestion_run

    def _insert_hotspot_records(
        self, records: List[Dict[str, Any]], ingestion_run_id: uuid.UUID
    ) -> Tuple[int, int]:
        """Insert records with deduplication against event_id or coordinate-time tuples."""
        if not records:
            return 0, 0

        # Collect event_ids to check existing in one batch
        event_ids = [r["event_id"] for r in records if r.get("event_id")]
        existing_ids = set()
        if event_ids:
            existing_query = self.db.query(Hotspot.event_id).filter(Hotspot.event_id.in_(event_ids)).all()
            existing_ids = {row[0] for row in existing_query if row[0]}

        inserted = 0
        skipped = 0

        for r in records:
            event_id = r.get("event_id")
            if event_id and event_id in existing_ids:
                skipped += 1
                continue

            lat = r["latitude"]
            lon = r["longitude"]
            geom_wkt = f"POINT({lon} {lat})"

            hotspot = Hotspot(
                id=uuid.uuid4(),
                event_id=event_id,
                latitude=lat,
                longitude=lon,
                geom=geom_wkt,
                brightness=r.get("brightness"),
                bright_ti4=r.get("bright_ti4"),
                bright_ti5=r.get("bright_ti5"),
                frp=r.get("frp"),
                confidence=r.get("confidence"),
                satellite=r.get("satellite"),
                instrument=r.get("instrument"),
                acq_date=r.get("acq_date"),
                acq_time=r.get("acq_time"),
                daynight=r.get("daynight"),
                source=r.get("source"),
                raw_data=r.get("raw_data"),
                ingestion_run_id=ingestion_run_id,
            )
            self.db.add(hotspot)
            existing_ids.add(event_id)
            inserted += 1

        self.db.commit()
        return inserted, skipped
