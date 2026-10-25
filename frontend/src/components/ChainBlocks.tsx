import type { ChainBlock } from "../api/types";
import { hhmm, shortHash } from "../lib/format";
import { cx } from "./ui";

/** Hash-chain visual: each block links to its predecessor; broken blocks turn red. */
export function ChainBlocks({ blocks, selected, onSelect }: { blocks: ChainBlock[]; selected?: number; onSelect?: (seq: number) => void }) {
  return (
    <div className="overflow-x-auto pb-2">
      <ol className="flex min-w-max items-center">
        {blocks.map((b, i) => (
          <li key={b.seq} className="flex items-center">
            {i > 0 && (
              <span aria-hidden className={cx("h-0.5 w-4", b.ok && blocks[i - 1].ok ? "bg-brand/40" : "bg-sev-critical")} />
            )}
            <button
              onClick={() => onSelect?.(b.seq)}
              className={cx(
                "w-28 rounded-lg border-2 p-2 text-left text-[11px] transition-shadow hover:shadow-md",
                b.ok ? "border-brand/30 bg-white" : "border-sev-critical bg-red-50 animate-[pulse_2s_ease-in-out_3]",
                selected === b.seq && "ring-2 ring-accent ring-offset-1",
              )}
              title={b.ok ? "Signature and chain link verified" : b.problem?.summary}
            >
              <div className="flex items-center justify-between font-semibold">
                <span className={b.ok ? "text-brand" : "text-sev-critical"}>#{b.seq}</span>
                <span aria-label={b.ok ? "verified" : "broken"}>{b.ok ? "✓" : "✕"}</span>
              </div>
              <div className="text-ink-muted">{hhmm(b.ts)}</div>
              <div className="font-semibold tabular-nums text-ink">{b.ac_power_kw.toFixed(1)} kW</div>
              <div className="mt-1 truncate font-mono text-[10px] text-ink-faint">{shortHash(b.hash, 8)}</div>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
