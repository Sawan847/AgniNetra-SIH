import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, MetricCard, CardHeader } from "../components/common/Card";
import { CardSkeleton } from "../components/common/Skeleton";
import { useToast } from "../components/common/Toast";
import { modelApi } from "../api/client";
import { FIRE_CLASS_LABELS, type FireClass, type ModelMetrics } from "../types";

/**
 * Format a 0-1 metric as a percentage, or an em dash when it is genuinely absent.
 * Never substitute an invented figure: these tiles previously fell back to
 * hardcoded values (76.8%, 84.2%, 74.5%, 1.8%) that were displayed as the live
 * model's measured performance.
 */
function pct(value: unknown, digits = 1): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function ModelIntelligencePage() {
  const { addToast } = useToast();
  const [metrics, setMetrics] = useState<ModelMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    modelApi
      .metrics()
      .then((res) => {
        setMetrics(res);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Model Metrics Offline",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const evalMetrics = metrics?.evaluation_metrics || {};

  // Format feature importance for horizontal bar chart
  const importanceData = metrics?.feature_importances
    ? Object.entries(metrics.feature_importances)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([name, weight]) => ({
          name: name.replace(/_/g, " "),
          weight: Math.round(weight * 1000) / 10,
        }))
    : [];

  // The model card emits { labels, matrix } so the axes always correspond to the
  // classes actually present in the holdout. An older shape was a bare number[][].
  //
  // There is deliberately no fallback matrix. This previously defaulted to an
  // invented 6x6 grid with ~48 correct on every diagonal, which rendered as a
  // near-perfect confusion matrix for a model that had not been evaluated at all.
  const rawCm = evalMetrics.confusion_matrix;
  const cmLabels: string[] =
    rawCm && !Array.isArray(rawCm) && Array.isArray(rawCm.labels) ? rawCm.labels : [];
  const confusionMatrix: number[][] = Array.isArray(rawCm)
    ? rawCm
    : rawCm && Array.isArray(rawCm.matrix)
      ? rawCm.matrix
      : [];

  // Axis labels come from the matrix itself where available, else the model card's
  // class list. The previous hardcoded list included "Uncertain", which is not a
  // trained class - abstention is a decision rule applied at inference.
  const classSource: string[] =
    cmLabels.length > 0
      ? cmLabels
      : Array.isArray(evalMetrics.classes)
        ? evalMetrics.classes
        : [];
  const classLabels: string[] = classSource.map(
    (c) => FIRE_CLASS_LABELS[c as FireClass] ?? c,
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* KPI Evaluation Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <MetricCard
          label="Holdout Macro F1 Score"
          value={loading ? "..." : pct(evalMetrics.macro_f1)}
          meta="Chronological unseen holdout split"
          icon="🎯"
          trend="up"
        />
        <MetricCard
          label="Macro F1 (confident subset)"
          value={loading ? "..." : pct(evalMetrics.macro_f1_on_confident_subset)}
          meta="Excludes detections the model abstained on"
          icon="📊"
        />
        <MetricCard
          label="Spatial GroupKFold F1"
          value={loading ? "..." : pct(evalMetrics.mean_spatial_cv_f1)}
          meta="5-fold spatial cluster validation"
          icon="🌐"
        />
        <MetricCard
          label="Abstention Rate"
          value={loading ? "..." : pct(evalMetrics.abstain_rate)}
          meta="Routed to human verification queue"
          icon="🛡️"
        />
      </div>

      {/* Honest Limitations & Architecture Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, rgba(29, 78, 216, 0.06) 0%, rgba(13, 148, 136, 0.06) 100%)",
          border: "1px solid var(--primary-border)",
          borderRadius: "var(--radius-card)",
          padding: "16px 20px",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="badge badge--success">ACTIVE INFERENCE ENGINE</span>
            <span className="font-bold">{metrics?.active_model_name || "No model loaded"}</span>
            <span className="text-xs text-muted">v{metrics?.version ?? "—"}</span>
            <span className="badge badge--info">{metrics?.algorithm ?? "—"}</span>
          </div>
          <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
            {evalMetrics.data_provenance
              ? `Trained on: ${evalMetrics.data_provenance}`
              : "Site-level classifier over weakly-supervised FIRMS detections."}
          </div>
        </div>

        <div className="text-xs text-muted" style={{ textAlign: "right" }}>
          Abstains below <strong>&tau; = 0.55</strong> &nbsp;•&nbsp; Features:{" "}
          <strong>{evalMetrics.n_features ?? "—"}</strong> &nbsp;•&nbsp; Classes:{" "}
          <strong>{Array.isArray(evalMetrics.classes) ? evalMetrics.classes.length : "—"}</strong>
        </div>
      </div>

      {loading ? (
        <CardSkeleton height="360px" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
          {/* Top 10 Feature Importances */}
          <Card>
            <CardHeader
              title="Top Attribution Drivers"
              subtitle="Normalized feature importance from the active model"
            />
            {importanceData.length === 0 ? (
              <div
                className="text-muted text-xs"
                style={{ padding: "48px 20px", textAlign: "center", lineHeight: 1.7 }}
              >
                <div style={{ fontSize: 22, marginBottom: 10 }}>📊</div>
                <strong>No feature importances published by this model.</strong>
                <div style={{ marginTop: 8 }}>
                  The active model is{" "}
                  <code>{metrics?.algorithm ?? "unknown"}</code>, which does not expose
                  tree-style importance weights. Per-detection evidence is available on
                  the Incident Investigation page instead.
                </div>
              </div>
            ) : (
            <div style={{ height: 280, width: "100%", marginTop: 10 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  layout="vertical"
                  data={importanceData}
                  margin={{ top: 5, right: 30, left: 70, bottom: 5 }}
                >
                  <XAxis type="number" fontSize={11} tickLine={false} unit="%" />
                  <YAxis type="category" dataKey="name" fontSize={11} tickLine={false} width={150} />
                  <Tooltip formatter={(val) => [`${val}%`, "Importance Weight"]} />
                  <Bar dataKey="weight" fill="var(--primary)" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            )}
          </Card>

          {/* Confusion Matrix Interactive Grid */}
          <Card>
            <CardHeader
              title="Multi-Class Confusion Matrix"
              subtitle="Holdout cross-validation accuracy per operational category"
            />
            <div className="table-container" style={{ marginTop: 8 }}>
              <table className="table" style={{ fontSize: "0.75rem", textAlign: "center" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Actual \ Pred</th>
                    {classLabels.map((lbl, idx) => (
                      <th key={idx} style={{ padding: "8px 6px" }}>{lbl.slice(0, 8)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {confusionMatrix.map((row, rIdx) => (
                    <tr key={rIdx}>
                      <td style={{ textAlign: "left", fontWeight: 700 }}>{classLabels[rIdx]}</td>
                      {row.map((val, cIdx) => {
                        const isDiag = rIdx === cIdx;
                        return (
                          <td
                            key={cIdx}
                            style={{
                              background: isDiag ? "rgba(22, 163, 74, 0.15)" : val > 0 ? "rgba(234, 88, 12, 0.10)" : "transparent",
                              fontWeight: isDiag ? 800 : 400,
                              color: isDiag ? "var(--success)" : val > 0 ? "var(--warning)" : "var(--text-muted)",
                            }}
                          >
                            {val}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="text-xs text-muted" style={{ marginTop: 10, textAlign: "center" }}>
              Green diagonal represents verified true-positive classifications.
            </div>
          </Card>
        </div>
      )}

      {/* Methodological Rigor & Data Leakage Safeguards */}
      <Card>
        <CardHeader
          title="Methodological Rigor & Scientific Safeguards"
          subtitle="Measures implemented to guarantee honest, production-quality AI evaluation"
        />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
          <div
            style={{
              padding: 14,
              background: "var(--surface-subtle)",
              borderRadius: "var(--radius-inner)",
              border: "1px solid var(--border-card)",
            }}
          >
            <div className="font-bold text-sm" style={{ color: "var(--primary)", marginBottom: 4 }}>
              1. Spatial GroupKFold Cross-Validation
            </div>
            <div className="text-xs text-secondary">
              Folds are grouped by DBSCAN site ID, so no physical site ever appears in both training and validation. A random split would place the same refinery on both sides and score well by memorising a location.
            </div>
          </div>

          <div
            style={{
              padding: 14,
              background: "var(--surface-subtle)",
              borderRadius: "var(--radius-inner)",
              border: "1px solid var(--border-card)",
            }}
          >
            <div className="font-bold text-sm" style={{ color: "var(--secondary)", marginBottom: 4 }}>
              2. Strict Chronological 15% Holdout
            </div>
            <div className="text-xs text-secondary">
              The reported score comes from the chronologically latest 20% of acquisitions. The model is selected on cross-validation and never on this holdout, so it stays an honest estimate of unseen performance.
            </div>
          </div>

          <div
            style={{
              padding: 14,
              background: "var(--surface-subtle)",
              borderRadius: "var(--radius-inner)",
              border: "1px solid var(--border-card)",
            }}
          >
            <div className="font-bold text-sm" style={{ color: "var(--warning)", marginBottom: 4 }}>
              3. Honest Uncertainty Thresholding
            </div>
            <div className="text-xs text-secondary">
              Whenever the calibrated class probability falls below &tau; = 0.45, the platform assigns "Uncertain", preventing confident misclassifications on ambiguous data.
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
