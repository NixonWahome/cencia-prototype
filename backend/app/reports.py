"""Investor report: verified generation, integrity and security posture."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Alert, Attack, Finding, Site, Telemetry
from .scanner.scan import latest_scan
from .simulator import physics

SOURCE_FRAUD = ("spoof_night_generation", "inflate_output")


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build_report(session: Session, rt, site_id: str, start: datetime, end: datetime) -> dict:
    site = session.get(Site, site_id)
    interval_h = rt.settings.interval_minutes / 60
    capacities = rt.engine.capacities
    broken = {(d["device_id"], b["seq"]) for d in rt.monitor.devices(site_id)
              for b in rt.monitor.broken_records(d["device_id"])}
    attacks = session.scalars(select(Attack).where(Attack.site_id == site_id, Attack.type.in_(SOURCE_FRAUD))).all()
    windows = [(a.device_id, a.started_at, a.ended_at or end) for a in attacks]

    reported = tampered_excess = spoofed_excess = 0.0
    records = broken_count = 0
    daily: dict[str, dict] = defaultdict(lambda: {"reported_kwh": 0.0, "verified_kwh": 0.0})
    rows = session.scalars(select(Telemetry).where(
        Telemetry.site_id == site_id, Telemetry.ts >= start, Telemetry.ts <= end).order_by(Telemetry.ts))
    for t in rows:
        records += 1
        kwh = t.ac_power_kw * interval_h
        reported += kwh
        excess = 0.0
        if (t.device_id, t.seq) in broken:
            broken_count += 1
            signed_kw = json.loads(t.payload).get("ac_power_kw", 0.0)
            excess += max(0.0, t.ac_power_kw - signed_kw) * interval_h
            tampered_excess += max(0.0, t.ac_power_kw - signed_kw) * interval_h
        if any(t.device_id == d and s < t.ts <= e for d, s, e in windows):
            expected = physics.expected_power_kw(t.irradiance_wm2, t.ambient_temp_c, capacities[t.device_id])
            spoof = max(0.0, min(t.ac_power_kw, json.loads(t.payload)["ac_power_kw"]) - expected) * interval_h
            excess += spoof
            spoofed_excess += spoof
        day = daily[t.ts.date().isoformat()]
        day["reported_kwh"] += kwh
        day["verified_kwh"] += kwh - excess

    verified = reported - tampered_excess - spoofed_excess
    factor = rt.settings.emission_factors[site.emission_baseline]

    alerts = session.scalars(select(Alert).where(Alert.site_id == site_id)).all()
    mttd = [(a.detected_real - a.attack_started_real).total_seconds() for a in alerts if a.attack_started_real]
    mttr = [(a.resolved_real - a.detected_real).total_seconds() for a in alerts if a.resolved_real]
    scan = latest_scan(session, site_id)
    open_findings = session.scalars(select(Finding).where(Finding.site_id == site_id, Finding.status == "open")).all()
    integrity = rt.monitor.site_summary(site_id)

    return {
        "site": {"id": site.id, "name": site.name, "site_type": site.site_type, "capacity_kwp": site.capacity_kwp,
                 "location": site.location},
        "period": {"from": start.isoformat(timespec="seconds"), "to": end.isoformat(timespec="seconds")},
        "generated_at_sim": rt.clock.now().isoformat(timespec="seconds"),
        "simulated": True,
        "generation": {
            "reported_kwh": round(reported, 1),
            "verified_kwh": round(verified, 1),
            "flagged_kwh": round(tampered_excess + spoofed_excess, 1),
            "tampered_kwh": round(tampered_excess, 1),
            "spoofed_kwh": round(spoofed_excess, 1),
            "daily": [{"date": d, "reported_kwh": round(v["reported_kwh"], 1), "verified_kwh": round(v["verified_kwh"], 1)}
                      for d, v in sorted(daily.items())],
        },
        "integrity": {
            "records": records,
            "verified_records": records - broken_count,
            "verified_pct": round((records - broken_count) / records * 100, 3) if records else 100.0,
            "chain_heads": [{"device_id": d["device_id"], "chain_head": d["chain_head"], "ok": d["ok"]}
                            for d in rt.monitor.devices(site_id)],
            "all_chains_ok": integrity["ok"],
        },
        "security": {
            "risk_score": scan.risk_score if scan else None,
            "last_scan": scan.finished_at.isoformat(timespec="seconds") if scan and scan.finished_at else None,
            "open_critical_findings": sum(1 for f in open_findings if f.severity == "critical"),
            "open_findings": len(open_findings),
            "alerts_total": len(alerts),
            "open_alerts": sum(1 for a in alerts if a.status != "resolved"),
            "avg_mttd_seconds": _avg(mttd),
            "avg_mttr_seconds": _avg(mttr),
        },
        "carbon": {
            "baseline": site.emission_baseline,
            "kg_co2_per_kwh": factor["kg_co2_per_kwh"],
            "label": factor["label"],
            "avoided_t_co2": round(verified * factor["kg_co2_per_kwh"] / 1000, 3),
            "disclaimer": "Illustrative only. Emission factors are placeholders and must be verified before use.",
        },
    }
