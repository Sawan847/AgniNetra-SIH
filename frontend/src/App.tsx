import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { OperationsPage } from "./pages/OperationsPage";
import { InvestigationPage } from "./pages/InvestigationPage";
import { FacilitiesPage } from "./pages/FacilitiesPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ModelIntelligencePage } from "./pages/ModelIntelligencePage";
import { LabellingPage } from "./pages/LabellingPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          {/* 1. Live Operations Command Centre */}
          <Route index element={<OperationsPage />} />
          <Route path="map" element={<OperationsPage />} />

          {/* 2. Incident Investigation */}
          <Route path="investigate" element={<InvestigationPage />} />
          <Route path="investigate/:id" element={<InvestigationPage />} />

          {/* 3. Industrial Facility Monitoring */}
          <Route path="facilities" element={<FacilitiesPage />} />

          {/* 4. Historical Analytics */}
          <Route path="analytics" element={<AnalyticsPage />} />

          {/* 5. Alerts Centre */}
          <Route path="alerts" element={<AlertsPage />} />

          {/* 6. Model Intelligence */}
          <Route path="model" element={<ModelIntelligencePage />} />

          {/* 7. Analyst Labelling and Feedback */}
          <Route path="labelling" element={<LabellingPage />} />

          {/* 8. System Health */}
          <Route path="system" element={<SystemHealthPage />} />
          <Route path="settings" element={<SystemHealthPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
