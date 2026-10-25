import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { LiveProvider } from "./api/live";
import { Layout } from "./components/Layout";
import Alerts from "./pages/Alerts";
import Demo from "./pages/Demo";
import Integrity from "./pages/Integrity";
import Overview from "./pages/Overview";
import Report from "./pages/Report";
import SiteDetail from "./pages/SiteDetail";
import Vulnerabilities from "./pages/Vulnerabilities";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LiveProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="sites/:siteId" element={<SiteDetail />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="vulnerabilities" element={<Vulnerabilities />} />
            <Route path="integrity" element={<Integrity />} />
            <Route path="report" element={<Report />} />
            <Route path="demo" element={<Demo />} />
            <Route path="*" element={<Overview />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </LiveProvider>
  </StrictMode>,
);
