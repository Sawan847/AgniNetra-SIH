import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { ToastProvider } from "../common/Toast";

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <ToastProvider>
      <div className="app-shell">
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed((prev) => !prev)}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
        />

        {mobileOpen && (
          <div
            className="drawer-backdrop"
            style={{ zIndex: 25 }}
            onClick={() => setMobileOpen(false)}
          />
        )}

        <div className="app-shell__main">
          <Header onMobileMenuToggle={() => setMobileOpen((prev) => !prev)} />
          <main className="app-shell__content">
            <Outlet />
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
