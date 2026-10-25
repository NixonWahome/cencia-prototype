import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useLive } from "../api/live";
import type { Alert, Explanation } from "../api/types";
import { SITE_SHORT, dayTime, fmtSeconds } from "../lib/format";
import { Button, Pill, SeverityBadge } from "./ui";

const ACTION_LABEL: Record<string, string> = {
  block_ip: "Block source IP",
  isolate: "Isolate device",
  restore_record: "Restore from signed payload",
};

const HIDDEN_EVIDENCE = new Set(["explanation", "fields", "reasons", "params", "command_id", "telemetry_id"]);

function ExplanationBars({ items }: { items: Explanation[] }) {
  const max = Math.max(...items.map((e) => Math.abs(e.z)), 1);
  return (
    <ul className="space-y-2">
      {items.map((e) => (
        <li key={e.feature}>
          <div className="flex justify-between text-xs">
            <span className="text-ink">{e.text}</span>
            <span className="tabular-nums text-ink-muted">{e.z > 0 ? "+" : ""}{e.z}σ</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-accent" style={{ width: `${(Math.abs(e.z) / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function fmtEvidence(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3).replace(/\.?0+$/, "");
  if (typeof v === "string") return v.replace("T", " ");
  return JSON.stringify(v);
}

export function AlertDrawer({ alert, onClose, onChanged }: { alert: Alert; onClose: () => void; onChanged: (a?: Alert) => void }) {
  const { pushToast } = useLive();
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (key: string, fn: () => Promise<unknown>, success: string) => {
    setBusy(key);
    try {
      await fn();
      pushToast({ tone: "good", title: success });
      onChanged();
    } catch (e) {
      pushToast({ tone: "critical", title: "Action failed", body: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const ev = alert.evidence ?? {};
  const fields = (ev.fields ?? []) as { field: string; signed: number; stored: number }[];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={alert.title}>
      <button className="absolute inset-0 bg-ink/30" onClick={onClose} aria-label="Close" />
      <aside className="relative h-full w-full max-w-lg overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 flex items-start justify-between gap-3 border-b border-line bg-white px-5 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={alert.severity} />
              <Pill tone="brand">{alert.rule_id} · {alert.rule_name}</Pill>
              <Pill tone={alert.status === "resolved" ? "good" : alert.status === "acknowledged" ? "warn" : "bad"}>{alert.status}</Pill>
            </div>
            <h2 className="mt-2 text-lg font-semibold leading-snug">{alert.title}</h2>
            <div className="mt-1 text-xs text-ink-muted">
              <Link className="hover:underline" to={`/sites/${alert.site_id}`}>{SITE_SHORT[alert.site_id]}</Link>
              {alert.device_id && ` · ${alert.device_id}`} · detected {dayTime(alert.detected_at)}
            </div>
          </div>
          <button onClick={onClose} className="text-xl text-ink-faint hover:text-ink" aria-label="Close drawer">✕</button>
        </header>

        <div className="space-y-5 px-5 py-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-canvas p-3">
              <div className="text-xs text-ink-muted">Time to detect</div>
              <div className="text-xl font-semibold tabular-nums text-brand">{fmtSeconds(alert.mttd_seconds)}</div>
              {alert.mttd_sim_seconds !== null && <div className="text-[11px] text-ink-faint">{fmtSeconds(alert.mttd_sim_seconds)} sim time</div>}
              {alert.mttd_seconds === null && <div className="text-[11px] text-ink-faint">no linked attack</div>}
            </div>
            <div className="rounded-lg bg-canvas p-3">
              <div className="text-xs text-ink-muted">Time to resolve</div>
              <div className="text-xl font-semibold tabular-nums text-ink">{fmtSeconds(alert.mttr_seconds)}</div>
              {alert.mttr_seconds === null && <div className="text-[11px] text-ink-faint">still open</div>}
            </div>
          </div>

          <p className="text-sm leading-relaxed text-ink">{alert.description}</p>

          {fields.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-sev-critical/30">
              <table className="w-full text-sm">
                <thead className="bg-red-50 text-xs text-sev-critical">
                  <tr><th className="px-3 py-2 text-left">Field</th><th className="px-3 py-2 text-right">Signed by device</th><th className="px-3 py-2 text-right">Stored in DB</th></tr>
                </thead>
                <tbody>
                  {fields.map((f) => (
                    <tr key={f.field} className="border-t border-line">
                      <td className="px-3 py-2 font-mono text-xs">{f.field}</td>
                      <td className="px-3 py-2 text-right font-semibold tabular-nums text-brand">{fmtEvidence(f.signed)}</td>
                      <td className="px-3 py-2 text-right font-semibold tabular-nums text-sev-critical">{fmtEvidence(f.stored)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {Array.isArray(ev.explanation) && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Why the model flagged it · score {alert.ml_score} (threshold {ev.threshold})
              </h3>
              <ExplanationBars items={ev.explanation as Explanation[]} />
            </div>
          )}

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">Evidence</h3>
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
              {Object.entries(ev)
                .filter(([k]) => !HIDDEN_EVIDENCE.has(k))
                .map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-ink-muted">{k.replace(/_/g, " ")}</dt>
                    <dd className="break-all font-medium tabular-nums">{fmtEvidence(v)}</dd>
                  </div>
                ))}
            </dl>
            {Array.isArray(ev.reasons) && (
              <ul className="mt-2 list-disc pl-5 text-sm text-sev-critical">
                {(ev.reasons as string[]).map((r) => <li key={r}>{r}</li>)}
              </ul>
            )}
          </div>

          {alert.mitre_technique && (
            <div className="text-sm">
              <span className="text-ink-muted">MITRE ATT&CK for ICS: </span>
              <span className="font-medium">{alert.mitre_technique}</span>
            </div>
          )}

          <div className="rounded-lg border border-accent/30 bg-accent-50 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-accent-700">Recommended action</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink">{alert.recommended_action}</p>
          </div>

          {alert.status !== "resolved" && (
            <div className="flex flex-wrap gap-2 border-t border-line pt-4">
              {(alert.actions ?? []).map((a) => (
                <Button
                  key={a}
                  variant="primary"
                  disabled={busy !== null}
                  onClick={() => run(a, () => api.post(`/api/alerts/${alert.id}/actions/${a}`), `${ACTION_LABEL[a]}: done`)}
                >
                  {busy === a ? "Working…" : ACTION_LABEL[a]}
                </Button>
              ))}
              {alert.status === "open" && (
                <Button disabled={busy !== null} onClick={() => run("ack", () => api.patch(`/api/alerts/${alert.id}`, { status: "acknowledged" }), "Acknowledged")}>
                  Acknowledge
                </Button>
              )}
              <Button variant="ghost" disabled={busy !== null} onClick={() => run("resolve", () => api.patch(`/api/alerts/${alert.id}`, { status: "resolved" }), "Resolved")}>
                Mark resolved
              </Button>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
