export type Severity = "critical" | "high" | "medium" | "low";
export type AlertStatus = "open" | "acknowledged" | "resolved";

export interface SimStatus {
  sim_time: string;
  last_interval: string;
  speed: number;
  interval_minutes: number;
  timezone: string;
  simulated: boolean;
}

export interface IntegritySummary {
  total: number;
  verified: number;
  integrity_pct: number;
  ok: boolean;
}

export interface SiteSummary {
  id: string;
  name: string;
  site_type: string;
  capacity_kwp: number;
  location: string;
  status: "normal" | "warning" | "alert";
  live_kw: number;
  irradiance_wm2: number;
  energy_today_kwh: number;
  online_devices: number;
  inverters: number;
  open_alerts: number;
  open_alerts_by_severity: Partial<Record<Severity, number>>;
  risk_score: number | null;
  integrity: IntegritySummary;
}

export interface Overview {
  sim: SimStatus;
  kpis: {
    mw_monitored: number;
    live_mw: number;
    open_critical_alerts: number;
    open_alerts: number;
    avg_mttd_seconds: number | null;
    telemetry_verified_pct: number;
  };
  sites: SiteSummary[];
}

export interface Reading {
  ts: string;
  device_id: string;
  ac_power_kw: number;
  expected_kw?: number;
  dc_voltage_v: number;
  ac_voltage_v: number;
  frequency_hz: number;
  temperature_c: number;
  status: string;
  energy_today_kwh: number;
  irradiance_wm2: number;
  ambient_temp_c: number;
}

export interface SitePoint {
  ts: string;
  ac_power_kw: number;
  expected_kw: number;
  irradiance_wm2: number;
  ac_voltage_v: number;
  frequency_hz: number;
  temperature_c: number;
  energy_today_kwh: number;
  reporting_devices: number;
}

export interface DeviceIntegrity {
  device_id: string;
  site_id: string;
  ok: boolean;
  total: number;
  verified: number;
  integrity_pct: number;
  chain_head: string | null;
  first_broken: BrokenRecord | null;
  broken_count: number;
  last_checked: string | null;
}

export interface Device {
  id: string;
  site_id: string;
  kind: string;
  name: string;
  vendor: string;
  model: string;
  ip: string;
  capacity_kw: number | null;
  firmware_version: string;
  latest_firmware: string;
  open_ports: number[];
  services: { port: number; name: string; [k: string]: unknown }[];
  default_credentials: boolean;
  protocol_auth: boolean;
  tls_enabled: boolean;
  last_patched: string;
  signs_telemetry: boolean;
  public_key: string | null;
  quarantined: boolean;
  latest?: Reading | null;
  online?: boolean;
  integrity?: DeviceIntegrity | null;
}

export interface SiteDetail extends SiteSummary {
  devices: Device[];
}

export interface Command {
  id: number;
  site_id: string;
  device_id: string;
  ts: string;
  command: string;
  params: Record<string, unknown>;
  source_ip: string;
  user: string;
  protocol: string;
  is_write: boolean;
  attack_id: number | null;
}

export interface Explanation {
  feature: string;
  value: number;
  baseline: number;
  z: number;
  text: string;
}

export interface Alert {
  id: number;
  site_id: string;
  device_id: string | null;
  rule_id: string;
  rule_name: string;
  severity: Severity;
  title: string;
  description: string;
  evidence: Record<string, any>;
  recommended_action: string;
  mitre_technique: string | null;
  ml_score: number | null;
  status: AlertStatus;
  attack_id: number | null;
  attack_started_at: string | null;
  detected_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  mttd_seconds: number | null;
  mttd_sim_seconds: number | null;
  mttr_seconds: number | null;
  mttr_sim_seconds: number | null;
  actions?: string[];
}

export interface Finding {
  id: number;
  scan_id: number;
  site_id: string;
  device_id: string;
  finding_type: string;
  severity: Severity;
  title: string;
  evidence: string;
  remediation: string;
  status: "open" | "remediated" | "superseded";
  detected_at: string;
  remediated_at: string | null;
}

export interface Scan {
  id: number;
  site_id: string;
  status: "running" | "completed";
  progress: number;
  current_device: string | null;
  started_at: string;
  finished_at: string | null;
  risk_score: number | null;
  findings?: Finding[];
  counts?: Record<Severity, number>;
}

export interface SiteSecurity {
  site_id: string;
  latest_scan: Scan | null;
  running_scan: Scan | null;
  devices: Device[];
}

export interface Problem {
  check: string;
  message: string;
  fields?: { field: string; signed: unknown; stored: unknown; message: string }[];
}

export interface BrokenRecord {
  telemetry_id: number;
  seq: number;
  ts: string;
  hash: string;
  problems: Problem[];
  summary: string;
}

export interface ChainBlock {
  seq: number;
  ts: string;
  ac_power_kw: number;
  prev_hash: string;
  hash: string;
  signature: string;
  ok: boolean;
  problem: BrokenRecord | null;
}

export interface ChainRecords {
  device_id: string;
  state: DeviceIntegrity;
  blocks: ChainBlock[];
  broken_records: BrokenRecord[];
}

export interface AttackSpec {
  type: string;
  site_id: string;
  device_id: string;
  label: string;
  expects: string[];
  story: string;
}

export interface AttackRun {
  id: number;
  type: string;
  site_id: string;
  device_id: string;
  started_at: string;
  ended_at: string | null;
  active: boolean;
  params: Record<string, unknown>;
  label?: string;
  note?: string;
  jumped_to?: string | null;
}

export interface Report {
  site: { id: string; name: string; site_type: string; capacity_kwp: number; location: string };
  period: { from: string; to: string };
  generated_at_sim: string;
  simulated: boolean;
  generation: {
    reported_kwh: number;
    verified_kwh: number;
    flagged_kwh: number;
    tampered_kwh: number;
    spoofed_kwh: number;
    daily: { date: string; reported_kwh: number; verified_kwh: number }[];
  };
  integrity: {
    records: number;
    verified_records: number;
    verified_pct: number;
    chain_heads: { device_id: string; chain_head: string | null; ok: boolean }[];
    all_chains_ok: boolean;
  };
  security: {
    risk_score: number | null;
    last_scan: string | null;
    open_critical_findings: number;
    open_findings: number;
    alerts_total: number;
    open_alerts: number;
    avg_mttd_seconds: number | null;
    avg_mttr_seconds: number | null;
  };
  carbon: { baseline: string; kg_co2_per_kwh: number; label: string; avoided_t_co2: number; disclaimer: string };
}

export type LiveMessage =
  | ({ type: "hello" } & SimStatus)
  | { type: "tick"; sim_time: string; ts: string; intervals: number; sites: Record<string, { point: SitePoint | null; online_devices: number; inverters: number }> }
  | { type: "alert"; alert: Alert }
  | { type: "alert_updated"; alert: Alert }
  | { type: "attack"; attack: AttackRun }
  | { type: "integrity_failure"; problems: (BrokenRecord & { device_id: string; site_id: string })[] }
  | { type: "scan_progress"; scan_id: number; site_id: string; device_id: string; progress: number; findings: Finding[] }
  | { type: "scan_complete"; scan: Scan }
  | { type: "finding_remediated"; site_id: string; risk_score: number }
  | { type: "reset" };
