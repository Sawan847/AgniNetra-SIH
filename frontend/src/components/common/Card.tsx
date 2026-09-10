import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  glass?: boolean;
}

export function Card({
  glass = false,
  className = "",
  children,
  ...props
}: CardProps) {
  const glassClass = glass ? "card--glass" : "";
  return (
    <div className={`card ${glassClass} ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  action,
  subtitle,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  subtitle?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`card__header ${className}`}>
      {children ? (
        children
      ) : (
        <>
          <div>
            {title && <div className="card__title">{title}</div>}
            {subtitle && (
              <div className="text-xs text-muted" style={{ marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
          {action && <div>{action}</div>}
        </>
      )}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  meta,
  icon,
  trend,
  className = "",
}: {
  label: string;
  value: React.ReactNode;
  meta?: React.ReactNode;
  icon?: React.ReactNode;
  trend?: "up" | "down" | "neutral";
  className?: string;
}) {
  return (
    <Card className={`metric-card ${className}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <span className="metric-card__label">{label}</span>
        {icon && <div style={{ color: "var(--primary)" }}>{icon}</div>}
      </div>
      <div className="metric-card__value">{value}</div>
      {meta && (
        <div className="metric-card__meta">
          {trend === "up" && <span style={{ color: "var(--danger)" }}>▲</span>}
          {trend === "down" && <span style={{ color: "var(--success)" }}>▼</span>}
          {meta}
        </div>
      )}
    </Card>
  );
}
