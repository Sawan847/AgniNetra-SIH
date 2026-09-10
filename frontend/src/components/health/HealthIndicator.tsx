import { useHealthCheck } from "../../hooks/useHealthCheck";

/**
 * Compact indicator showing backend connectivity status.
 * Renders a colored dot with tooltip-style text.
 */
export function HealthIndicator() {
  const { health, loading, error } = useHealthCheck();

  if (loading) {
    return (
      <span className="health-indicator health-indicator--loading">
        <span className="health-dot health-dot--loading" />
        Connecting…
      </span>
    );
  }

  if (error || !health) {
    return (
      <span className="health-indicator health-indicator--error">
        <span className="health-dot health-dot--error" />
        Offline
      </span>
    );
  }

  const isHealthy = health.status === "healthy";

  return (
    <span
      className={`health-indicator ${isHealthy ? "health-indicator--ok" : "health-indicator--warn"}`}
    >
      <span
        className={`health-dot ${isHealthy ? "health-dot--ok" : "health-dot--warn"}`}
      />
      {isHealthy ? "Connected" : "Degraded"}
      <span className="health-version">v{health.version}</span>
    </span>
  );
}
