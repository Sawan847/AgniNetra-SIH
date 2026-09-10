import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "./Sidebar";

describe("Sidebar Component", () => {
  it("renders all command centre navigation links", () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={() => {}} />
      </MemoryRouter>
    );

    expect(screen.getByText("AgniNetra AI")).toBeInTheDocument();
    expect(screen.getByText("Live Operations")).toBeInTheDocument();
    expect(screen.getByText("Incident Investigation")).toBeInTheDocument();
    expect(screen.getByText("Facility Monitoring")).toBeInTheDocument();
    expect(screen.getByText("Historical Analytics")).toBeInTheDocument();
    expect(screen.getByText("Alerts Centre")).toBeInTheDocument();
    expect(screen.getByText("Model Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Analyst Feedback")).toBeInTheDocument();
    expect(screen.getByText("System Health")).toBeInTheDocument();
  });

  it("hides labels when collapsed", () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={() => {}} />
      </MemoryRouter>
    );

    expect(screen.queryByText("Live Operations")).not.toBeInTheDocument();
    expect(screen.queryByText("Alerts Centre")).not.toBeInTheDocument();
  });
});
