import {
  FIRE_CLASS_COLORS,
  FIRE_CLASS_LABELS,
  type FireClass,
} from "../../types";

export interface FireClassBadgeProps {
  fireClass: FireClass | string;
  size?: "sm" | "md";
}

export function FireClassBadge({ fireClass, size = "md" }: FireClassBadgeProps) {
  const normalized = fireClass as FireClass;
  const label = FIRE_CLASS_LABELS[normalized] || fireClass;
  const color = FIRE_CLASS_COLORS[normalized] || "#64748B";

  const isCritical = normalized === "accidental_industrial_fire";

  return (
    <span
      className="badge"
      style={{
        backgroundColor: `${color}18`,
        color: color,
        border: `1px solid ${color}40`,
        fontSize: size === "sm" ? "0.7rem" : "0.75rem",
        padding: size === "sm" ? "2px 8px" : "3px 10px",
      }}
    >
      {isCritical && <span className="pulse-dot pulse-dot--danger" />}
      {label}
    </span>
  );
}
