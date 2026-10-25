export const SITE_SHORT: Record<string, string> = {
  kibwezi: "Kibwezi",
  naivasha: "Naivasha",
  thika: "Thika",
};

export function fmtKw(kw: number): string {
  return kw >= 1000 ? `${(kw / 1000).toFixed(2)} MW` : `${kw.toFixed(1)} kW`;
}

export function fmtKwh(kwh: number): string {
  if (kwh >= 1_000_000) return `${(kwh / 1_000_000).toFixed(2)} GWh`;
  if (kwh >= 1000) return `${(kwh / 1000).toFixed(2)} MWh`;
  return `${kwh.toFixed(1)} kWh`;
}

export function fmtSeconds(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  if (s < 1) return `${Math.round(s * 1000)} ms`;
  if (s < 90) return `${s.toFixed(1)} s`;
  return `${(s / 60).toFixed(1)} min`;
}

export function hhmm(iso: string | null | undefined): string {
  return iso ? iso.slice(11, 16) : "—";
}

export function dayTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString(undefined, { day: "numeric", month: "short" })} ${iso.slice(11, 16)}`;
}

export function shortHash(h: string | null | undefined, n = 10): string {
  return h ? `${h.slice(0, n)}…` : "—";
}

export const RULE_LABEL: Record<string, string> = {
  R1: "Night generation",
  R2: "Physics mismatch",
  R3: "Unauthorized command",
  R4: "Command flood",
  R5: "Device silent",
  R6: "Frequency out of range",
  R7: "Integrity failure",
  "ML-ANOMALY": "ML anomaly",
};
