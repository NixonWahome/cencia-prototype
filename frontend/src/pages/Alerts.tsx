import { useSearchParams } from "react-router-dom";
import { useApi } from "../api/live";
import type { Alert } from "../api/types";
import { AlertDrawer } from "../components/AlertDrawer";
import { Card, Empty, Loading, PageHeader, Pill, SeverityBadge, cx } from "../components/ui";
import { RULE_LABEL, SITE_SHORT, dayTime, fmtSeconds } from "../lib/format";

const FILTERS = {
  site_id: { label: "Site", options: Object.entries(SITE_SHORT) },
  severity: { label: "Severity", options: ["critical", "high", "medium"].map((s) => [s, s]) },
  status: { label: "Status", options: [["active", "Active"], ["open", "Open"], ["acknowledged", "Acknowledged"], ["resolved", "Resolved"]] },
  rule_id: { label: "Rule", options: Object.entries(RULE_LABEL).map(([k, v]) => [k, `${k} ${v}`]) },
} as const;

export default function Alerts() {
  const [params, setParams] = useSearchParams();
  const query = new URLSearchParams();
  for (const key of Object.keys(FILTERS)) {
    const v = params.get(key);
    if (v) query.set(key, v);
  }
  const { data: alerts, reload } = useApi<Alert[]>(`/api/alerts?${query}`, ["alerts"]);
  const selectedId = Number(params.get("id")) || null;
  const { data: selected, reload: reloadSelected } = useApi<Alert>(selectedId ? `/api/alerts/${selectedId}` : null, ["alerts"]);

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader title="Alerts" subtitle="Rules R1–R7 plus the ML anomaly layer. Click an alert for evidence, explanation and response." />

      <div className="mb-4 flex flex-wrap gap-2">
        {Object.entries(FILTERS).map(([key, f]) => (
          <select
            key={key}
            value={params.get(key) ?? ""}
            onChange={(e) => set(key, e.target.value || null)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm capitalize"
            aria-label={f.label}
          >
            <option value="">{f.label}: all</option>
            {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ))}
      </div>

      <Card>
        {!alerts ? (
          <Loading />
        ) : alerts.length === 0 ? (
          <Empty>No alerts match. Fire an attack from the Demo panel to see detection in action.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="text-left text-xs text-ink-muted">
                <tr className="border-b border-line">
                  <th className="px-4 py-2">Severity</th><th className="px-4 py-2">Alert</th><th className="px-4 py-2">Rule</th>
                  <th className="px-4 py-2">Site · device</th><th className="px-4 py-2">Detected</th>
                  <th className="px-4 py-2 text-right">MTTD</th><th className="px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr
                    key={a.id}
                    onClick={() => set("id", String(a.id))}
                    className={cx("cursor-pointer border-b border-line last:border-0 hover:bg-canvas", selectedId === a.id && "bg-accent-50")}
                  >
                    <td className="px-4 py-2.5"><SeverityBadge severity={a.severity} /></td>
                    <td className="px-4 py-2.5 font-medium">
                      {a.title}
                      {(a.evidence?.occurrences ?? 1) > 1 && <span className="ml-1 text-xs text-ink-muted">×{a.evidence.occurrences}</span>}
                    </td>
                    <td className="px-4 py-2.5 text-ink-muted">{a.rule_id}</td>
                    <td className="px-4 py-2.5 text-ink-muted">{SITE_SHORT[a.site_id]} · {a.device_id}</td>
                    <td className="px-4 py-2.5 tabular-nums text-ink-muted">{dayTime(a.detected_at)}</td>
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-brand">{fmtSeconds(a.mttd_seconds)}</td>
                    <td className="px-4 py-2.5">
                      <Pill tone={a.status === "resolved" ? "good" : a.status === "acknowledged" ? "warn" : "bad"}>{a.status}</Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected && (
        <AlertDrawer
          alert={selected}
          onClose={() => set("id", null)}
          onChanged={() => {
            reload();
            reloadSelected();
          }}
        />
      )}
    </>
  );
}
