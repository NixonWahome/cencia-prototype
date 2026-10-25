import { Link } from "react-router-dom";
import { useApi } from "../api/live";
import type { Alert, Overview as OverviewData, SitePoint, SiteSummary } from "../api/types";
import { Sparkline } from "../components/charts";
import { Card, Kpi, Loading, PageHeader, SeverityBadge, StatusPill, cx } from "../components/ui";
import { SITE_SHORT, fmtKw, fmtKwh, fmtSeconds, hhmm } from "../lib/format";

function SiteCard({ site }: { site: SiteSummary }) {
  const { data } = useApi<{ points: SitePoint[] }>(`/api/sites/${site.id}/telemetry`, ["tick"]);
  const pct = (site.live_kw / site.capacity_kwp) * 100;
  return (
    <Link
      to={`/sites/${site.id}`}
      className={cx(
        "group block rounded-xl border bg-white p-4 shadow-card transition-shadow hover:shadow-md",
        site.status === "alert" ? "border-sev-critical ring-2 ring-sev-critical/20" : "border-line",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-ink group-hover:text-brand">{site.name}</h3>
          <div className="text-xs text-ink-muted">{site.site_type} · {site.capacity_kwp >= 1000 ? `${site.capacity_kwp / 1000} MWp` : `${site.capacity_kwp} kWp`}</div>
        </div>
        <StatusPill status={site.status} />
      </div>

      <div className="mt-3 flex items-end justify-between">
        <div>
          <div className="text-3xl font-semibold tabular-nums text-ink">{fmtKw(site.live_kw)}</div>
          <div className="text-xs text-ink-muted">{pct.toFixed(0)}% of capacity · {site.irradiance_wm2.toFixed(0)} W/m²</div>
        </div>
        <div className="text-right text-xs text-ink-muted">
          today<br />
          <span className="font-semibold text-ink">{fmtKwh(site.energy_today_kwh)}</span>
        </div>
      </div>

      <div className="mt-2 -mx-1">{data && <Sparkline data={data.points} />}</div>

      <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3 text-center">
        <div>
          <dt className="text-[11px] text-ink-muted">Open alerts</dt>
          <dd className={cx("text-lg font-semibold tabular-nums", site.open_alerts ? "text-sev-critical" : "text-ink")}>{site.open_alerts}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-ink-muted">Risk score</dt>
          <dd className={cx("text-lg font-semibold tabular-nums", (site.risk_score ?? 0) >= 70 ? "text-sev-critical" : "text-ink")}>{site.risk_score ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-ink-muted">Integrity</dt>
          <dd className={cx("text-lg font-semibold tabular-nums", site.integrity.ok ? "text-brand" : "text-sev-critical")}>
            {site.integrity.integrity_pct.toFixed(site.integrity.ok ? 0 : 2)}%
          </dd>
        </div>
      </dl>
      <div className="mt-2 text-center text-[11px] text-ink-faint">
        {site.online_devices}/{site.inverters} inverters reporting
      </div>
    </Link>
  );
}

export default function Overview() {
  const { data } = useApi<OverviewData>("/api/overview", ["tick", "alerts", "scans", "integrity"]);
  const { data: alerts } = useApi<Alert[]>("/api/alerts?status=active&limit=6", ["alerts"]);
  if (!data) return <Loading />;
  const k = data.kpis;
  return (
    <>
      <PageHeader
        title="Fleet overview"
        subtitle={`Live from 3 demo sites · sim time ${hhmm(data.sim.sim_time)} EAT`}
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Capacity monitored" value={`${k.mw_monitored} MW`} hint={`${k.live_mw.toFixed(2)} MW generating now`} />
        <Kpi label="Open critical alerts" value={k.open_critical_alerts} tone={k.open_critical_alerts ? "bad" : undefined} hint={`${k.open_alerts} open in total`} />
        <Kpi label="Avg time to detect" value={fmtSeconds(k.avg_mttd_seconds)} hint="across injected attacks" />
        <Kpi label="Telemetry verified" value={`${k.telemetry_verified_pct.toFixed(k.telemetry_verified_pct === 100 ? 0 : 3)}%`} tone={k.telemetry_verified_pct === 100 ? "good" : "bad"} hint="Ed25519 signed + hash-chained" />
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.sites.map((s) => <SiteCard key={s.id} site={s} />)}
      </div>

      <Card className="mt-5" title="Active alerts" action={<Link to="/alerts" className="text-sm font-medium text-brand hover:underline">All alerts →</Link>}>
        {alerts && alerts.length ? (
          <ul className="divide-y divide-line">
            {alerts.map((a) => (
              <li key={a.id}>
                <Link to={`/alerts?id=${a.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-canvas">
                  <SeverityBadge severity={a.severity} />
                  <span className="flex-1 truncate text-sm font-medium">{a.title}</span>
                  <span className="hidden text-xs text-ink-muted sm:inline">{SITE_SHORT[a.site_id]}</span>
                  <span className="text-xs tabular-nums text-ink-muted">{a.mttd_seconds !== null ? `detected in ${fmtSeconds(a.mttd_seconds)}` : hhmm(a.detected_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex items-center gap-2 px-4 py-6 text-sm text-ink-muted">
            <span className="text-sev-good">✓</span> All clear: no active alerts across the fleet.
          </div>
        )}
      </Card>
    </>
  );
}
