import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthResponse } from "../types";

interface UseHealthCheckResult {
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
}

/**
 * Polls the backend health endpoint at a fixed interval.
 * Returns the latest health status, loading state, and any error.
 */
export function useHealthCheck(intervalMs = 30_000): UseHealthCheckResult {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function check() {
      try {
        const data = await api.get<HealthResponse>("/health");
        if (mounted) {
          setHealth(data);
          setError(null);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Health check failed");
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    check();
    const timer = setInterval(check, intervalMs);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return { health, loading, error };
}
