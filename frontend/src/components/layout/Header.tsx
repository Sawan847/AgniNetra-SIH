import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HealthIndicator } from "../health/HealthIndicator";
import { alertsApi } from "../../api/client";

interface HeaderProps {
  onMobileMenuToggle?: () => void;
}

export function Header({ onMobileMenuToggle }: HeaderProps) {
  const [activeAlertsCount, setActiveAlertsCount] = useState<number>(0);

  useEffect(() => {
    alertsApi
      .list({ status: "active", per_page: 1 })
      .then((res) => {
        setActiveAlertsCount(res.meta?.total ?? res.data?.length ?? 0);
      })
      .catch(() => {
        // Silently handle if offline/initial loading
      });
  }, []);

  return (
    <header className="header">
      <div className="header__left">
        {onMobileMenuToggle && (
          <button
            className="btn btn--outline btn--icon"
            onClick={onMobileMenuToggle}
            aria-label="Toggle mobile menu"
            style={{ display: "none" }}
            id="mobile-menu-btn"
          >
            ☰
          </button>
        )}
        <div className="header__badge">
          <span className="pulse-dot pulse-dot--success" />
          GOI • SIH 2024
        </div>
        <div>
          <div className="header__title">National Emergency Command Centre</div>
          <div className="header__subtitle">
            Industrial Thermal Intelligence & Wildfire Classification
          </div>
        </div>
      </div>

      <div className="header__right">
        <Link
          to="/alerts"
          className="btn btn--outline btn--sm"
          style={{
            borderColor: activeAlertsCount > 0 ? "var(--danger-border)" : undefined,
            background: activeAlertsCount > 0 ? "var(--danger-subtle)" : undefined,
          }}
        >
          {activeAlertsCount > 0 && <span className="pulse-dot pulse-dot--danger" />}
          <span>Alerts</span>
          {activeAlertsCount > 0 && (
            <span
              style={{
                background: "var(--danger)",
                color: "white",
                borderRadius: "var(--radius-pill)",
                padding: "1px 6px",
                fontSize: "0.7rem",
                fontWeight: 700,
              }}
            >
              {activeAlertsCount}
            </span>
          )}
        </Link>
        <HealthIndicator />
      </div>
    </header>
  );
}
