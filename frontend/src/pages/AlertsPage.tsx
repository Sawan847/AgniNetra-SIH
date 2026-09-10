import React, { useEffect, useState, useMemo } from "react";
import { Card, MetricCard, CardHeader } from "../components/common/Card";
import { Button } from "../components/common/Button";
import { StatusBadge } from "../components/common/StatusBadge";
import { Modal } from "../components/common/Modal";
import { TableSkeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { useToast } from "../components/common/Toast";
import { alertsApi, hotspotsApi } from "../api/client";
import type { AlertRead, AlertSeverity, AlertStatus, Hotspot } from "../types";

export function AlertsPage() {
  const { addToast } = useToast();

  const [alerts, setAlerts] = useState<AlertRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");

  // Create alert modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [hotspotsList, setHotspotsList] = useState<Hotspot[]>([]);
  const [selectedHotspotId, setSelectedHotspotId] = useState("");
  const [newSeverity, setNewSeverity] = useState<AlertSeverity>("critical");
  const [newAlertType, setNewAlertType] = useState("emergency_fire");
  const [newDescription, setNewDescription] = useState("");
  const [submittingAlert, setSubmittingAlert] = useState(false);

  const fetchAlerts = () => {
    setLoading(true);
    alertsApi
      .list({
        per_page: 100,
        severity: filterSeverity !== "all" ? (filterSeverity as AlertSeverity) : undefined,
        status: filterStatus !== "all" ? (filterStatus as AlertStatus) : undefined,
      })
      .then((res) => {
        setAlerts(res.data || []);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Failed to load alerts",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchAlerts();
  }, [filterSeverity, filterStatus]);

  // Load hotspots for create modal
  useEffect(() => {
    if (createModalOpen) {
      hotspotsApi.list({ per_page: 30 }).then((res) => {
        setHotspotsList(res.data || []);
        if (res.data && res.data.length > 0) {
          setSelectedHotspotId(res.data[0].id);
        }
      });
    }
  }, [createModalOpen]);

  const handleUpdateStatus = async (alertId: string, status: AlertStatus) => {
    try {
      await alertsApi.updateStatus(alertId, status);
      addToast({
        type: "success",
        title: "Alert Status Updated",
        message: `Alert marked as ${status.replace("_", " ")}.`,
      });
      fetchAlerts();
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Failed to update alert",
        message: err instanceof Error ? err.message : "Error updating alert status",
      });
    }
  };

  const handleCreateAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedHotspotId) {
      addToast({ type: "warning", title: "Missing Hotspot", message: "Please select an associated hotspot." });
      return;
    }
    setSubmittingAlert(true);
    try {
      await alertsApi.create({
        hotspot_id: selectedHotspotId,
        severity: newSeverity,
        alert_type: newAlertType,
        status: "active",
        description: newDescription || "Manual operational alert dispatched from command console",
      });
      addToast({
        type: "success",
        title: "Alert Dispatched",
        message: "New operational incident alert created successfully.",
      });
      setCreateModalOpen(false);
      setNewDescription("");
      fetchAlerts();
    } catch (err: unknown) {
      addToast({
        type: "danger",
        title: "Dispatch Failed",
        message: err instanceof Error ? err.message : "Failed to create alert",
      });
    } finally {
      setSubmittingAlert(false);
    }
  };

  // Severity metrics calculation
  const counts = useMemo(() => {
    const critical = alerts.filter((a) => a.severity === "critical").length;
    const high = alerts.filter((a) => a.severity === "high").length;
    const medium = alerts.filter((a) => a.severity === "medium").length;
    const low = alerts.filter((a) => a.severity === "low").length;
    return { critical, high, medium, low };
  }, [alerts]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Severity Metrics Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <MetricCard
          label="Critical Incidents"
          value={loading ? "..." : counts.critical}
          meta="Immediate emergency response"
          icon="🚨"
          trend={counts.critical > 0 ? "up" : "neutral"}
        />
        <MetricCard
          label="High Severity"
          value={loading ? "..." : counts.high}
          meta="Monitored industrial flaring & fires"
          icon="⚠️"
        />
        <MetricCard
          label="Medium Priority"
          value={loading ? "..." : counts.medium}
          meta="Agricultural & natural fire alerts"
          icon="🌾"
        />
        <MetricCard
          label="Low / Informational"
          value={loading ? "..." : counts.low}
          meta="Routine thermal anomalies"
          icon="ℹ️"
        />
      </div>

      {/* Alerts Table Card */}
      <Card>
        <CardHeader
          title="Operational Alerts Command Log"
          subtitle="Real-time incident dispatching and response lifecycle"
          action={
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
              <select
                className="form-select"
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                style={{ width: 150 }}
              >
                <option value="all">All Severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>

              <select
                className="form-select"
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                style={{ width: 160 }}
              >
                <option value="all">All Statuses</option>
                <option value="active">Active</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="resolved">Resolved</option>
                <option value="false_positive">False Positive</option>
              </select>

              <Button
                variant="primary"
                size="sm"
                onClick={() => setCreateModalOpen(true)}
              >
                + Dispatch Alert
              </Button>
            </div>
          }
        />

        {loading ? (
          <TableSkeleton rows={6} cols={6} />
        ) : alerts.length === 0 ? (
          <EmptyState
            title="No Alerts Found"
            description="There are currently no active or historical alerts matching the selected criteria."
            actionLabel="Reset Filters"
            onAction={() => {
              setFilterSeverity("all");
              setFilterStatus("all");
            }}
          />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Incident Type</th>
                  <th>Description</th>
                  <th>Status</th>
                  <th>Timestamp</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <StatusBadge
                        variant={a.severity}
                        pulse={a.severity === "critical" && a.status === "active"}
                      >
                        {a.severity.toUpperCase()}
                      </StatusBadge>
                    </td>
                    <td className="font-semibold text-xs">
                      {a.alert_type ? a.alert_type.replace(/_/g, " ").toUpperCase() : "GENERAL ALERT"}
                    </td>
                    <td style={{ maxWidth: 320, fontSize: "0.85rem" }}>
                      {a.description || "Operational anomaly detected"}
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background:
                            a.status === "active"
                              ? "var(--danger-subtle)"
                              : a.status === "acknowledged"
                              ? "var(--warning-subtle)"
                              : "var(--success-subtle)",
                          color:
                            a.status === "active"
                              ? "var(--danger)"
                              : a.status === "acknowledged"
                              ? "var(--warning)"
                              : "var(--success)",
                        }}
                      >
                        {a.status.replace(/_/g, " ").toUpperCase()}
                      </span>
                    </td>
                    <td className="text-muted text-xs">
                      {new Date(a.created_at).toLocaleString()}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", gap: 6 }}>
                        {a.status === "active" && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleUpdateStatus(a.id, "acknowledged")}
                          >
                            Acknowledge
                          </Button>
                        )}
                        {a.status !== "resolved" && (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleUpdateStatus(a.id, "resolved")}
                          >
                            Resolve
                          </Button>
                        )}
                        {a.status !== "false_positive" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleUpdateStatus(a.id, "false_positive")}
                          >
                            False Alarm
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Manual Alert Dispatch Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Dispatch New Operational Incident Alert"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={submittingAlert}
              onClick={handleCreateAlert}
            >
              Dispatch Incident Alert
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreateAlert} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="form-group">
            <label className="form-label">Associate Thermal Hotspot *</label>
            <select
              className="form-select"
              value={selectedHotspotId}
              onChange={(e) => setSelectedHotspotId(e.target.value)}
              required
            >
              {hotspotsList.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.acq_date || "Recent"} • {h.frp ? `${h.frp} MW` : "Detection"} • ({h.latitude.toFixed(2)}, {h.longitude.toFixed(2)})
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Alert Severity Level *</label>
            <select
              className="form-select"
              value={newSeverity}
              onChange={(e) => setNewSeverity(e.target.value as AlertSeverity)}
              required
            >
              <option value="critical">Critical (Emergency sirens / evacuation)</option>
              <option value="high">High (Immediate inspection crew dispatch)</option>
              <option value="medium">Medium (Advisory / monitoring)</option>
              <option value="low">Low (Informational / log)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Alert Type Identifier *</label>
            <input
              type="text"
              className="form-input"
              value={newAlertType}
              onChange={(e) => setNewAlertType(e.target.value)}
              placeholder="e.g. industrial_flare_runaway, forest_containment_breach"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Incident Description & Instructions</label>
            <textarea
              className="form-textarea"
              rows={3}
              placeholder="Enter operational incident notes, instructions for first responders..."
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
            />
          </div>
        </form>
      </Modal>
    </div>
  );
}
