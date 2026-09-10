import { useHealthCheck } from "../hooks/useHealthCheck";
import { FIRE_CLASS_LABELS, FIRE_CLASS_COLORS } from "../types";
import type { FireClass, ServiceStatus } from "../types";

const CLASSIFICATION_CATEGORIES = Object.entries(FIRE_CLASS_LABELS) as [
  FireClass,
  string,
][];

export function DashboardPage() {
  const { health } = useHealthCheck();

  return (
    <div className="page page--dashboard">
      <h2 className="page__title">Dashboard</h2>

      <div className="dashboard-grid">
        {/* System Status Card */}
        <section className="card">
          <h3 className="card__title">System Status</h3>
          <div className="card__body">
            <p>
              <strong>Backend:</strong>{" "}
              {health?.status === "healthy" ? "✅ Online" : "⚠️ Checking…"}
            </p>
            {health?.services.map((svc: ServiceStatus) => (
              <p key={svc.name}>
                <strong>{svc.name}:</strong>{" "}
                {svc.status === "healthy"
                  ? `✅ ${svc.latency_ms?.toFixed(1)}ms`
                  : `❌ ${svc.error ?? "Unavailable"}`}
              </p>
            ))}
          </div>
        </section>

        {/* Classification Categories Card */}
        <section className="card">
          <h3 className="card__title">Classification Categories</h3>
          <div className="card__body">
            <ul className="category-list">
              {CLASSIFICATION_CATEGORIES.map(([key, label]) => (
                <li key={key} className="category-list__item">
                  <span
                    className="category-dot"
                    style={{ backgroundColor: FIRE_CLASS_COLORS[key] }}
                  />
                  {label}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Quick Stats Placeholder */}
        <section className="card">
          <h3 className="card__title">Hotspot Summary</h3>
          <div className="card__body card__body--stats">
            <div className="stat">
              <span className="stat__value">—</span>
              <span className="stat__label">Total Hotspots</span>
            </div>
            <div className="stat">
              <span className="stat__value">—</span>
              <span className="stat__label">Active Alerts</span>
            </div>
            <div className="stat">
              <span className="stat__value">—</span>
              <span className="stat__label">Last Ingestion</span>
            </div>
          </div>
        </section>

        {/* Data Sources Card */}
        <section className="card">
          <h3 className="card__title">Data Sources</h3>
          <div className="card__body">
            <ul className="source-list">
              <li>🛰️ NASA FIRMS (VIIRS / MODIS)</li>
              <li>🗺️ OpenStreetMap Industrial Data</li>
              <li>🌍 ESA WorldCover Land Classification</li>
              <li>📡 Sentinel-2 Satellite Imagery</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}
