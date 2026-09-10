import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import * as healthHook from "../hooks/useHealthCheck";

describe("DashboardPage Component", () => {
  it("renders dashboard cards and classifications", () => {
    vi.spyOn(healthHook, "useHealthCheck").mockReturnValue({
      health: {
        status: "healthy",
        version: "0.1.0",
        environment: "development",
        timestamp: "2024-09-10T12:00:00Z",
        services: [{ name: "postgresql", status: "healthy", latency_ms: 1.2, error: null }],
      },
      loading: false,
      error: null,
    });

    render(<DashboardPage />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("System Status")).toBeInTheDocument();
    expect(screen.getByText("Classification Categories")).toBeInTheDocument();
    expect(screen.getByText("Accidental Industrial Fire")).toBeInTheDocument();
    expect(screen.getByText("Forest / Natural Fire")).toBeInTheDocument();
  });
});
