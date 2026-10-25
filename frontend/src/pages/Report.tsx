import { useSearchParams } from "react-router-dom";
import { useApi } from "../api/live";
import type { Report as ReportData } from "../api/types";
import { DailyEnergyChart } from "../components/charts";
import { Button, Card, Loading, PageHeader, Pill, SiteTabs, cx } from "../components/ui";
import { dayTime, fmtKwh, fmtSeconds, shortHash } from "../lib/format";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 print:shadow-none">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", tone === "good" ? "text-brand" : tone === "bad" ? "text-sev-critical" : "text-ink")}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

export default function Report() {
  const [params, setParams] = useSearchParams();
  const siteId = params.get("site") ?? "kibwezi";
  const { data: r } = useApi<ReportData>(`/api/reports/${siteId}`, ["alerts", "scans", "integrity", "attacks"]);

  const download = () => {
    if (!r) return;
    const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `cencia-report-${siteId}-${r.period.to.slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <div className="print:hidden">
        <PageHeader
          title="Investor report"
          subtitle="Verified generation you can bank on: every kWh traced to a signed, unbroken reading."
          actions={
            <>
              <SiteTabs value={siteId} onChange={(id) => setParams({ site: id }, { replace: true })} />
              <Button onClick={download} disabled={!r}>Download JSON</Button>
              <Button variant="primary" onClick={() => window.print()} disabled={!r}>Print / PDF</Button>
            </>
          }
        />
      </div>
      {!r ? (
        <Loading />
      ) : (
        <article className="mx-auto max-w-4xl space-y-4 rounded-2xl border border-line bg-white p-5 shadow-card sm:p-8 print:max-w-none print:border-0 print:p-0 print:shadow-none">
          <header className="flex flex-col justify-between gap-3 border-b border-line pb-4 sm:flex-row">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-accent-700">Cencia AI · Verified generation report</div>
              <h2 className="mt-1 text-2xl font-semibold">{r.site.name}</h2>
              <div className="text-sm text-ink-muted">{r.site.site_type} · {r.site.capacity_kwp} kWp · {r.site.location}</div>
            </div>
            <div className="text-sm text-ink-muted sm:text-right">
              Period {dayTime(r.period.from)} → {dayTime(r.period.to)}<br />
              Generated {dayTime(r.generated_at_sim)} (sim)<br />
              <Pill tone="warn">Simulated demo data</Pill>
            </div>
          </header>

          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Verified generation" value={fmtKwh(r.generation.verified_kwh)} sub={`of ${fmtKwh(r.generation.reported_kwh)} reported`} tone="good" />
            <Stat label="Records verified" value={`${r.integrity.verified_pct.toFixed(r.integrity.verified_pct === 100 ? 0 : 3)}%`} sub={`${r.integrity.verified_records.toLocaleString()} / ${r.integrity.records.toLocaleString()} signed readings`} tone={r.integrity.verified_pct === 100 ? "good" : "bad"} />
            <Stat label="Avoided CO₂ (illustrative)" value={`${r.carbon.avoided_t_co2.toFixed(1)} t`} sub={`${r.carbon.kg_co2_per_kwh} kg/kWh · ${r.carbon.baseline} baseline`} />
            <Stat label="Open critical findings" value={String(r.security.open_critical_findings)} sub={r.security.risk_score === null ? "site not scanned yet" : `risk score ${r.security.risk_score}/100`} tone={r.security.open_critical_findings ? "bad" : undefined} />
          </section>

          {r.generation.flagged_kwh > 0 ? (
            <section className="rounded-xl border-2 border-accent bg-accent-50 p-4">
              <h3 className="font-semibold text-accent-700">Fraud prevented: {fmtKwh(r.generation.flagged_kwh)} excluded from this report</h3>
              <p className="mt-1 text-sm text-ink">
                Without verification this report would have claimed <strong>{fmtKwh(r.generation.reported_kwh)}</strong>.
                {r.generation.spoofed_kwh > 0 && <> {fmtKwh(r.generation.spoofed_kwh)} came from physically impossible readings (spoofed or inflated at the source).</>}
                {r.generation.tampered_kwh > 0 && <> {fmtKwh(r.generation.tampered_kwh)} came from database records that no longer match their signatures.</>}
              </p>
            </section>
          ) : (
            <section className="rounded-xl border border-brand/20 bg-brand-50 p-4 text-sm text-brand">
              ✓ No spoofed, inflated or tampered generation detected in this period.
            </section>
          )}

          <Card title="Daily energy: reported vs verified">
            <div className="p-3"><DailyEnergyChart data={r.generation.daily} /></div>
            <table className="w-full border-t border-line text-xs">
              <thead className="text-left text-ink-muted"><tr><th className="px-4 py-1.5">Date</th><th className="px-4 py-1.5 text-right">Reported</th><th className="px-4 py-1.5 text-right">Verified</th></tr></thead>
              <tbody>
                {r.generation.daily.map((d) => (
                  <tr key={d.date} className="border-t border-line"><td className="px-4 py-1.5">{d.date}</td><td className="px-4 py-1.5 text-right tabular-nums">{fmtKwh(d.reported_kwh)}</td><td className="px-4 py-1.5 text-right tabular-nums">{fmtKwh(d.verified_kwh)}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Security operations">
              <dl className="grid grid-cols-2 gap-3 p-4 text-sm">
                <div><dt className="text-ink-muted">Alerts raised</dt><dd className="text-lg font-semibold">{r.security.alerts_total}</dd></div>
                <div><dt className="text-ink-muted">Still open</dt><dd className="text-lg font-semibold">{r.security.open_alerts}</dd></div>
                <div><dt className="text-ink-muted">Mean time to detect</dt><dd className="text-lg font-semibold">{fmtSeconds(r.security.avg_mttd_seconds)}</dd></div>
                <div><dt className="text-ink-muted">Mean time to resolve</dt><dd className="text-lg font-semibold">{fmtSeconds(r.security.avg_mttr_seconds)}</dd></div>
              </dl>
            </Card>
            <Card title="Chain heads (audit anchors)">
              <ul className="divide-y divide-line text-xs">
                {r.integrity.chain_heads.map((c) => (
                  <li key={c.device_id} className="flex items-center justify-between gap-2 px-4 py-2">
                    <span className="font-medium">{c.device_id}</span>
                    <span className="truncate font-mono text-ink-muted">{shortHash(c.chain_head, 24)}</span>
                    {c.ok ? <Pill tone="good">✓</Pill> : <Pill tone="bad">✕</Pill>}
                  </li>
                ))}
              </ul>
              <p className="border-t border-line px-4 py-2 text-[11px] text-ink-muted">Publishing these daily to a public timestamp service would make the history independently auditable.</p>
            </Card>
          </div>

          <footer className="border-t border-line pt-3 text-[11px] leading-relaxed text-ink-muted">
            ⚠ {r.carbon.label}. {r.carbon.disclaimer} Figures are generated by a simulator for demonstration and do not describe a real site.
          </footer>
        </article>
      )}
    </>
  );
}
