import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi, useLive } from "../api/live";
import type { Alert, AttackRun, AttackSpec, SimStatus } from "../api/types";
import { Button, Card, PageHeader, Pill, SeverityBadge, cx } from "../components/ui";
import { SITE_SHORT, fmtSeconds, hhmm } from "../lib/format";

const ICON: Record<string, string> = {
  spoof_night_generation: "🌙",
  inflate_output: "📈",
  unauthorized_shutdown: "⛔",
  command_flood: "🌊",
  tamper_stored_record: "✎",
  device_offline: "📡",
};

// The order follows the demo script.
const SCRIPT_ORDER = ["unauthorized_shutdown", "inflate_output", "tamper_stored_record", "spoof_night_generation", "command_flood", "device_offline"];

export default function Demo() {
  const { sim, pushToast } = useLive();
  const { data, reload } = useApi<{ catalog: AttackSpec[]; active: AttackRun[]; blocklist: string[] }>("/api/demo/attacks", ["attacks", "alerts"]);
  const { data: alerts } = useApi<Alert[]>("/api/alerts?limit=8", ["alerts"]);
  const [busy, setBusy] = useState<string | null>(null);

  const call = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await fn();
      reload();
    } catch (e) {
      pushToast({ tone: "critical", title: "Request failed", body: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const catalog = [...(data?.catalog ?? [])].sort((a, b) => SCRIPT_ORDER.indexOf(a.type) - SCRIPT_ORDER.indexOf(b.type));
  const active = new Set((data?.active ?? []).map((a) => a.type));

  return (
    <>
      <PageHeader
        title="Demo control panel"
        subtitle="Open this page on a phone to fire attacks while the dashboard is on the projector."
        actions={
          <Button variant="danger" size="lg" disabled={busy !== null} onClick={() => call("reset", () => api.post("/api/demo/reset"))}>
            {busy === "reset" ? "Resetting…" : "↺ Reset demo"}
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {catalog.map((a) => (
          <div key={a.type} className={cx("flex flex-col rounded-xl border bg-white p-4 shadow-card", active.has(a.type) ? "border-sev-critical ring-2 ring-sev-critical/20" : "border-line")}>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-base font-semibold"><span aria-hidden className="mr-1.5">{ICON[a.type]}</span>{a.label}</h3>
              {active.has(a.type) && <Pill tone="bad">active</Pill>}
            </div>
            <p className="mt-1 flex-1 text-sm text-ink-muted">{a.story}</p>
            <div className="mt-2 flex flex-wrap gap-1 text-xs">
              <Pill>{SITE_SHORT[a.site_id]} · {a.device_id}</Pill>
              {a.expects.map((r) => <Pill key={r} tone="brand">→ {r}</Pill>)}
            </div>
            <Button
              className="mt-3 w-full"
              variant="accent"
              size="lg"
              disabled={busy !== null}
              onClick={() =>
                call(a.type, async () => {
                  const res = await api.post<AttackRun>(`/api/demo/attack/${a.type}`);
                  if (res.jumped_to) pushToast({ tone: "info", title: `Clock jumped to ${hhmm(res.jumped_to)} EAT`, body: "Gap backfilled with signed telemetry." });
                })
              }
            >
              {busy === a.type ? "Launching…" : "Launch attack"}
            </Button>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Simulation clock">
          <div className="space-y-4 p-4">
            <div className="text-3xl font-semibold tabular-nums">{sim ? `${hhmm(sim.sim_time)} EAT` : "—"} <span className="text-base font-normal text-ink-muted">at {sim?.speed ?? "—"}×</span></div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">Jump forward to</div>
              <div className="flex flex-wrap gap-2">
                {[["01:00", 1], ["06:30", 6.5], ["10:00", 10], ["13:00", 13], ["17:30", 17.5]].map(([label, hour]) => (
                  <Button key={label} disabled={busy !== null} onClick={() => call(`jump${hour}`, () => api.post<SimStatus>("/api/demo/jump", { hour }))}>
                    {busy === `jump${hour}` ? "…" : label}
                  </Button>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">Speed</div>
              <div className="flex flex-wrap gap-2">
                {[30, 60, 120, 300].map((s) => (
                  <Button key={s} variant={sim?.speed === s ? "primary" : "secondary"} disabled={busy !== null} onClick={() => call(`speed${s}`, () => api.post("/api/demo/speed", { multiplier: s }))}>
                    {s}×
                  </Button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
              <Button size="sm" disabled={busy !== null} onClick={() => call("retrain", async () => {
                await api.post("/api/demo/retrain");
                pushToast({ tone: "good", title: "Anomaly models retrained", body: "Known attack windows excluded." });
              })}>
                Retrain ML models
              </Button>
              {data?.blocklist.length ? <span className="text-xs text-ink-muted">Blocked: {data.blocklist.map((ip) => <code key={ip} className="mr-1">{ip}</code>)}</span> : null}
            </div>
          </div>
        </Card>

        <Card title="Live detections" action={<Link to="/alerts" className="text-sm font-medium text-brand hover:underline">Alerts →</Link>}>
          {alerts?.length ? (
            <ul className="divide-y divide-line">
              {alerts.map((a) => (
                <li key={a.id}>
                  <Link to={`/alerts?id=${a.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-canvas">
                    <SeverityBadge severity={a.severity} />
                    <span className={cx("flex-1 truncate text-sm", a.status === "resolved" && "text-ink-faint line-through")}>{a.title}</span>
                    <span className="text-xs font-semibold tabular-nums text-brand">{fmtSeconds(a.mttd_seconds)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4 py-8 text-center text-sm text-ink-muted">No detections yet. Launch an attack.</div>
          )}
        </Card>
      </div>

      <Card className="mt-4" title="Demo script (~5 min)">
        <ol className="list-decimal space-y-1.5 py-4 pl-9 pr-4 text-sm">
          <li><Link className="font-medium text-brand hover:underline" to="/">Overview</Link>: 3 sites live, all green.</li>
          <li><Link className="font-medium text-brand hover:underline" to="/vulnerabilities?site=naivasha">Vulnerabilities</Link>: scan Naivasha → default creds + open Modbus → remediate → risk score drops.</li>
          <li>Launch <strong>Unauthorized shutdown</strong> → critical alert in milliseconds, power drops to 0 → <em>Block source IP</em> (MTTR).</li>
          <li>Launch <strong>Inflate output</strong> → <Link className="text-brand hover:underline" to="/sites/kibwezi">Kibwezi</Link>, pick KIB-INV-03: reported line leaves the expected line. "Carbon-credit fraud, validly signed, caught by physics."</li>
          <li>Launch <strong>Tamper stored record</strong> → <Link className="text-brand hover:underline" to="/integrity?site=kibwezi">Integrity</Link>: red block, signed vs stored.</li>
          <li><Link className="font-medium text-brand hover:underline" to="/report?site=kibwezi">Investor report</Link>: verified kWh, fraud prevented, why investors care.</li>
          <li>Reset.</li>
        </ol>
      </Card>
    </>
  );
}
