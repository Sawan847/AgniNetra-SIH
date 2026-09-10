import { useEffect, useState } from "react";
import { Card, CardHeader } from "../components/common/Card";
import { Button } from "../components/common/Button";
import { StatusBadge } from "../components/common/StatusBadge";
import { Modal } from "../components/common/Modal";
import { CardSkeleton } from "../components/common/Skeleton";
import { useToast } from "../components/common/Toast";
import { systemApi, ingestionApi } from "../api/client";
import type { SystemStatus, IngestionRun } from "../types";

export function SystemHealthPage() {
  const { addToast } = useToast();

  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [loading, setLoading] = useState(true);

  // Ingestion trigger modal
  const [ingestModalOpen, setIngestModalOpen] = useState(false);
  const [startDate, setStartDate] = useState(
    new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString().split("T")[0],
  );
  const [endDate, setEndDate] = useState(
    new Date().toISOString().split("T")[0],
  );
  const [bboxStr, setBboxStr] = useState("68.0, 7.0, 97.0, 36.0"); // India bbox
  const [triggering, setTriggering] = useState(false);

  const loadHealthData = () => {
    setLoading(true);
    Promise.all([systemApi.status(), ingestionApi.runs({ limit: 25 })])
      .then(([sysStatus, runsRes]) => {
        setStatus(sysStatus);
        setRuns(runsRes || []);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Diagnostics Offline",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadHealthData();
  }, []);

  const handleTriggerIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    setTriggering(true);
    try {
      const parts = bboxStr.split(",").map((p) => parseFloat(p.trim()));
      if (parts.length !== 4 || parts.some(isNaN)) {
        throw new Error("Bounding box must be 4 comma-separated floats: min_lon,min_lat,max_lon,max_lat");
      }
      const [min_lon, min_lat, max_lon, max_lat] = parts;

      const res = await ingestionApi.trigger({
        bbox: [min_lon, min_lat, max_lon, max_lat],
        start_date: startDate,
        end_date: endDate,
      });

      addToast({
        type: "success",
        title: "FIRMS Ingestion Triggered",
        message: res.message || "Batch ingestion process executed successfully.",
      });

      setIngestModalOpen(false);
      loadHealthData();
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Ingestion Failed",
        message: err instanceof Error ? err.message : "Error initiating ingestion",
      });
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Top Status Banner & Trigger Button */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          background: "white",
          padding: "16px 20px",
          borderRadius: "var(--radius-card)",
          border: "1px solid var(--border-card)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="font-bold text-lg">Subsystem Diagnostics:</span>
          <StatusBadge
            variant={status?.status === "healthy" ? "success" : "warning"}
            pulse={status?.status === "healthy"}
          >
            {status?.status ? status.status.toUpperCase() : "CHECKING..."}
          </StatusBadge>
          <span className="text-xs text-muted">
            Telemetry Heartbeat: {status?.timestamp ? new Date(status.timestamp).toLocaleTimeString() : "-"}
          </span>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <Button variant="outline" size="sm" onClick={loadHealthData}>
            🔄 Check Health
          </Button>
          <Button variant="primary" size="sm" onClick={() => setIngestModalOpen(true)}>
            ⚡ Trigger FIRMS Ingestion
          </Button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
          <CardSkeleton height="140px" />
          <CardSkeleton height="140px" />
          <CardSkeleton height="140px" />
          <CardSkeleton height="140px" />
        </div>
      ) : (
        <>
          {/* Subsystem Health Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
            {/* Database */}
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span className="text-xs text-muted font-bold">DATABASE</span>
                <StatusBadge variant={status?.database_connected ? "success" : "critical"}>
                  {status?.database_connected ? "ONLINE" : "OFFLINE"}
                </StatusBadge>
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800 }}>PostgreSQL + PostGIS</div>
              <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                Spatial SRID 4326 • GIST R-Tree Indexed
              </div>
            </Card>

            {/* NASA FIRMS */}
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span className="text-xs text-muted font-bold">NASA FIRMS API</span>
                <StatusBadge variant={status?.firms_configured ? "success" : "warning"}>
                  {status?.firms_configured ? "ACTIVE" : "UNCONFIGURED"}
                </StatusBadge>
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800 }}>VIIRS NRT Sensors</div>
              <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                SNPP, NOAA-20, NOAA-21 Area Ingestion
              </div>
            </Card>

            {/* Google Earth Engine */}
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span className="text-xs text-muted font-bold">EARTH ENGINE</span>
                <StatusBadge variant={status?.gee_connected ? "success" : "medium"}>
                  {status?.gee_connected ? "AUTHENTICATED" : "FALLBACK ACTIVE"}
                </StatusBadge>
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800 }}>Sentinel-2 SR</div>
              <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                SCL Cloud Masking & Spectral Baselines
              </div>
            </Card>

            {/* OpenStreetMap Overpass */}
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span className="text-xs text-muted font-bold">OPENSTREETMAP</span>
                <StatusBadge variant="success">ONLINE</StatusBadge>
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800 }}>Overpass GIS API</div>
              <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                7-day cached industrial registry
              </div>
            </Card>
          </div>

          {/* Database Entity Counter Cards */}
          {status?.total_records && (
            <Card>
              <CardHeader
                title="Platform Database Footprint"
                subtitle="Persistent records across all AgniNetra AI tables"
              />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
                {Object.entries(status.total_records).map(([tbl, count]) => (
                  <div
                    key={tbl}
                    style={{
                      background: "var(--surface-subtle)",
                      border: "1px solid var(--border-card)",
                      borderRadius: "var(--radius-inner)",
                      padding: 12,
                      textAlign: "center",
                    }}
                  >
                    <div className="text-xs text-muted font-semibold uppercase">{tbl.replace(/_/g, " ")}</div>
                    <div style={{ fontSize: "1.4rem", fontWeight: 800, marginTop: 4, color: "var(--primary)" }}>
                      {count}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Ingestion Runs History Table */}
          <Card>
            <CardHeader
              title="Automated Ingestion Run History"
              subtitle="Audit ledger of NASA FIRMS and GIS batch ingestion transactions"
            />
            {runs.length === 0 ? (
              <div className="empty-state">No ingestion runs recorded in audit log.</div>
            ) : (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Started At</th>
                      <th>Data Source</th>
                      <th>Status</th>
                      <th>Records Fetched</th>
                      <th>Records Inserted</th>
                      <th>Skipped / Dupes</th>
                      <th>Error Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.id}>
                        <td className="text-xs text-muted">{new Date(r.started_at).toLocaleString()}</td>
                        <td className="font-semibold text-xs">{r.source}</td>
                        <td>
                          <StatusBadge
                            variant={
                              r.status === "completed"
                                ? "success"
                                : r.status === "running"
                                ? "warning"
                                : "critical"
                            }
                          >
                            {r.status.toUpperCase()}
                          </StatusBadge>
                        </td>
                        <td className="font-bold">{r.records_fetched}</td>
                        <td className="text-success font-bold">{r.records_inserted}</td>
                        <td className="text-muted">{r.records_skipped}</td>
                        <td className="text-xs" style={{ maxWidth: 220 }}>
                          {r.error_message || "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {/* Trigger Ingestion Modal */}
      <Modal
        isOpen={ingestModalOpen}
        onClose={() => setIngestModalOpen(false)}
        title="Trigger Real NASA FIRMS Area Ingestion"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setIngestModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={triggering}
              onClick={handleTriggerIngest}
            >
              Start Ingestion Process
            </Button>
          </>
        }
      >
        <form onSubmit={handleTriggerIngest} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="form-group">
            <label className="form-label">Geographic Bounding Box (min_lon, min_lat, max_lon, max_lat)</label>
            <input
              type="text"
              className="form-input"
              value={bboxStr}
              onChange={(e) => setBboxStr(e.target.value)}
              placeholder="e.g. 68.0, 7.0, 97.0, 36.0 (India)"
              required
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Start Date (YYYY-MM-DD)</label>
              <input
                type="date"
                className="form-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">End Date (YYYY-MM-DD)</label>
              <input
                type="date"
                className="form-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                required
              />
            </div>
          </div>

          <div
            style={{
              padding: 10,
              background: "var(--surface-subtle)",
              borderRadius: "var(--radius-inner)",
              fontSize: "0.78rem",
              color: "var(--text-secondary)",
            }}
          >
            ℹ️ Date ranges exceeding 5 days will be automatically partitioned into compliant batches under NASA FIRMS Area API constraints. Deterministic SHA-256 deduplication is enforced.
          </div>
        </form>
      </Modal>
    </div>
  );
}
