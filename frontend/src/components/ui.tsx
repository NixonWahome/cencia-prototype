import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Severity } from "../api/types";
import { SITE_SHORT } from "../lib/format";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({ children, className, title, action }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    // min-w-0: as a grid item, let wide tables scroll inside the card instead of widening the page
    <section className={cx("min-w-0 rounded-xl border border-line bg-white shadow-card", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const SEV_STYLE: Record<Severity, string> = {
  critical: "bg-red-50 text-sev-critical ring-red-200",
  high: "bg-orange-50 text-sev-high ring-orange-200",
  medium: "bg-amber-50 text-sev-medium ring-amber-200",
  low: "bg-gray-50 text-sev-low ring-gray-200",
};
const SEV_ICON: Record<Severity, string> = { critical: "▲", high: "◆", medium: "●", low: "○" };

/** Severity is never color-alone: icon + label ride along. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset", SEV_STYLE[severity])}>
      <span aria-hidden className="text-[9px]">{SEV_ICON[severity]}</span>
      {severity}
    </span>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "brand" }) {
  const tones = {
    neutral: "bg-gray-100 text-ink-muted",
    good: "bg-green-50 text-sev-good ring-1 ring-inset ring-green-200",
    warn: "bg-amber-50 text-sev-medium ring-1 ring-inset ring-amber-200",
    bad: "bg-red-50 text-sev-critical ring-1 ring-inset ring-red-200",
    brand: "bg-brand-50 text-brand ring-1 ring-inset ring-brand-100",
  };
  return <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function StatusPill({ status }: { status: "normal" | "warning" | "alert" }) {
  if (status === "alert") return <Pill tone="bad">▲ Under attack</Pill>;
  if (status === "warning") return <Pill tone="warn">● Attention</Pill>;
  return <Pill tone="good">✓ Normal</Pill>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "accent" | "danger" | "ghost"; size?: "sm" | "md" | "lg" };

export function Button({ variant = "secondary", size = "md", className, ...props }: ButtonProps) {
  const variants = {
    primary: "bg-brand text-white hover:bg-brand-700 disabled:bg-brand/50",
    accent: "bg-accent text-white hover:bg-accent-700 disabled:bg-accent/50",
    danger: "bg-sev-critical text-white hover:bg-red-800 disabled:opacity-50",
    secondary: "bg-white text-ink ring-1 ring-inset ring-line hover:bg-canvas disabled:opacity-50",
    ghost: "text-ink-muted hover:bg-canvas hover:text-ink",
  };
  const sizes = { sm: "px-2.5 py-1.5 text-xs", md: "px-3.5 py-2 text-sm", lg: "px-4 py-3 text-base" };
  return (
    <button
      {...props}
      className={cx("inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed", variants[variant], sizes[size], className)}
    />
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "bad" | "good" }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums sm:text-3xl", tone === "bad" ? "text-sev-critical" : tone === "good" ? "text-brand" : "text-ink")}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-muted">{hint}</div>}
    </div>
  );
}

export function SiteTabs({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  return (
    <div role="tablist" className="inline-flex rounded-lg bg-white p-1 ring-1 ring-inset ring-line">
      {Object.entries(SITE_SHORT).map(([id, label]) => (
        <button
          key={id}
          role="tab"
          aria-selected={value === id}
          onClick={() => onChange(id)}
          className={cx("rounded-md px-3 py-1.5 text-sm font-medium transition-colors", value === id ? "bg-brand text-white" : "text-ink-muted hover:text-ink")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-10 text-center text-sm text-ink-muted">{children}</div>;
}

export function Loading() {
  return <div className="px-4 py-10 text-center text-sm text-ink-faint">Loading…</div>;
}

export function ProgressBar({ value, tone = "brand" }: { value: number; tone?: "brand" | "accent" }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100" role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all duration-500", tone === "brand" ? "bg-brand" : "bg-accent")} style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  );
}
