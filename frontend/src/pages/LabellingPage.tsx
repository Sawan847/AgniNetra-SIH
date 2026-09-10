import React, { useEffect, useState, useMemo } from "react";
import { Card, MetricCard, CardHeader } from "../components/common/Card";
import { Button } from "../components/common/Button";
import { FireClassBadge } from "../components/common/Badge";
import { TableSkeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { useToast } from "../components/common/Toast";
import { feedbackApi, hotspotsApi } from "../api/client";
import {
  FIRE_CLASS_LABELS,
  type FeedbackRead,
  type FireClass,
  type Hotspot,
} from "../types";

export function LabellingPage() {
  const { addToast } = useToast();

  const [queue, setQueue] = useState<Hotspot[]>([]);
  const [feedbackHistory, setFeedbackHistory] = useState<FeedbackRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedHotspot, setSelectedHotspot] = useState<Hotspot | null>(null);

  // Form inputs
  const [verifiedClass, setVerifiedClass] = useState<FireClass>("accidental_industrial_fire");
  const [reviewerName, setReviewerName] = useState("Lead Thermal Analyst");
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [labelSource, setLabelSource] = useState<string>("analyst_verified");
  const [submitting, setSubmitting] = useState(false);

  const loadData = () => {
    setLoading(true);
    Promise.all([
      hotspotsApi.list({ per_page: 50 }),
      feedbackApi.list({ limit: 50 }),
    ])
      .then(([hotspotsRes, feedbackRes]) => {
        const hList = hotspotsRes.data || [];
        setQueue(hList);
        if (hList.length > 0 && !selectedHotspot) {
          setSelectedHotspot(hList[0]);
          if (hList[0].predicted_class) {
            setVerifiedClass(hList[0].predicted_class);
          }
        }
        setFeedbackHistory(feedbackRes.data || []);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Failed to load review data",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSelectHotspot = (h: Hotspot) => {
    setSelectedHotspot(h);
    if (h.predicted_class) {
      setVerifiedClass(h.predicted_class);
    }
  };

  const handleSubmitFeedback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedHotspot) return;

    if (labelSource === "analyst_verified" && !reviewerName.trim()) {
      addToast({
        type: "warning",
        title: "Reviewer Name Required",
        message: "Analyst-verified labels require a reviewer name for audit logging.",
      });
      return;
    }

    setSubmitting(true);
    try {
      await feedbackApi.create({
        hotspot_id: selectedHotspot.id,
        suggested_class: selectedHotspot.predicted_class || "uncertain",
        verified_class: verifiedClass,
        is_correct: selectedHotspot.predicted_class === verifiedClass,
        reviewer_name: reviewerName,
        label_source: labelSource,
        notes: reviewerNotes,
        evidence: {
          frp: selectedHotspot.frp,
          satellite: selectedHotspot.satellite,
          latitude: selectedHotspot.latitude,
          longitude: selectedHotspot.longitude,
        },
      });

      addToast({
        type: "success",
        title: "Verification Recorded",
        message: `Saved human label '${FIRE_CLASS_LABELS[verifiedClass]}' to feedback log.`,
      });

      setReviewerNotes("");
      loadData();
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Submission Failed",
        message: err instanceof Error ? err.message : "Error saving analyst feedback",
      });
    } finally {
      setSubmitting(false);
    }
  };

  // Review statistics
  const stats = useMemo(() => {
    const total = feedbackHistory.length;
    const verified = feedbackHistory.filter((f) => f.label_source === "analyst_verified").length;
    const corrections = feedbackHistory.filter((f) => !f.is_correct).length;
    const correctionRate = total > 0 ? ((corrections / total) * 100).toFixed(1) : "0.0";
    return { total, verified, corrections, correctionRate };
  }, [feedbackHistory]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Review Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <MetricCard
          label="Human-Verified Records"
          value={loading ? "..." : stats.verified}
          meta="Analyst validated ground truth"
          icon="✅"
        />
        <MetricCard
          label="Queue Review Items"
          value={loading ? "..." : queue.length}
          meta="Satellite thermal detections"
          icon="📋"
        />
        <MetricCard
          label="Analyst Correction Rate"
          value={loading ? "..." : `${stats.correctionRate}%`}
          meta={`${stats.corrections} corrections recorded`}
          icon="🔄"
        />
        <MetricCard
          label="Weak Rule Guard"
          value="Enforced"
          meta="Weak rules never auto-verified"
          icon="🛡️"
        />
      </div>

      {/* Main Review Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        {/* 1. Review Queue List */}
        <Card>
          <CardHeader
            title="Thermal Detection Review Queue"
            subtitle="Select an incident to examine evidence and confirm or correct label"
          />
          {loading ? (
            <TableSkeleton rows={5} cols={4} />
          ) : queue.length === 0 ? (
            <EmptyState title="Queue Empty" description="All thermal anomalies have been reviewed." />
          ) : (
            <div className="table-container" style={{ maxHeight: 380, overflowY: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>FRP</th>
                    <th>Suggested Label</th>
                    <th style={{ textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((h) => {
                    const isSelected = selectedHotspot?.id === h.id;
                    return (
                      <tr
                        key={h.id}
                        style={{
                          background: isSelected ? "var(--primary-subtle)" : undefined,
                          cursor: "pointer",
                        }}
                        onClick={() => handleSelectHotspot(h)}
                      >
                        <td className="text-xs">{h.acq_date || "Recent"}</td>
                        <td className="font-bold text-danger">{h.frp ? `${h.frp} MW` : "N/A"}</td>
                        <td>
                          {h.predicted_class ? (
                            <FireClassBadge fireClass={h.predicted_class} size="sm" />
                          ) : (
                            <span className="badge badge--neutral">Unclassified</span>
                          )}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <Button
                            variant={isSelected ? "primary" : "outline"}
                            size="sm"
                            onClick={() => handleSelectHotspot(h)}
                          >
                            {isSelected ? "Inspecting" : "Select"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* 2. Verification Form & Evidence Card */}
        <Card>
          <CardHeader
            title="Analyst Verification Panel"
            subtitle="Record human confirmation or correction for continuous learning"
          />
          {selectedHotspot ? (
            <form onSubmit={handleSubmitFeedback} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Evidence Summary Box */}
              <div
                style={{
                  background: "var(--surface-subtle)",
                  border: "1px solid var(--border-card)",
                  borderRadius: "var(--radius-inner)",
                  padding: 12,
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  fontSize: "0.8rem",
                }}
              >
                <div>
                  <span className="text-muted">Coordinate:</span>{" "}
                  <strong>{selectedHotspot.latitude.toFixed(3)}°N, {selectedHotspot.longitude.toFixed(3)}°E</strong>
                </div>
                <div>
                  <span className="text-muted">Sensor:</span> <strong>{selectedHotspot.satellite} VIIRS</strong>
                </div>
                <div>
                  <span className="text-muted">FRP:</span> <strong className="text-danger">{selectedHotspot.frp} MW</strong>
                </div>
                <div>
                  <span className="text-muted">Suggested:</span>{" "}
                  <strong>{selectedHotspot.predicted_class ? FIRE_CLASS_LABELS[selectedHotspot.predicted_class] : "Uncertain"}</strong>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Verified Ground-Truth Label *</label>
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
              </div>

              <div className="form-group">
                <label className="form-label">Reviewer Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  placeholder="e.g. Lead Thermal Analyst"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Label Provenance Source</label>
                <select
                  className="form-select"
                  value={labelSource}
                  onChange={(e) => setLabelSource(e.target.value)}
                >
                  <option value="analyst_verified">analyst_verified (Human Expert)</option>
                  <option value="weak_rule">weak_rule (Algorithmic Heuristic)</option>
                  <option value="model_inference">model_inference (Model Output)</option>
                </select>
                <span className="text-xs text-muted" style={{ marginTop: 2 }}>
                  Weak rules are tagged explicitly and excluded from verified training sets.
                </span>
              </div>

              <div className="form-group">
                <label className="form-label">Analytic Evidence & Notes</label>
                <textarea
                  className="form-textarea"
                  rows={2}
                  placeholder="Evidence observations from Sentinel-2 SWIR or plant shift schedules..."
                  value={reviewerNotes}
                  onChange={(e) => setReviewerNotes(e.target.value)}
                />
              </div>

              <Button variant="primary" loading={submitting} type="submit" style={{ marginTop: 4 }}>
                💾 Submit Ground-Truth Label
              </Button>
            </form>
          ) : (
            <div className="empty-state">Select an incident from the queue to verify.</div>
          )}
        </Card>
      </div>

      {/* Verified History Table */}
      <Card>
        <CardHeader
          title="Verified Submissions History"
          subtitle="Audit log of analyst-reviewed and weak-rule classifications"
        />
        {feedbackHistory.length === 0 ? (
          <EmptyState title="No Submissions Yet" description="Verified analyst entries will be archived here." />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Reviewer</th>
                  <th>Verified Label</th>
                  <th>Suggested Label</th>
                  <th>Provenance</th>
                  <th>Accuracy</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {feedbackHistory.map((fb) => (
                  <tr key={fb.id}>
                    <td className="text-xs text-muted">{new Date(fb.created_at).toLocaleString()}</td>
                    <td className="font-bold">{fb.reviewer_name || "Analyst"}</td>
                    <td>
                      <FireClassBadge fireClass={fb.verified_class} size="sm" />
                    </td>
                    <td className="text-xs">
                      {fb.suggested_class ? FIRE_CLASS_LABELS[fb.suggested_class as FireClass] || fb.suggested_class : "Uncertain"}
                    </td>
                    <td>
                      <span className={`badge ${fb.label_source === "analyst_verified" ? "badge--success" : "badge--warning"}`}>
                        {fb.label_source}
                      </span>
                    </td>
                    <td>
                      {fb.is_correct ? (
                        <span className="badge badge--success">Match</span>
                      ) : (
                        <span className="badge badge--critical">Corrected</span>
                      )}
                    </td>
                    <td style={{ maxWidth: 220, fontSize: "0.8rem" }}>{fb.notes || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
