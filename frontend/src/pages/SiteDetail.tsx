import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../api/live";
import type { Alert, Command, Reading, SiteDetail as SiteDetailData, SitePoint } from "../api/types";
import { AlertDrawer } from "../components/AlertDrawer";
import { MetricChart, PowerChart } from "../components/charts";
import { Card, Empty, Loading, PageHeader, Pill, SeverityBadge, StatusPill, cx } from "../components/ui";
import { fmtKw, hhmm } from "../lib/format";

export default function SiteDetail() {
  const { siteId = "kibwezi" } = useParams();
  const [deviceId, setDeviceId] = useState<string>("");
  const [writesOnly, setWritesOnly] = useState(false);
  const [openAlert, setOpenAlert] = useState<Alert | null>(null);

  const { data: site } = useApi<SiteDetailData>(`/api/sites/${siteId}`, ["tick", "alerts"]);
  const telemetryPath = deviceId
    ? `/api/sites/${siteId}/telemetry?view=device&device_id=${deviceId}`
    : `/api/sites/${siteId}/telemetry`;
  const { data: telemetry } = useApi<{ points?: SitePoint[]; readings?: Reading[] }>(telemetryPath, ["tick"]);
  const { data: commands } = useApi<Command[]>(`/api/sites/${siteId}/commands?limit=40${writesOnly ? "&writes_only=true" : ""}`, ["tick", "attacks"]);
  const { data: alerts, reload } = useApi<Alert[]>(`/api/alerts?site_id=${siteId}&limit=20`, ["alerts"]);

  if (!site) return <Loading />;
  const series = (telemetry?.points ?? telemetry?.readings ?? []) as (SitePoint | Reading)[];
  const inverters = site.devices.filter((d) => d.signs_telemetry);

  return (
    <>
      <PageHeader
        title={site.name}
        subtitle={<>{site.site_type} · {site.location} · <StatusPill status={site.status} /></>}
        actions={
          <select
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
            aria-label="Chart scope"
          >
            <option value="">All inverters (site total)</option>
            {inverters.map((d) => <option key={d.id} value={d.id}>{d.id}</option>)}
          </select>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={`Power: reported vs physics-expected · ${deviceId || "site total"} · last 24 h`}>
          <div className="p-2 sm:p-4">
            <PowerChart data={series} />
            <p className="px-2 text-xs text-ink-muted">
              Expected power comes from measured irradiance, temperature and capacity. Reported power above the dashed line is physically implausible.
            </p>
          </div>
        </Card>
        <Card title="Irradiance (W/m²)">
          <div className="p-2 sm:p-4"><MetricChart data={series} dataKey="irradiance_wm2" unit="W/m²" area height={230} /></div>
        </Card>
        <Card title="AC voltage (V)">
          <div className="p-2"><MetricChart data={series} dataKey="ac_voltage_v" unit="V" /></div>
        </Card>
        <Card title="Grid frequency (Hz), alarm band 49.5–50.5">
          <div className="p-2"><MetricChart data={series} dataKey="frequency_hz" unit="Hz" domain={[49.4, 50.6]} refLines={[49.5, 50.5]} /></div>
        </Card>
        <Card title="Inverter temperature (°C)">
          <div className="p-2"><MetricChart data={series} dataKey="temperature_c" unit="°C" /></div>
        </Card>
      </div>

      <Card className="mt-4" title="Devices">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left text-xs text-ink-muted">
              <tr className="border-b border-line">
                <th className="px-4 py-2">Device</th><th className="px-4 py-2">Type</th><th className="px-4 py-2">Status</th>
                <th className="px-4 py-2 text-right">Power</th><th className="px-4 py-2">Firmware</th><th className="px-4 py-2 text-right">Integrity</th>
              </tr>
            </thead>
            <tbody>
              {site.devices.map((d) => (
                <tr key={d.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 font-medium">{d.id}<div className="text-xs font-normal text-ink-muted">{d.vendor} {d.model} · {d.ip}</div></td>
                  <td className="px-4 py-2 capitalize text-ink-muted">{d.kind.replace(/_/g, " ")}</td>
                  <td className="px-4 py-2">
                    {d.quarantined ? <Pill tone="warn">Isolated</Pill>
                      : !d.signs_telemetry ? <Pill>Online</Pill>
                      : !d.online ? <Pill tone="bad">✕ Silent</Pill>
                      : d.latest?.status === "shutdown" ? <Pill tone="bad">Shut down</Pill>
                      : d.latest?.status === "limited" ? <Pill tone="warn">Limited</Pill>
                      : <Pill tone="good">{d.latest?.status ?? "online"}</Pill>}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{d.latest ? fmtKw(d.latest.ac_power_kw) : "—"}</td>
                  <td className="px-4 py-2">
                    <span className={cx(d.firmware_version !== d.latest_firmware && "text-sev-medium")}>{d.firmware_version}</span>
                    {d.firmware_version !== d.latest_firmware && <span className="text-xs text-ink-muted"> → {d.latest_firmware}</span>}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {d.integrity ? <span className={d.integrity.ok ? "text-brand" : "font-semibold text-sev-critical"}>{d.integrity.integrity_pct.toFixed(d.integrity.ok ? 0 : 2)}%</span> : <span className="text-ink-faint">n/a</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card
          title="Command log"
          action={
            <label className="flex items-center gap-2 text-xs text-ink-muted">
              <input type="checkbox" checked={writesOnly} onChange={(e) => setWritesOnly(e.target.checked)} /> writes only
            </label>
          }
        >
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white text-left text-ink-muted">
                <tr className="border-b border-line"><th className="px-3 py-2">Time</th><th className="px-3 py-2">Command</th><th className="px-3 py-2">Device</th><th className="px-3 py-2">Source</th></tr>
              </thead>
              <tbody>
                {(commands ?? []).map((c) => (
                  <tr key={c.id} className={cx("border-b border-line last:border-0", c.attack_id !== null && "bg-red-50")}>
                    <td className="px-3 py-1.5 tabular-nums text-ink-muted">{hhmm(c.ts)}</td>
                    <td className={cx("px-3 py-1.5 font-mono", c.is_write ? "font-semibold" : "text-ink-muted")}>
                      {c.command}{c.params?.blocked ? " (blocked)" : ""}
                    </td>
                    <td className="px-3 py-1.5">{c.device_id}</td>
                    <td className={cx("px-3 py-1.5 font-mono", c.attack_id !== null && "font-semibold text-sev-critical")}>{c.source_ip}<span className="font-sans text-ink-faint"> · {c.user}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Site alerts" action={<Link to="/alerts" className="text-sm font-medium text-brand hover:underline">All →</Link>}>
          {alerts && alerts.length ? (
            <ul className="max-h-96 divide-y divide-line overflow-auto">
              {alerts.map((a) => (
                <li key={a.id}>
                  <button onClick={() => setOpenAlert(a)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-canvas">
                    <SeverityBadge severity={a.severity} />
                    <span className={cx("flex-1 truncate text-sm", a.status === "resolved" && "text-ink-faint line-through")}>{a.title}</span>
                    <span className="text-xs tabular-nums text-ink-muted">{hhmm(a.detected_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No alerts for this site.</Empty>
          )}
        </Card>
      </div>
      {openAlert && (
        <AlertDrawer
          alert={alerts?.find((a) => a.id === openAlert.id) ?? openAlert}
          onClose={() => setOpenAlert(null)}
          onChanged={() => reload()}
        />
      )}
    </>
  );
}
