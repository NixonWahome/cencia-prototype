import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi, useLive } from "../api/live";
import type { Finding, Scan, Severity, SiteSecurity } from "../api/types";
import { RiskGauge } from "../components/RiskGauge";
import { Button, Card, Empty, Loading, PageHeader, Pill, ProgressBar, SeverityBadge, SiteTabs } from "../components/ui";

const ORDER: Severity[] = ["critical", "high", "medium", "low"];

export default function Vulnerabilities() {
  const [params, setParams] = useSearchParams();
  const siteId = params.get("site") ?? "naivasha";
  const { pushToast } = useLive();
  const { data, reload } = useApi<SiteSecurity>(`/api/sites/${siteId}/security`, ["scans"]);
  const running = data?.running_scan;
  const { data: live } = useApi<Scan>(running ? `/api/scans/${running.id}` : null, ["scans"]);
  const [busy, setBusy] = useState<number | "scan" | null>(null);

  const startScan = async () => {
    setBusy("scan");
    try {
      await api.post("/api/scans", { site_id: siteId });
      reload();
    } catch (e) {
      pushToast({ tone: "critical", title: "Scan failed", body: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const remediate = async (f: Finding) => {
    setBusy(f.id);
    try {
      const res = await api.post<{ risk_score: number }>(`/api/findings/${f.id}/remediate`);
      pushToast({ tone: "good", title: `Remediated: ${f.title}`, body: `${f.device_id} · risk score now ${res.risk_score}` });
      reload();
    } catch (e) {
      pushToast({ tone: "critical", title: "Remediation failed", body: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const scan = data?.latest_scan;
  const findings = scan?.findings ?? [];
  const open = findings.filter((f) => f.status === "open");
  const grouped = ORDER.map((sev) => ({ sev, items: findings.filter((f) => f.severity === sev) })).filter((g) => g.items.length);

  return (
    <>
      <PageHeader
        title="Vulnerabilities"
        subtitle="Simulated scan of each device's configuration. No packets are sent; nothing real is scanned."
        actions={<SiteTabs value={siteId} onChange={(id) => setParams({ site: id }, { replace: true })} />}
      />
      {!data ? (
        <Loading />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="Site risk score" className="lg:row-span-2">
            <div className="flex flex-col items-center gap-4 p-5">
              <RiskGauge score={running ? null : scan?.risk_score ?? null} />
              <div className="grid w-full grid-cols-3 gap-2 text-center text-xs">
                {(["critical", "high", "medium"] as Severity[]).map((s) => (
                  <div key={s} className="rounded-lg bg-canvas p-2">
                    <div className="text-lg font-semibold tabular-nums">{open.filter((f) => f.severity === s).length}</div>
                    <div className="capitalize text-ink-muted">{s}</div>
                  </div>
                ))}
              </div>
              <p className="text-center text-xs text-ink-muted">Critical 25 · High 15 · Medium 7 per open finding, capped at 100.</p>
              {running ? (
                <div className="w-full space-y-2">
                  <ProgressBar value={live?.progress ?? running.progress} tone="accent" />
                  <div className="text-center text-xs text-ink-muted">Scanning {live?.current_device ?? running.current_device ?? "…"}</div>
                </div>
              ) : (
                <Button variant="primary" size="lg" className="w-full" onClick={startScan} disabled={busy !== null}>
                  {scan ? "Rescan site" : "Run scan"}
                </Button>
              )}
            </div>
          </Card>

          <Card title={running ? "Findings so far" : scan ? `Findings · scan #${scan.id}` : "Findings"} className="lg:col-span-2">
            {running && live?.findings?.length ? (
              <ul className="divide-y divide-line">
                {live.findings.map((f) => (
                  <li key={f.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                    <SeverityBadge severity={f.severity} /> <span className="font-medium">{f.title}</span> <span className="text-ink-muted">· {f.device_id}</span>
                  </li>
                ))}
              </ul>
            ) : !scan ? (
              <Empty>No scan yet. Run one to find default credentials, open Modbus, Telnet and more.</Empty>
            ) : grouped.length === 0 ? (
              <Empty>✓ No findings: this site is clean.</Empty>
            ) : (
              <div className="divide-y divide-line">
                {grouped.map((g) => (
                  <div key={g.sev} className="px-4 py-3">
                    <div className="mb-2 flex items-center gap-2"><SeverityBadge severity={g.sev} /> <span className="text-xs text-ink-muted">{g.items.length} finding(s)</span></div>
                    <ul className="space-y-2">
                      {g.items.map((f) => (
                        <li key={f.id} className="flex flex-col gap-2 rounded-lg border border-line p-3 sm:flex-row sm:items-center">
                          <div className="flex-1">
                            <div className="text-sm font-semibold">
                              {f.title} <span className="font-normal text-ink-muted">· {f.device_id}</span>
                            </div>
                            <div className="text-xs text-ink-muted">{f.evidence}</div>
                            <div className="mt-1 text-xs text-ink"><span className="font-medium text-accent-700">Fix: </span>{f.remediation}</div>
                          </div>
                          {f.status === "open" ? (
                            <Button size="sm" variant="primary" disabled={busy !== null} onClick={() => remediate(f)}>
                              {busy === f.id ? "Applying…" : "Mark remediated"}
                            </Button>
                          ) : (
                            <Pill tone="good">✓ {f.status}</Pill>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Device inventory" className="lg:col-span-2">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-sm">
                <thead className="text-left text-xs text-ink-muted">
                  <tr className="border-b border-line"><th className="px-4 py-2">Device</th><th className="px-4 py-2">Open ports</th><th className="px-4 py-2">Auth</th><th className="px-4 py-2">TLS</th><th className="px-4 py-2">Firmware</th></tr>
                </thead>
                <tbody>
                  {data.devices.map((d) => (
                    <tr key={d.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-2 font-medium">{d.id}<div className="text-xs font-normal text-ink-muted">{d.ip}</div></td>
                      <td className="px-4 py-2 font-mono text-xs">{d.open_ports.join(", ")}</td>
                      <td className="px-4 py-2">{d.default_credentials ? <Pill tone="bad">default creds</Pill> : d.protocol_auth ? <Pill tone="good">✓</Pill> : <Pill tone="warn">none</Pill>}</td>
                      <td className="px-4 py-2">{d.tls_enabled ? <Pill tone="good">✓</Pill> : <Pill tone="warn">off</Pill>}</td>
                      <td className="px-4 py-2 text-xs">{d.firmware_version}{d.firmware_version !== d.latest_firmware && <span className="text-sev-medium"> (latest {d.latest_firmware})</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
