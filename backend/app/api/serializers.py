"""Model → JSON-friendly dict helpers shared by the routers."""
from __future__ import annotations

from datetime import date, datetime

from ..models import Alert, Attack, Command, Device, Finding, Scan, Site, Telemetry

TELEMETRY_FIELDS = (
    "ac_power_kw", "dc_voltage_v", "ac_voltage_v", "frequency_hz", "temperature_c",
    "status", "energy_today_kwh", "irradiance_wm2", "ambient_temp_c",
)


def iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat()


def site_basic(site: Site) -> dict:
    return {
        "id": site.id,
        "name": site.name,
        "site_type": site.site_type,
        "capacity_kwp": site.capacity_kwp,
        "location": site.location,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "emission_baseline": site.emission_baseline,
    }


def device_dict(device: Device) -> dict:
    return {
        "id": device.id,
        "site_id": device.site_id,
        "kind": device.kind,
        "name": device.name,
        "vendor": device.vendor,
        "model": device.model,
        "ip": device.ip,
        "capacity_kw": device.capacity_kw,
        "firmware_version": device.firmware_version,
        "latest_firmware": device.latest_firmware,
        "open_ports": device.open_ports,
        "services": device.services,
        "default_credentials": device.default_credentials,
        "protocol_auth": device.protocol_auth,
        "tls_enabled": device.tls_enabled,
        "last_patched": iso(device.last_patched),
        "signs_telemetry": device.public_key is not None,
        "public_key": device.public_key,
        "quarantined": device.quarantined,
    }


def telemetry_dict(row: Telemetry) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "seq": row.seq,
        "ts": iso(row.ts),
        **{f: getattr(row, f) for f in TELEMETRY_FIELDS},
    }


def _seconds(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return round((later - earlier).total_seconds(), 2)


def alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "site_id": a.site_id,
        "device_id": a.device_id,
        "rule_id": a.rule_id,
        "severity": a.severity,
        "title": a.title,
        "description": a.description,
        "evidence": a.evidence,
        "recommended_action": a.recommended_action,
        "mitre_technique": a.mitre_technique,
        "ml_score": a.ml_score,
        "status": a.status,
        "attack_id": a.attack_id,
        "attack_started_at": iso(a.attack_started_at),
        "detected_at": iso(a.detected_at),
        "acknowledged_at": iso(a.acknowledged_at),
        "resolved_at": iso(a.resolved_at),
        # headline metrics are real seconds; sim seconds shown alongside
        "mttd_seconds": _seconds(a.detected_real, a.attack_started_real),
        "mttd_sim_seconds": _seconds(a.detected_at, a.attack_started_at),
        "mttr_seconds": _seconds(a.resolved_real, a.detected_real),
        "mttr_sim_seconds": _seconds(a.resolved_at, a.detected_at),
    }


def attack_dict(a: Attack) -> dict:
    return {
        "id": a.id,
        "type": a.type,
        "site_id": a.site_id,
        "device_id": a.device_id,
        "started_at": iso(a.started_at),
        "ended_at": iso(a.ended_at),
        "active": a.active,
        "params": a.params,
    }


def finding_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "scan_id": f.scan_id,
        "site_id": f.site_id,
        "device_id": f.device_id,
        "finding_type": f.finding_type,
        "severity": f.severity,
        "title": f.title,
        "evidence": f.evidence,
        "remediation": f.remediation,
        "status": f.status,
        "detected_at": iso(f.detected_at),
        "remediated_at": iso(f.remediated_at),
    }


def scan_dict(s: Scan) -> dict:
    return {
        "id": s.id,
        "site_id": s.site_id,
        "status": s.status,
        "progress": s.progress,
        "current_device": s.current_device,
        "started_at": iso(s.started_at),
        "finished_at": iso(s.finished_at),
        "risk_score": s.risk_score,
    }


def command_dict(cmd: Command) -> dict:
    return {
        "id": cmd.id,
        "site_id": cmd.site_id,
        "device_id": cmd.device_id,
        "ts": iso(cmd.ts),
        "command": cmd.command,
        "params": cmd.params,
        "source_ip": cmd.source_ip,
        "user": cmd.user,
        "protocol": cmd.protocol,
        "is_write": cmd.is_write,
        "attack_id": cmd.attack_id,
    }
