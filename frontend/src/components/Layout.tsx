import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useLive } from "../api/live";
import { cx } from "./ui";
import { Toasts } from "./Toasts";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/alerts", label: "Alerts" },
  { to: "/vulnerabilities", label: "Vulnerabilities" },
  { to: "/integrity", label: "Integrity" },
  { to: "/report", label: "Investor report" },
  { to: "/demo", label: "Demo" },
];

function SimClock() {
  const { sim, connected } = useLive();
  return (
    <div className="flex items-center gap-2 text-xs text-brand-100">
      <span className={cx("h-2 w-2 rounded-full", connected ? "bg-green-400" : "bg-red-400 animate-pulse")} title={connected ? "Live" : "Reconnecting"} />
      <span className="tabular-nums">
        {sim ? sim.sim_time.slice(11, 16) : "—"}
        <span className="hidden sm:inline">{sim && ` EAT · ${sim.speed}×`}</span>
      </span>
    </div>
  );
}

export function Layout() {
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 bg-brand text-white shadow print:hidden">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            <span className="text-lg font-semibold tracking-tight">
              Cencia<span className="text-accent"> AI</span>
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <SimClock />
            <span className="whitespace-nowrap rounded-md bg-accent px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-white">
              <span className="hidden sm:inline">Simulated </span>demo data
            </span>
          </div>
        </div>
        <nav className="mx-auto max-w-7xl overflow-x-auto px-2" aria-label="Main">
          <ul className="flex min-w-max gap-1 pb-2">
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.end}
                  className={({ isActive }) =>
                    cx("block rounded-md px-3 py-1.5 text-sm font-medium transition-colors", isActive ? "bg-white/15 text-white" : "text-brand-100 hover:bg-white/10 hover:text-white")
                  }
                >
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 pb-24">
        <Outlet />
      </main>
      {pathname !== "/demo" && (
        <Link
          to="/demo"
          className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-accent px-4 py-3 text-sm font-semibold text-white shadow-lg hover:bg-accent-700 print:hidden"
        >
          <span aria-hidden>⚡</span> Demo panel
        </Link>
      )}
      <Toasts />
    </div>
  );
}
