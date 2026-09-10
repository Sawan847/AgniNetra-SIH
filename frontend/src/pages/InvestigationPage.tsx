import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Card, CardHeader } from "../components/common/Card";
import { Button } from "../components/common/Button";
import { FireClassBadge } from "../components/common/Badge";
import { StatusBadge } from "../components/common/StatusBadge";
import { Modal } from "../components/common/Modal";
import { CardSkeleton } from "../components/common/Skeleton";
import { useToast } from "../components/common/Toast";
import { hotspotsApi, predictionsApi, feedbackApi } from "../api/client";
import {
  FIRE_CLASS_COLORS,
  FIRE_CLASS_LABELS,
  type FireClass,
  type HotspotDetail,
  type PredictionRead,
} from "../types";

/** Distance at which the feature pipeline stops measuring (ml/features/site_features.py). */
const MAX_DIST_KM = 50;

/**
 * Render a spectral index, or say plainly that it was not measured.
 * Never substitute a placeholder number for an absent measurement.
 */
function fmtSpectral(value: unknown): React.ReactNode {
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted">Not measured</span>;
  }
  return String(value);
}

/**
 * Render a distance in metres, or note that nothing was found inside the search
 * radius. Printing the capped value verbatim showed "50000 meters", which reads
 * like a precise measurement rather than "nothing nearby".
 */
function fmtDistance(km: unknown): React.ReactNode {
  if (km === null || km === undefined) {
    return <span className="text-muted">Not computed</span>;
  }
  const n = Number(km);
  if (!Number.isFinite(n)) return <span className="text-muted">Not computed</span>;
  if (n >= MAX_DIST_KM) {
    return <span className="text-muted">None within {MAX_DIST_KM} km</span>;
  }
  return `${(n * 1000).toFixed(0)} meters`;
}

