import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge Component", () => {
  it("renders success badge with correct text", () => {
    render(<StatusBadge variant="success">Active</StatusBadge>);
    const el = screen.getByText("Active");
    expect(el).toBeInTheDocument();
    expect(el).toHaveClass("badge--success");
  });

  it("renders error badge with correct class", () => {
    render(<StatusBadge variant="error">Critical</StatusBadge>);
    const el = screen.getByText("Critical");
    expect(el).toHaveClass("badge--error");
  });
});
