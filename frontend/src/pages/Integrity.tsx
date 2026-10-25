import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi, useLive } from "../api/live";
import type { Alert, BrokenRecord, ChainRecords, DeviceIntegrity } from "../api/types";
import { ChainBlocks } from "../components/ChainBlocks";
import { Button, Card, Loading, PageHeader, Pill, SiteTabs, cx } from "../components/ui";
import { dayTime, shortHash } from "../lib/format";

function BrokenPanel({ record, alert, onRestored }: { record: BrokenRecord; alert?: Alert; onRestored: () => void }) {
  const { pushToast } = useLive();
  const columns = record.problems.find((p) => p.check === "columns");
  return (
    <div className="rounded-xl border-2 border-sev-critical bg-red-50/50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="bad">✕ Record #{record.seq} failed verification</Pill>
        <span className="text-xs text-ink-muted">{dayTime(record.ts)}</span>
      </div>
      {columns?.fields?.length ? (
        <div className="mt-3 grid grid-cols-2 gap-3">
          {columns.fields.map((f) => (
            <div key={f.field} className="contents">
              <div className="rounded-lg bg-white p-3 ring-1 ring-brand/30">
                <div className="text-xs text-ink-muted">Signed by device ({f.field})</div>
                <div className="text-2xl font-semibold tabular-nums text-brand">{String(f.signed)}</div>
              </div>
              <div className="rounded-lg bg-white p-3 ring-1 ring-sev-critical/40">
                <div className="text-xs text-ink-muted">Stored in database</div>
                <div className="text-2xl font-semibold tabular-nums text-sev-critical">{String(f.stored)}</div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <ul className="mt-3 space-y-1 text-sm">
        {record.problems.map((p) => (
          <li key={p.check}><span className="font-mono text-xs font-semibold uppercase text-sev-critical">{p.check}</span> {p.message}</li>
        ))}
      </ul>
      {alert && alert.status !== "resolved" && (
        <Button
          className="mt-3"
          variant="primary"
          onClick={async () => {
            await api.post(`/api/alerts/${alert.id}/actions/restore_record`);
            pushToast({ tone: "good", title: `Record #${record.seq} restored from the signed payload` });
            onRestored();
          }}
        >
          Restore from signed payload
        </Button>
      )}
    </div>
  );
}

export default function Integrity() {
  const [params, setParams] = useSearchParams();
  const siteId = params.get("site") ?? "kibwezi";
  const { pushToast } = useLive();
  const { data: status, reload } = useApi<{ summary: { integrity_pct: number; ok: boolean; total: number; verified: number }; devices: DeviceIntegrity[] }>(
    `/api/integrity/status?site_id=${siteId}`,
    ["tick", "integrity"],
  );
  const firstBroken = status?.devices.find((d) => !d.ok)?.device_id;
  const [picked, setPicked] = useState<string | null>(null);
  const deviceId = picked && status?.devices.some((d) => d.device_id === picked) ? picked : firstBroken ?? status?.devices[0]?.device_id;
  const { data: chain, reload: reloadChain } = useApi<ChainRecords>(deviceId ? `/api/integrity/records/${deviceId}?limit=12` : null, ["tick", "integrity"]);
  const { data: r7 } = useApi<Alert[]>(`/api/alerts?rule_id=R7&status=active&site_id=${siteId}`, ["alerts"]);
  const [verifying, setVerifying] = useState(false);

  const verify = async () => {
    setVerifying(true);
    try {
      const res = await api.post<{ ok: boolean; total: number; integrity_pct: number }>(`/api/integrity/verify/site/${siteId}`);
      pushToast({
        tone: res.ok ? "good" : "critical",
        title: res.ok ? `All ${res.total.toLocaleString()} records verified` : `Chain broken: ${res.integrity_pct.toFixed(3)}% verified`,
      });
      reload();
      reloadChain();
    } finally {
      setVerifying(false);
    }
  };

  const broken = chain?.broken_records ?? [];

  return (
    <>
      <PageHeader
        title="Telemetry integrity"
        subtitle="Every reading is Ed25519-signed at the edge and hash-chained per device. Edit one value and the chain shows it."
        actions={
          <>
            <SiteTabs value={siteId} onChange={(id) => { setPicked(null); setParams({ site: id }, { replace: true }); }} />
            <Button variant="primary" onClick={verify} disabled={verifying}>{verifying ? "Verifying…" : "Verify all chains"}</Button>
          </>
        }
      />
      {!status ? (
        <Loading />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {status.devices.map((d) => (
              <button
                key={d.device_id}
                onClick={() => setPicked(d.device_id)}
                className={cx(
                  "rounded-xl border bg-white p-4 text-left shadow-card transition-shadow hover:shadow-md",
                  d.ok ? "border-line" : "border-sev-critical ring-2 ring-sev-critical/20",
                  deviceId === d.device_id && "outline outline-2 outline-accent",
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{d.device_id}</span>
                  {d.ok ? <Pill tone="good">✓ Intact</Pill> : <Pill tone="bad">✕ Broken</Pill>}
                </div>
                <div className={cx("mt-2 text-2xl font-semibold tabular-nums", d.ok ? "text-brand" : "text-sev-critical")}>
                  {d.integrity_pct.toFixed(d.ok ? 0 : 3)}%
                </div>
                <div className="text-xs text-ink-muted">{d.verified.toLocaleString()} / {d.total.toLocaleString()} records verified</div>
                <div className="mt-1 truncate font-mono text-[10px] text-ink-faint">head {shortHash(d.chain_head, 16)}</div>
              </button>
            ))}
          </div>

          {chain && (
            <Card className="mt-4" title={`${chain.device_id} · ${chain.broken_records.length ? "blocks around the break" : "latest blocks"}`} action={<span className="text-xs text-ink-muted">checked {chain.state.last_checked?.slice(11, 19) ?? "—"} UTC</span>}>
              <div className="p-4">
                <ChainBlocks blocks={chain.blocks} />
                <p className="mt-2 text-xs text-ink-muted">
                  hash = sha256(prev_hash + signed payload + signature). Each block commits to the one before it.
                </p>
              </div>
            </Card>
          )}

          {broken.length > 0 && (
            <div className="mt-4 space-y-3">
              {broken.slice(0, 3).map((b) => (
                <BrokenPanel
                  key={b.seq}
                  record={b}
                  alert={r7?.find((a) => a.evidence?.telemetry_id === b.telemetry_id)}
                  onRestored={() => { reload(); reloadChain(); }}
                />
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
