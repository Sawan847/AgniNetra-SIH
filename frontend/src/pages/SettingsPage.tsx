import { useHealthCheck } from "../hooks/useHealthCheck";
import type { ServiceStatus } from "../types";

export function SettingsPage() {
  const { health, loading, error } = useHealthCheck();

  return (
    <div className="page page--settings">
      <h2 className="page__title">Settings</h2>

      <div className="settings-grid">
        <section className="card">
          <h3 className="card__title">Connection Status</h3>
          <div className="card__body">
            {loading && <p>Checking backend connection…</p>}
            {error && (
              <p className="text--error">
                ❌ Connection error: {error}
              </p>
            )}
            {health && (
              <table className="settings-table">
                <tbody>
                  <tr>
                    <td>Backend Status</td>
                    <td>{health.status}</td>
                  </tr>
                  <tr>
                    <td>Version</td>
                    <td>{health.version}</td>
                  </tr>
                  <tr>
                    <td>Environment</td>
                    <td>{health.environment}</td>
                  </tr>
                  {health.services.map((svc: ServiceStatus) => (
                    <tr key={svc.name}>
                      <td>{svc.name}</td>
                      <td>
                        {svc.status === "healthy"
                          ? `✅ Healthy (${svc.latency_ms?.toFixed(1)}ms)`
                          : `❌ ${svc.error}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="card">
          <h3 className="card__title">About</h3>
          <div className="card__body">
            <p>
              <strong>AgniNetra AI</strong> — Industrial Thermal Intelligence
              and Fire Classification Platform
            </p>
            <p>
              Smart India Hackathon project integrating NASA FIRMS, OpenStreetMap,
              satellite imagery, and land-cover data for thermal anomaly
              classification.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
