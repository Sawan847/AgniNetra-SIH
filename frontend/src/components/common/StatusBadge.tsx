import React from "react";

export interface StatusBadgeProps {
  variant:
    | "success"
    | "warning"
    | "error"
    | "info"
    | "neutral"
    | "critical"
    | "high"
    | "medium"
    | "low";
  children: React.ReactNode;
  pulse?: boolean;
}

const VARIANT_CLASSES: Record<StatusBadgeProps["variant"], string> = {
  success: "badge badge--success",
  warning: "badge badge--warning",
  error: "badge badge--critical badge--error",
  critical: "badge badge--critical",
  high: "badge badge--high",
  medium: "badge badge--medium",
  low: "badge badge--low",
  info: "badge badge--info",
  neutral: "badge badge--neutral",
};

export function StatusBadge({ variant, children, pulse }: StatusBadgeProps) {
  return (
    <span className={VARIANT_CLASSES[variant] || "badge"}>
      {pulse && (
        <span
          className={`pulse-dot ${
            variant === "critical" || variant === "error"
              ? "pulse-dot--danger"
              : variant === "warning" || variant === "high"
              ? "pulse-dot--warning"
              : "pulse-dot--success"
          }`}
        />
      )}
      {children}
    </span>
  );
}