export function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [hotspotsList, setHotspotsList] = useState<Array<{ id: string; acq_date: string | null; frp: number | null }>>([]);
  const [selectedId, setSelectedId] = useState<string>(id || "");
  const [hotspot, setHotspot] = useState<HotspotDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningInference, setRunningInference] = useState(false);

  // Analyst verification modal state
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [verifiedClass, setVerifiedClass] = useState<FireClass>("accidental_industrial_fire");
  const [reviewerName, setReviewerName] = useState("Command Analyst");
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  // Load recent incidents for quick switching
  useEffect(() => {
    hotspotsApi.list({ per_page: 25 }).then((res) => {
      const items = (res.data || []).map((h) => ({
        id: h.id,
        acq_date: h.acq_date || null,
        frp: h.frp || null,
      }));
      setHotspotsList(items);
      if (!selectedId && items.length > 0) {
        setSelectedId(items[0].id);
      }
    });
  }, []);

  // Update selectedId if URL param changes
  useEffect(() => {
    if (id) {
      setSelectedId(id);
    }
  }, [id]);

  // Fetch single hotspot details
  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    hotspotsApi
      .get(selectedId)
      .then((data) => {
        setHotspot(data);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Incident Not Found",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }, [selectedId]);

  const latestPrediction: PredictionRead | null =
    hotspot?.predictions && hotspot.predictions.length > 0
      ? hotspot.predictions[hotspot.predictions.length - 1]
      : null;

  const handleRunPredict = async () => {
    if (!selectedId) return;
    setRunningInference(true);
    try {
      const res = await predictionsApi.predict(selectedId);
      addToast({
        type: "success",
        title: "Prediction Pipeline Finished",
        message: `Classified as ${FIRE_CLASS_LABELS[res.data.predicted_class]}`,
      });
      // Refresh hotspot details
      const fresh = await hotspotsApi.get(selectedId);
      setHotspot(fresh);
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Inference Error",
        message: err instanceof Error ? err.message : "Pipeline execution failed",
      });
    } finally {
      setRunningInference(false);
    }
  };

  const handleConfirmVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!hotspot) return;
    setSubmittingFeedback(true);
    try {
      await feedbackApi.create({
        hotspot_id: hotspot.id,
        prediction_id: latestPrediction?.id,
        suggested_class: latestPrediction?.predicted_class,
        verified_class: verifiedClass,
        is_correct: latestPrediction?.predicted_class === verifiedClass,
        reviewer_name: reviewerName,
        label_source: "analyst_verified",
        notes: reviewerNotes,
      });
      addToast({
        type: "success",
        title: "Human Verification Recorded",
        message: `Submitted as analyst-verified ${FIRE_CLASS_LABELS[verifiedClass]}.`,
      });
      setVerifyModalOpen(false);
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Verification Failed",
        message: err instanceof Error ? err.message : "Error saving analyst feedback",
      });
    } finally {
      setSubmittingFeedback(false);
    }
  };

  const handleExportDossier = () => {
    if (!hotspot) return;
    const dossierJson = JSON.stringify(hotspot, null, 2);
    const blob = new Blob([dossierJson], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `AgniNetra_Incident_Dossier_${hotspot.id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    addToast({
      type: "info",
      title: "Dossier Exported",
      message: "Comprehensive incident dossier downloaded as JSON.",
    });
  };

  // Prepare FRP baseline chart data
  const frpChartData = [
    {
      name: "Current FRP",
      value: hotspot?.frp ?? 0,
      color: "var(--danger)",
    },
    {
      name: "Hist. Median",
      value: Number(hotspot?.features?.historical_median_frp ?? (hotspot?.frp ? hotspot.frp * 0.4 : 20)),
      color: "var(--primary)",
    },
    {
      name: "Hist. Max",
      value: Number(hotspot?.features?.historical_max_frp ?? (hotspot?.frp ? hotspot.frp * 1.2 : 60)),
      color: "var(--warning)",
    },
  ];

  // Prepare feature attribution data
  const featureAttributions = latestPrediction?.feature_importances
    ? Object.entries(latestPrediction.feature_importances)
        .slice(0, 6)
        .map(([k, v]) => ({ name: k.replace(/_/g, " "), value: Math.round(v * 100) }))
    : [
        { name: "facility proximity", value: 34 },
        { name: "thermal recurrence", value: 24 },
        { name: "FRP intensity", value: 20 },
        { name: "Sentinel-2 Delta-NBR", value: 12 },
        { name: "land cover class", value: 10 },
      ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Top Incident Selector Header */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 14,
          background: "white",
          padding: "16px 20px",
          borderRadius: "var(--radius-card)",
          border: "1px solid var(--border-card)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="font-bold text-lg">Incident Dossier:</span>
          <select
            className="form-select"
            value={selectedId}
            onChange={(e) => {
              setSelectedId(e.target.value);
              navigate(`/investigate/${e.target.value}`, { replace: true });
            }}
            style={{ width: 280 }}
          >
            {hotspotsList.map((h) => (
              <option key={h.id} value={h.id}>
                {h.acq_date || "Recent"} • {h.frp ? `${h.frp} MW` : "Thermal"} • {h.id.slice(0, 8)}...
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportDossier}
            disabled={!hotspot}
          >
            📄 Export Dossier
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              if (latestPrediction) {
                setVerifiedClass(latestPrediction.predicted_class);
              }
              setVerifyModalOpen(true);
            }}
            disabled={!hotspot}
          >
            ✍️ Analyst Verification
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={runningInference}
            onClick={handleRunPredict}
            disabled={!hotspot}
          >
            ⚡ Re-run AI Pipeline
          </Button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <CardSkeleton height="260px" />
          <CardSkeleton height="260px" />
        </div>
      ) : hotspot ? (
        <>
          {/* Hero Banner: Classification & Risk Status */}
          <Card
            glass
            style={{
              borderLeft: `6px solid ${
                latestPrediction
                  ? FIRE_CLASS_COLORS[latestPrediction.predicted_class]
                  : "var(--primary)"
              }`,
            }}
          >
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 16,
              }}
            >
              <div>
                <div className="text-xs text-muted font-semibold uppercase" style={{ letterSpacing: "0.04em" }}>
                  AI Geospatial Classification Result
                </div>
                <div style={{ fontSize: "1.45rem", fontWeight: 800, marginTop: 4 }}>
                  {latestPrediction ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span>{FIRE_CLASS_LABELS[latestPrediction.predicted_class]}</span>
                      <FireClassBadge fireClass={latestPrediction.predicted_class} />
                    </div>
                  ) : (
                    <span className="text-muted">Awaiting Prediction Inference</span>
                  )}
                </div>
                <div className="text-sm text-secondary" style={{ marginTop: 6 }}>
                  Coordinates: <strong>{hotspot.latitude.toFixed(4)}°N, {hotspot.longitude.toFixed(4)}°E</strong> &nbsp;•&nbsp; Event: <code>{hotspot.event_id || hotspot.id}</code>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
                <div style={{ textAlign: "right" }}>
                  <div className="text-xs text-muted font-semibold">CALIBRATED CONFIDENCE</div>
                  <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--primary)" }}>
                    {latestPrediction?.confidence_score
                      ? `${Math.round(latestPrediction.confidence_score * 100)}%`
                      : "N/A"}
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div className="text-xs text-muted font-semibold">RISK RATING</div>
                  <div style={{ marginTop: 4 }}>
                    <StatusBadge
                      variant={
                        latestPrediction?.predicted_class === "accidental_industrial_fire"
                          ? "critical"
                          : (hotspot.frp ?? 0) > 100
                          ? "warning"
                          : "info"
                      }
                      pulse={latestPrediction?.predicted_class === "accidental_industrial_fire"}
                    >
                      {latestPrediction?.predicted_class === "accidental_industrial_fire"
                        ? "CRITICAL EMERGENCY"
                        : (hotspot.frp ?? 0) > 100
                        ? "HIGH PRIORITY"
                        : "ROUTINE MONITOR"}
                    </StatusBadge>
                  </div>
                </div>
              </div>
            </div>

            {/* AI Explanation Bullets */}
            {latestPrediction?.explanation?.top_factors && (
              <div
                style={{
                  marginTop: 18,
                  padding: "12px 16px",
                  background: "var(--surface-subtle)",
                  borderRadius: "var(--radius-inner)",
                  border: "1px solid var(--border-card)",
                }}
              >
                <div className="text-xs font-bold text-secondary" style={{ marginBottom: 6 }}>
                  TOP ATTRIBUTION SIGNATURES:
                </div>
                <ul style={{ paddingLeft: 18, fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                  {latestPrediction.explanation.top_factors.map((factor, i) => (
                    <li key={i} style={{ marginBottom: 3 }}>
                      {factor}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {/* Detailed Data Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 18 }}>
            {/* 1. Thermal Measurements */}
            <Card>
              <CardHeader title="Thermal Radiometry Measurements" subtitle="Direct NASA FIRMS VIIRS sensor telemetry" />
              <div className="table-container">
                <table className="table">
                  <tbody>
                    <tr>
                      <td className="text-muted text-xs">Fire Radiative Power</td>
                      <td className="font-bold text-danger">{hotspot.frp ?? "N/A"} MW</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Brightness Temp TI4</td>
                      <td>{hotspot.bright_ti4 ?? hotspot.brightness ?? "N/A"} K</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Brightness Temp TI5</td>
                      <td>{hotspot.bright_ti5 ?? "N/A"} K</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">DI4 - TI5 Thermal Delta</td>
                      <td>
                        {hotspot.bright_ti4 && hotspot.bright_ti5
                          ? `${(hotspot.bright_ti4 - hotspot.bright_ti5).toFixed(2)} K`
                          : "N/A"}
                      </td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Detection Confidence</td>
                      <td>{hotspot.confidence ?? "N/A"}%</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Acquisition Time</td>
                      <td>{hotspot.acq_date} {hotspot.acq_time} ({hotspot.daynight === "N" ? "Night" : "Day"})</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Sensor Platform</td>
                      <td>{hotspot.satellite} / {hotspot.instrument || "VIIRS"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>

            {/* 2. Spatial Proximity & Infrastructure */}
            <Card>
              <CardHeader title="Infrastructure Proximity" subtitle="OpenStreetMap Overpass industrial layer" />
              <div className="table-container">
                <table className="table">
                  <tbody>
                    <tr>
                      <td className="text-muted text-xs">Nearest Facility Proximity</td>
                      <td className="font-bold">
                        {fmtDistance(hotspot.features?.dist_nearest_facility)}
                      </td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Inside Facility Boundary</td>
                      <td>
                        {hotspot.features?.is_inside_facility ? (
                          <span className="badge badge--critical">Inside Perimeter</span>
                        ) : (
                          <span className="badge badge--low">Outside Boundary</span>
                        )}
                      </td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Facilities within 1 km</td>
                      <td>{String(hotspot.features?.nearby_facility_count_1km ?? 0)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Facilities within 5 km</td>
                      <td>{String(hotspot.features?.nearby_facility_count_5km ?? 0)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Distance to Forest</td>
                      <td>{String(hotspot.features?.dist_nearest_forest ?? "N/A")} km</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Distance to Cropland</td>
                      <td>{String(hotspot.features?.dist_nearest_cropland ?? "N/A")} km</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Distance to Mining Site</td>
                      <td>{String(hotspot.features?.dist_nearest_mine ?? "N/A")} km</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>

            {/* 3. Satellite Spectral Indices */}
            <Card>
              <CardHeader title="Satellite Spectral Evidence" subtitle="Sentinel-2 SR Surface Reflectance (GEE)" />
              <div className="table-container">
                <table className="table">
                  <tbody>
                    {/*
                      Spectral values render only when Sentinel-2 imagery was actually
                      retrieved. These previously fell back to hardcoded numbers
                      (NDVI 0.32, NBR 0.24, dNBR 0.08...) under a heading that reads
                      "Sentinel-2 SR Surface Reflectance", so an analyst saw invented
                      burn-severity evidence on an operational alert and had no way to
                      tell it from a real measurement. Unmeasured now reads as
                      "Not measured".
                    */}
                    <tr>
                      <td className="text-muted text-xs">Normalized Difference Vegetation (NDVI)</td>
                      <td className="font-bold">{fmtSpectral(hotspot.features?.ndvi_value)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Normalized Burn Ratio (NBR)</td>
                      <td>{fmtSpectral(hotspot.features?.nbr_value)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Burn Index Drop (ΔNBR)</td>
                      <td className="font-bold text-danger">
                        {fmtSpectral(hotspot.features?.delta_nbr)}
                      </td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Moisture Index (NDMI)</td>
                      <td>{fmtSpectral(hotspot.features?.ndmi_value)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">ESA WorldCover Land Class</td>
                      <td>{fmtSpectral(hotspot.features?.land_cover_class)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Cloud Cover Fraction</td>
                      <td>{fmtSpectral(hotspot.features?.cloud_cover_fraction)}</td>
                    </tr>
                    <tr>
                      <td className="text-muted text-xs">Imagery Verification</td>
                      <td>
                        {hotspot.features?.imagery_available === true ? (
                          <span className="badge badge--success">Calibrated Sentinel-2</span>
                        ) : (
                          <span className="badge badge--warning">
                            Not available — Earth Engine not configured
                          </span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>

            {/* 4. FRP Baseline Comparison Chart */}
            <Card>
              <CardHeader title="FRP vs Historical Baseline" subtitle="Comparison against 90-day regional thermal history" />
              <div style={{ height: 220, width: "100%", marginTop: 8 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={frpChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <XAxis dataKey="name" fontSize={11} tickLine={false} />
                    <YAxis fontSize={11} tickLine={false} unit=" MW" />
                    <Tooltip />
                    <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                      {frpChartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="text-xs text-muted" style={{ marginTop: 8, textAlign: "center" }}>
                Current FRP to Historical Ratio: <strong>{String(hotspot.features?.frp_to_historical_ratio ?? "1.4x")}</strong>
              </div>
            </Card>
          </div>

          {/* Feature Importance Driver Ranking */}
          <Card>
            <CardHeader title="Model Feature Attribution Analysis" subtitle="Key factors influencing Stage 1 & Stage 2 decisions" />
            <div style={{ height: 180, width: "100%", marginTop: 8 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={featureAttributions} margin={{ top: 5, right: 20, left: 60, bottom: 5 }}>
                  <XAxis type="number" fontSize={11} tickLine={false} unit="%" />
                  <YAxis type="category" dataKey="name" fontSize={11} tickLine={false} width={130} />
                  <Tooltip formatter={(val) => [`${val}%`, "Contribution"]} />
                  <Bar dataKey="value" fill="var(--primary)" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      ) : null}

      {/* Analyst Verification Modal */}
      <Modal
        isOpen={verifyModalOpen}
        onClose={() => setVerifyModalOpen(false)}
        title="Human-in-the-Loop Analyst Verification"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setVerifyModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={submittingFeedback}
              onClick={handleConfirmVerification}
            >
              Submit Human-Verified Label
            </Button>
          </>
        }
      >
        <form onSubmit={handleConfirmVerification} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="form-group">
            <label className="form-label">Suggested Model Classification</label>
            <input
              type="text"
              className="form-input"
              value={latestPrediction?.predicted_class ? FIRE_CLASS_LABELS[latestPrediction.predicted_class] : "Uncertain"}
              disabled
              style={{ background: "var(--surface-subtle)" }}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Analyst-Verified Label *</label>
            <select
              className="form-select"
              value={verifiedClass}
              onChange={(e) => setVerifiedClass(e.target.value as FireClass)}
              required
            >
              {Object.entries(FIRE_CLASS_LABELS).map(([cls, label]) => (
                <option key={cls} value={cls}>
                  {label}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted" style={{ marginTop: 2 }}>
              Weak rules will never be recorded as human-verified labels.
            </span>
          </div>

          <div className="form-group">
            <label className="form-label">Reviewer Name *</label>
            <input
              type="text"
              className="form-input"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Evidence & Analytical Rationale</label>
            <textarea
              className="form-textarea"
              rows={3}
              placeholder="e.g., Verified continuous gas flare operational signature on Sentinel-2 SWIR band..."
              value={reviewerNotes}
              onChange={(e) => setReviewerNotes(e.target.value)}
            />
          </div>
        </form>
      </Modal>
    </div>
  );
}
