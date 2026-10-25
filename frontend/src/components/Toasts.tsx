import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useLive, type Toast } from "../api/live";
import { SITE_SHORT } from "../lib/format";
import { cx } from "./ui";

const TONE: Record<Toast["tone"], { bar: string; icon: string }> = {
  critical: { bar: "bg-sev-critical", icon: "▲" },
  high: { bar: "bg-sev-high", icon: "◆" },
  medium: { bar: "bg-sev-medium", icon: "●" },
  info: { bar: "bg-accent", icon: "●" },
  good: { bar: "bg-sev-good", icon: "✓" },
};

/** Mock of the SMS an on-call operator would receive for high/critical alerts. */
function SmsCard() {
  const { sms, dismissSms } = useLive();
  useEffect(() => {
    if (!sms) return;
    const t = window.setTimeout(dismissSms, 12000);
    return () => window.clearTimeout(t);
  }, [sms, dismissSms]);
  if (!sms) return null;
  const ip = sms.evidence?.source_ip as string | undefined;
  return (
    <div className="pointer-events-auto w-72 rounded-[1.6rem] border-4 border-ink bg-ink p-2 shadow-2xl">
      <div className="rounded-[1.2rem] bg-white p-3">
        <div className="mb-2 flex items-center justify-between text-[10px] text-ink-faint">
          <span>Messages · now</span>
          <button onClick={dismissSms} className="text-ink-faint hover:text-ink" aria-label="Dismiss SMS">✕</button>
        </div>
        <div className="text-xs font-semibold text-ink">CENCIA-SOC</div>
        <div className="mt-1 rounded-2xl rounded-tl-sm bg-gray-100 px-3 py-2 text-xs leading-relaxed text-ink">
          [{sms.severity.toUpperCase()}] {SITE_SHORT[sms.site_id]}: {sms.title}.{ip ? ` Source ${ip}.` : ""} Reply 1 to {ip ? "block" : "isolate"}, 2 to acknowledge.
        </div>
      </div>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useLive();
  return (
    <>
      <div className="pointer-events-none fixed left-4 top-28 z-40 hidden flex-col gap-2 md:flex print:hidden">
        <SmsCard />
      </div>
      <div className="pointer-events-none fixed inset-x-4 bottom-20 z-40 flex flex-col items-end gap-2 sm:inset-x-auto sm:right-5 sm:w-96 print:hidden" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto flex w-full overflow-hidden rounded-lg border border-line bg-white shadow-lg">
            <div className={cx("w-1.5 shrink-0", TONE[t.tone].bar)} />
            <div className="flex-1 px-3 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-semibold text-ink">
                  <span aria-hidden className="mr-1">{TONE[t.tone].icon}</span>
                  {t.href ? <Link to={t.href} className="hover:underline">{t.title}</Link> : t.title}
                </div>
                <button onClick={() => dismissToast(t.id)} className="text-ink-faint hover:text-ink" aria-label="Dismiss">✕</button>
              </div>
              {t.body && <div className="mt-0.5 text-xs text-ink-muted">{t.body}</div>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
