import { useEffect, useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Card, MetricCard, CardHeader } from "../components/common/Card";
import { CardSkeleton } from "../components/common/Skeleton";
import { useToast } from "../components/common/Toast";
import { analyticsApi } from "../api/client";
import {
  FIRE_CLASS_COLORS,
  FIRE_CLASS_LABELS,
  type AnalyticsSummary,
  type FireClass,
} from "../types";

export function AnalyticsPage() {
  const { addToast } = useToast();
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    analyticsApi
      .summary()
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Analytics Failed to Load",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  // Format classification pie data
  const classPieData = data?.classification_distribution
    ? Object.entries(data.classification_distribution).map(([key, count]) => ({
        name: FIRE_CLASS_LABELS[key as FireClass] || key,
        value: count,
        color: FIRE_CLASS_COLORS[key as FireClass] || "#64748B",
      }))
    : [];

  // Format severity bar data
  const severityBarData = data?.severity_distribution
    ? Object.entries(data.severity_distribution).map(([sev, count]) => ({
        severity: sev.toUpperCase(),
        count: count,
        fill:
          sev === "critical"
            ? "var(--danger)"
            : sev === "high"
            ? "var(--warning)"
            : sev === "medium"
            ? "#CA8A04"
            : "var(--secondary)",
      }))
    : [];

  // Satellite breakdown data
  const satelliteData = data?.satellite_sensor_distribution
    ? Object.entries(data.satellite_sensor_distribution).map(([sensor, count]) => ({
        sensor: sensor || "VIIRS SNPP",
        detections: count,
      }))
    : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <MetricCard
          label="Total Hotspots Ingested"
          value={loading ? "..." : (data?.total_hotspots ?? 0)}
          meta="Satellite thermal anomalies"
          icon="🛰️"
        />
        <MetricCard
          label="Active Operational Alerts"
          value={loading ? "..." : (data?.active_alerts ?? 0)}
          meta={`Out of ${data?.total_alerts ?? 0} total alerts`}
          icon="🚨"
        />
        <MetricCard
          label="Monitored Facilities"
          value={loading ? "..." : (data?.total_facilities ?? 0)}
          meta="Overpass registered assets"
          icon="🏭"
        />
        <MetricCard
          label="Thermal Intensity Peak"
          value={loading ? "..." : `${Math.round(data?.max_frp ?? 0)} MW`}
          meta={`Average FRP: ${data?.avg_frp?.toFixed(1) ?? 0} MW`}
          icon="🔥"
        />
      </div>

      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <CardSkeleton height="320px" />
          <CardSkeleton height="320px" />
        </div>
      ) : (
        <>
          {/* Main Visuals: Classification Donut & 7-Day Trend */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
            {/* 1. Classification Donut Chart */}
            <Card>
              <CardHeader
                title="Fire Classification Distribution"
                subtitle="Categorization across the 6-class operational taxonomy"
              />
              <div style={{ height: 260, width: "100%" }}>
                {classPieData.length === 0 ? (
                  <div className="empty-state" style={{ padding: "40px 0" }}>
                    No predictions recorded yet
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={classPieData}
                        innerRadius={65}
                        outerRadius={95}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {classPieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => [value, "Detections"]} />
                      <Legend iconType="circle" />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>

            {/* 2. 7-Day Chronological Incident Volume Area Chart */}
            <Card>
              <CardHeader
                title="7-Day Incident Trend Timeline"
                subtitle="Daily thermal anomaly volume across regional surveillance"
              />
              <div style={{ height: 260, width: "100%" }}>
                {(!data?.recent_trend_7d || data.recent_trend_7d.length === 0) ? (
                  <div className="empty-state" style={{ padding: "40px 0" }}>
                    No time-series data available
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={data.recent_trend_7d}
                      margin={{ top: 10, right: 20, left: -15, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="date" fontSize={11} tickLine={false} />
                      <YAxis fontSize={11} tickLine={false} />
                      <Tooltip />
                      <Area
                        type="monotone"
                        dataKey="count"
                        stroke="var(--primary)"
                        strokeWidth={2}
                        fillOpacity={1}
                        fill="url(#areaGradient)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>
          </div>

          {/* Secondary Visuals: Severity Bar & Satellite Distribution */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
            {/* 3. Severity Distribution Bar Chart */}
            <Card>
              <CardHeader
                title="Operational Alert Severity"
                subtitle="Distribution of critical, high, medium, and low incidents"
              />
              <div style={{ height: 240, width: "100%" }}>
                {severityBarData.length === 0 ? (
                  <div className="empty-state" style={{ padding: "40px 0" }}>
                    No alerts recorded
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={severityBarData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <XAxis dataKey="severity" fontSize={11} tickLine={false} />
                      <YAxis fontSize={11} tickLine={false} />
                      <Tooltip />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                        {severityBarData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>

            {/* 4. Satellite Sensor Telemetry Breakdown */}
            <Card>
              <CardHeader
                title="Satellite Constellation Telemetry"
                subtitle="Thermal anomalies captured per VIIRS sensor platform"
              />
              <div style={{ height: 240, width: "100%" }}>
                {satelliteData.length === 0 ? (
                  <div className="empty-state" style={{ padding: "40px 0" }}>
                    No sensor statistics available
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={satelliteData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <XAxis dataKey="sensor" fontSize={11} tickLine={false} />
                      <YAxis fontSize={11} tickLine={false} />
                      <Tooltip />
                      <Bar dataKey="detections" fill="var(--secondary)" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
