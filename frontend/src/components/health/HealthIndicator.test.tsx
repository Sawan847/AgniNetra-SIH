import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { HealthIndicator } from "./HealthIndicator";
import * as healthHook from "../../hooks/useHealthCheck";

describe("HealthIndicator Component", () => {
  it("renders loading state initially", () => {
    vi.spyOn(healthHook, "useHealthCheck").mockReturnValue({
      health: null,
      loading: true,
      error: null,
    });

    render(<HealthIndicator />);
    expect(screen.getByText(/Connecting/i)).toBeInTheDocument();
  });

  it("renders connected status when healthy", () => {
    vi.spyOn(healthHook, "useHealthCheck").mockReturnValue({
      health: {
        status: "healthy",
        version: "0.1.0",
        environment: "development",
        timestamp: "2024-09-10T12:00:00Z",
        services: [{ name: "postgresql", status: "healthy", latency_ms: 2.5, error: null }],
      },
      loading: false,
      error: null,
    });

    render(<HealthIndicator />);
    expect(screen.getByText(/Connected/i)).toBeInTheDocument();
    expect(screen.getByText(/v0.1.0/i)).toBeInTheDocument();
  });

  it("renders offline state on error", () => {
    vi.spyOn(healthHook, "useHealthCheck").mockReturnValue({
      health: null,
      loading: false,
      error: "Network error",
    });

    render(<HealthIndicator />);
    expect(screen.getByText(/Offline/i)).toBeInTheDocument();
  });
});
