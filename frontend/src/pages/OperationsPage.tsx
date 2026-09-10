import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { CommandMap } from "../components/map/CommandMap";
import { Card, MetricCard } from "../components/common/Card";
import { Button } from "../components/common/Button";
import { FireClassBadge } from "../components/common/Badge";
import { Drawer } from "../components/common/Drawer";
import { useToast } from "../components/common/Toast";
import { hotspotsApi, predictionsApi, alertsApi } from "../api/client";
import {
  FIRE_CLASS_COLORS,
  FIRE_CLASS_LABELS,
  type FireClass,
  type Hotspot,
} from "../types";

export function OperationsPage() {
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedHotspot, setSelectedHotspot] = useState<Hotspot | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [predicting, setPredicting] = useState(false);

  // Filters
  const [filterClass, setFilterClass] = useState<string>("all");
  const [minFrp, setMinFrp] = useState<number>(0);
  const [filterSatellite, setFilterSatellite] = useState<string>("all");
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showClusters, setShowClusters] = useState(false);

  const fetchHotspots = () => {
    setLoading(true);
    hotspotsApi
      .list({
        per_page: 250,
        min_frp: minFrp > 0 ? minFrp : undefined,
        satellite: filterSatellite !== "all" ? filterSatellite : undefined,
        fire_class: filterClass !== "all" ? filterClass : undefined,
      })
      .then((res) => {
        setHotspots(res.data || []);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Failed to load hotspots",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchHotspots();
  }, [filterClass, minFrp, filterSatellite]);

  const handleSelectHotspot = (h: Hotspot) => {
    setSelectedHotspot(h);
    setDrawerOpen(true);
  };

  const handleRunPredict = async () => {
    if (!selectedHotspot) return;
    setPredicting(true);
    try {
      const res = await predictionsApi.predict(selectedHotspot.id);
      addToast({
        type: "success",
        title: "AI Inference Complete",
        message: `Classified as ${FIRE_CLASS_LABELS[res.data.predicted_class]} (${Math.round((res.data.confidence_score ?? 0) * 100)}% confidence)`,
      });

      // Update hotspot in list
      setHotspots((prev) =>
        prev.map((item) =>
          item.id === selectedHotspot.id
            ? {
                ...item,
                predicted_class: res.data.predicted_class,
                confidence_score: res.data.confidence_score,
              }
            : item,
        ),
      );

      setSelectedHotspot((prev) =>
        prev
          ? {
              ...prev,
              predicted_class: res.data.predicted_class,
              confidence_score: res.data.confidence_score,
            }
          : null,
      );
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Inference Failed",
        message: err instanceof Error ? err.message : "Error executing prediction pipeline",
      });
    } finally {
      setPredicting(false);
    }
  };

  const handleDispatchAlert = async () => {
    if (!selectedHotspot) return;
    try {
      await alertsApi.create({
        hotspot_id: selectedHotspot.id,
        severity: "critical",
        alert_type: "emergency_dispatch",
        status: "active",
        description: `High-priority dispatch triggered from Operations Console for coordinate (${selectedHotspot.latitude}, ${selectedHotspot.longitude})`,
      });
      addToast({
        type: "warning",
        title: "Critical Alert Dispatched",
        message: "Incident broadcasted to emergency operational teams.",
      });
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Alert Dispatch Failed",
        message: err instanceof Error ? err.message : "Error dispatching alert",
      });
    }
  };

  // Metrics summary
  const metrics = useMemo(() => {
    const total = hotspots.length;
    const industrial = hotspots.filter(
      (h) =>
        h.predicted_class === "accidental_industrial_fire" ||
        h.predicted_class === "persistent_industrial_source",
    ).length;
    const critical = hotspots.filter(
      (h) => h.predicted_class === "accidental_industrial_fire" || (h.frp ?? 0) > 150,
    ).length;
    const maxFrp = hotspots.reduce((max, h) => Math.max(max, h.frp ?? 0), 0);

    return { total, industrial, critical, maxFrp };
  }, [hotspots]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* KPI Header Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: 14,
        }}
      >
        <MetricCard
          label="Active Thermal Detections"
          value={loading ? "..." : metrics.total}
          meta="VIIRS SNPP & NOAA satellites"
          icon="🛰️"
        />
        <MetricCard
          label="Critical Risk Events"
          value={loading ? "..." : metrics.critical}
          meta="Requires immediate evaluation"
          icon="🚨"
          trend={metrics.critical > 0 ? "up" : "neutral"}
        />
        <MetricCard
          label="Industrial Thermal Sites"
          value={loading ? "..." : metrics.industrial}
          meta="Refineries, flares & factories"
          icon="🏭"
        />
        <MetricCard
          label="Peak Radiative Power"
          value={loading ? "..." : `${Math.round(metrics.maxFrp)} MW`}
          meta="Highest thermal intensity"
          icon="🔥"
        />
      </div>

      {/* Operations Map Card with Top Controls */}
      <Card glass style={{ padding: 16 }}>
        {/* Intelligence Filter Bar */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            marginBottom: 14,
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <div>
              <select
                className="form-select"
                value={filterClass}
                onChange={(e) => setFilterClass(e.target.value)}
                style={{ width: 190 }}
              >
                <option value="all">All Classifications</option>
                {Object.entries(FIRE_CLASS_LABELS).map(([val, label]) => (
                  <option key={val} value={val}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <select
                className="form-select"
                value={filterSatellite}
                onChange={(e) => setFilterSatellite(e.target.value)}
                style={{ width: 150 }}
              >
                <option value="all">All Satellites</option>
                <option value="SNPP">VIIRS SNPP</option>
                <option value="NOAA20">NOAA-20</option>
                <option value="NOAA21">NOAA-21</option>
              </select>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="text-xs text-muted font-semibold">MIN FRP:</span>
              <input
                type="range"
                min="0"
                max="250"
                step="25"
                value={minFrp}
                onChange={(e) => setMinFrp(Number(e.target.value))}
                style={{ width: 100 }}
              />
              <span className="text-xs font-semibold">{minFrp} MW</span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Button
              variant={showHeatmap ? "primary" : "outline"}
              size="sm"
              onClick={() => setShowHeatmap((prev) => !prev)}
            >
              {showHeatmap ? "🔥 Heatmap Active" : "Heatmap"}
            </Button>
            <Button
              variant={showClusters ? "primary" : "outline"}
              size="sm"
              onClick={() => setShowClusters((prev) => !prev)}
            >
              {showClusters ? "Clustering Active" : "Cluster"}
            </Button>
            <Button variant="outline" size="sm" onClick={fetchHotspots}>
              🔄 Refresh
            </Button>
          </div>
        </div>

        {/* Map View */}
        <div style={{ height: "calc(100vh - 350px)", minHeight: 480 }}>
          <CommandMap
            hotspots={hotspots}
            selectedHotspot={selectedHotspot}
            onSelectHotspot={handleSelectHotspot}
            showHeatmap={showHeatmap}
            showClusters={showClusters}
          />
        </div>

        {/* Classification Legend Bar */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            marginTop: 14,
            paddingTop: 12,
            borderTop: "1px solid var(--border-subtle)",
            alignItems: "center",
          }}
        >
          <span className="text-xs font-semibold text-muted">CLASSIFICATION LEGEND:</span>
          {Object.entries(FIRE_CLASS_LABELS).map(([cls, label]) => (
            <div
              key={cls}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: "0.75rem",
                color: "var(--text-secondary)",
              }}
            >
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: FIRE_CLASS_COLORS[cls as FireClass],
                }}
              />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Selected Incident Drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={
          selectedHotspot ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>Thermal Incident Inspection</span>
              {selectedHotspot.predicted_class && (
                <FireClassBadge fireClass={selectedHotspot.predicted_class} size="sm" />
              )}
            </div>
          ) : (
            "Incident Details"
          )
        }
        subtitle={
          selectedHotspot
            ? `LAT ${selectedHotspot.latitude.toFixed(4)}°N • LON ${selectedHotspot.longitude.toFixed(4)}°E`
            : undefined
        }
        footer={
          selectedHotspot && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/investigate/${selectedHotspot.id}`)}
              >
                Full Dossier ➔
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleDispatchAlert}
              >
                Dispatch Alert
              </Button>
              <Button
                variant="primary"
                size="sm"
                loading={predicting}
                onClick={handleRunPredict}
              >
                Run AI Inference
              </Button>
            </>
          )
        }
      >
        {selectedHotspot ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Quick Status Box */}
            <div
              style={{
                background: "var(--surface-subtle)",
                border: "1px solid var(--border-card)",
                borderRadius: 12,
                padding: 14,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span className="text-xs text-muted font-semibold">AI CLASSIFICATION</span>
                <span className="text-xs font-semibold">
                  {selectedHotspot.confidence_score
                    ? `${Math.round(selectedHotspot.confidence_score * 100)}% Confidence`
                    : "Not Classified Yet"}
                </span>
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700 }}>
                {selectedHotspot.predicted_class
                  ? FIRE_CLASS_LABELS[selectedHotspot.predicted_class]
                  : "Awaiting Machine Learning Analysis"}
              </div>
            </div>

            {/* Thermal Measurements Table */}
            <div>
              <h4 style={{ marginBottom: 8 }}>Thermal Measurements</h4>
              <div className="table-container">
                <table className="table">
                  <tbody>
                    <tr>
                      <td className="text-muted text-xs">Fire Radiative Power (FRP)</td>
                      <td className="font-bold">{selectedHotspot.frp ? `${selectedHotspot.frp} MW` : "N/A"}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Brightness (TI4)</td>
                      <td>{selectedHotspot.bright_ti4 ?? selectedHotspot.brightness ?? "N/A"} K</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Brightness (TI5)</td>
                      <td>{selectedHotspot.bright_ti5 ?? "N/A"} K</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Detection Confidence</td>
                      <td>{selectedHotspot.confidence ? `${selectedHotspot.confidence}%` : "N/A"}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Satellite Sensor</td>
                      <td>{selectedHotspot.satellite ?? "VIIRS"}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Acquisition Time</td>
                      <td>
                        {selectedHotspot.acq_date ?? "N/A"} {selectedHotspot.acq_time ?? ""} (
                        {selectedHotspot.daynight === "N" ? "Night" : "Day"})
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Proximity & Context */}
            <div>
              <h4 style={{ marginBottom: 8 }}>Spatial Proximity Assessment</h4>
              <div
                style={{
                  background: "white",
                  border: "1px solid var(--border-card)",
                  borderRadius: 12,
                  padding: 14,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  fontSize: "0.85rem",
                }}
              >
                <div>
                  <span className="text-muted">Proximity: </span>
                  <span className="font-semibold">Integrated with OSM Industrial Infrastructure</span>
                </div>
                <div>
                  <span className="text-muted">Sentinel-2 SR: </span>
                  <span className="font-semibold">Cloud-masked surface reflectance calibrated</span>
                </div>
                <div>
                  <span className="text-muted">Event ID: </span>
                  <code style={{ fontSize: "0.75rem", background: "#F1F5F9", padding: "2px 6px", borderRadius: 4 }}>
                    {selectedHotspot.event_id || selectedHotspot.id.slice(0, 16)}
                  </code>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
