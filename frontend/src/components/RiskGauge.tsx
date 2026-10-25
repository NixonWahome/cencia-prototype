/** Semicircle risk gauge, 0–100. Status color + label, never color alone. */
export function RiskGauge({ score }: { score: number | null }) {
  const value = score ?? 0;
  const r = 70;
  const circumference = Math.PI * r;
  const level = score === null ? "Not scanned" : value >= 70 ? "High risk" : value >= 35 ? "Elevated" : value > 0 ? "Low risk" : "Clean";
  const color = score === null ? "#C9C4B8" : value >= 70 ? "#B42318" : value >= 35 ? "#C2410C" : "#15803D";
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 180 104" className="w-48" role="img" aria-label={`Risk score ${score ?? "unknown"} of 100: ${level}`}>
        <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="#ECE9E1" strokeWidth="14" strokeLinecap="round" />
        <path
          d="M 20 90 A 70 70 0 0 1 160 90"
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${(value / 100) * circumference} ${circumference}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
        <text x="90" y="80" textAnchor="middle" className="fill-ink" style={{ fontSize: 32, fontWeight: 600 }}>
          {score ?? "—"}
        </text>
        <text x="90" y="98" textAnchor="middle" className="fill-ink-muted" style={{ fontSize: 11 }}>
          of 100
        </text>
      </svg>
      <div className="mt-1 text-sm font-semibold" style={{ color }}>
        {level}
      </div>
    </div>
  );
}
