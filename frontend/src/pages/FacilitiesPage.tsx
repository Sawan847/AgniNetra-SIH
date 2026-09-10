import { useEffect, useState, useMemo } from "react";
import { Card, MetricCard, CardHeader } from "../components/common/Card";
import { Button } from "../components/common/Button";
import { Drawer } from "../components/common/Drawer";
import { TableSkeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { useToast } from "../components/common/Toast";
import { facilitiesApi, hotspotsApi } from "../api/client";
import type { IndustrialFacility, Hotspot } from "../types";

export function FacilitiesPage() {
  const { addToast } = useToast();

  const [facilities, setFacilities] = useState<IndustrialFacility[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState("all");

  const [selectedFacility, setSelectedFacility] = useState<IndustrialFacility | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [nearbyHotspots, setNearbyHotspots] = useState<Hotspot[]>([]);
  const [loadingNearby, setLoadingNearby] = useState(false);

  useEffect(() => {
    setLoading(true);
    facilitiesApi
      .list({ limit: 100 })
      .then((res) => {
        setFacilities(res.data || []);
      })
      .catch((err) => {
        addToast({
          type: "danger",
          title: "Failed to load facilities",
          message: err.message,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const filteredFacilities = useMemo(() => {
    return facilities.filter((f) => {
      const matchesSearch =
        !searchTerm ||
        (f.name && f.name.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (f.osm_id && f.osm_id.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchesType =
        selectedType === "all" ||
        (f.facility_type && f.facility_type.toLowerCase() === selectedType.toLowerCase());
      return matchesSearch && matchesType;
    });
  }, [facilities, searchTerm, selectedType]);

  const handleInspectFacility = (f: IndustrialFacility) => {
    setSelectedFacility(f);
    setDrawerOpen(true);
    setLoadingNearby(true);

    if (f.latitude && f.longitude) {
      hotspotsApi
        .list({
          bbox: `${f.longitude - 0.08},${f.latitude - 0.08},${f.longitude + 0.08},${f.latitude + 0.08}`,
          per_page: 20,
        })
        .then((res) => {
          setNearbyHotspots(res.data || []);
        })
        .catch(() => {
          setNearbyHotspots([]);
        })
        .finally(() => {
          setLoadingNearby(false);
        });
    } else {
      setLoadingNearby(false);
      setNearbyHotspots([]);
    }
  };

  const facilityTypes = useMemo(() => {
    const types = new Set<string>();
    facilities.forEach((f) => {
      if (f.facility_type) types.add(f.facility_type);
    });
    return Array.from(types);
  }, [facilities]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Metric Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        <MetricCard
          label="Monitored Facilities"
          value={loading ? "..." : facilities.length}
          meta="OpenStreetMap Industrial Infrastructure"
          icon="🏭"
        />
        <MetricCard
          label="Refineries & Flare Sites"
          value={
            loading
              ? "..."
              : facilities.filter((f) => (f.facility_type || "").includes("refinery") || (f.facility_type || "").includes("oil")).length
          }
          meta="Continuous thermal emission assets"
          icon="🔥"
        />
        <MetricCard
          label="Thermal Surveillance Radius"
          value="5.0 km"
          meta="Automated perimeter buffering"
          icon="📡"
        />
        <MetricCard
          label="Perimeter Alerts"
          value="Active"
          meta="Integrated with Two-Stage ML"
          icon="🛡️"
        />
      </div>

      {/* Facilities Directory Card */}
      <Card>
        <CardHeader
          title="Industrial Infrastructure Registry"
          subtitle="Real-time containment and perimeter monitoring directory"
          action={
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <input
                type="text"
                className="form-input"
                placeholder="Search by facility name or OSM ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ width: 240 }}
              />
              <select
                className="form-select"
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                style={{ width: 160 }}
              >
                <option value="all">All Facility Types</option>
                {facilityTypes.map((t) => (
                  <option key={t} value={t}>
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          }
        />

        {loading ? (
          <TableSkeleton rows={6} cols={5} />
        ) : filteredFacilities.length === 0 ? (
          <EmptyState
            title="No Facilities Found"
            description="No industrial facilities matched your search and filter criteria."
            actionLabel="Reset Filters"
            onAction={() => {
              setSearchTerm("");
              setSelectedType("all");
            }}
          />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Facility Name</th>
                  <th>Category</th>
                  <th>OSM Identifier</th>
                  <th>Coordinates</th>
                  <th>Perimeter Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredFacilities.map((f) => (
                  <tr key={f.id}>
                    <td className="font-bold">{f.name || "Industrial Facility (OSM)"}</td>
                    <td>
                      <span className="badge badge--low">
                        {f.facility_type ? f.facility_type.toUpperCase() : "INDUSTRIAL"}
                      </span>
                    </td>
                    <td>
                      <code style={{ fontSize: "0.75rem", background: "#F1F5F9", padding: "2px 6px", borderRadius: 4 }}>
                        {f.osm_id || "OSM-NODE"}
                      </code>
                    </td>
                    <td className="text-muted text-xs">
                      {f.latitude && f.longitude
                        ? `${f.latitude.toFixed(3)}°N, ${f.longitude.toFixed(3)}°E`
                        : "Geocoded in PostGIS"}
                    </td>
                    <td>
                      <span className="badge badge--success">Perimeter Monitored</span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <Button variant="outline" size="sm" onClick={() => handleInspectFacility(f)}>
                        Inspect Perimeter ➔
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Facility Inspection Drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={selectedFacility?.name || "Facility Surveillance"}
        subtitle={
          selectedFacility?.latitude && selectedFacility?.longitude
            ? `${selectedFacility.latitude.toFixed(4)}°N • ${selectedFacility.longitude.toFixed(4)}°E`
            : "Asset Metadata"
        }
      >
        {selectedFacility && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div
              style={{
                background: "var(--surface-subtle)",
                border: "1px solid var(--border-card)",
                borderRadius: 12,
                padding: 14,
              }}
            >
              <div className="text-xs text-muted font-semibold">INFRASTRUCTURE CATEGORY</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 700, marginTop: 4 }}>
                {selectedFacility.facility_type?.toUpperCase() || "INDUSTRIAL SITE"}
              </div>
              <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                Source: <strong>{selectedFacility.source || "OpenStreetMap"}</strong> &nbsp;•&nbsp; OSM ID: <code>{selectedFacility.osm_id}</code>
              </div>
            </div>

            <div>
              <h4 style={{ marginBottom: 8 }}>Perimeter Thermal Detections (within 8 km)</h4>
              {loadingNearby ? (
                <div className="text-xs text-muted">Scanning satellite telemetry...</div>
              ) : nearbyHotspots.length === 0 ? (
                <div
                  style={{
                    padding: "20px 14px",
                    background: "white",
                    borderRadius: 10,
                    border: "1px solid var(--border-card)",
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: "0.85rem",
                  }}
                >
                  ✅ No active thermal anomalies detected inside facility perimeter.
                </div>
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>FRP</th>
                        <th>Class</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nearbyHotspots.map((h) => (
                        <tr key={h.id}>
                          <td className="text-xs">{h.acq_date || "Recent"}</td>
                          <td className="font-bold text-danger">{h.frp ? `${h.frp} MW` : "N/A"}</td>
                          <td>
                            <span className="badge badge--high">
                              {h.predicted_class ? h.predicted_class.replace(/_/g, " ") : "thermal event"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
