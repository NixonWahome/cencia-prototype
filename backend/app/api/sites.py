from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Alert, Command, Device, Scan, Site
from ..runtime import Runtime
from .deps import get_rt
from .serializers import command_dict, device_dict, site_basic

router = APIRouter(prefix="/api", tags=["sites"])


def _open_alert_counts(db: Session, site_id: str | None = None) -> dict[str, int]:
    q = select(Alert.severity, func.count()).where(Alert.status != "resolved").group_by(Alert.severity)
    if site_id:
        q = q.where(Alert.site_id == site_id)
    return {sev: n for sev, n in db.execute(q)}


def _risk_score(db: Session, site_id: str) -> int | None:
    return db.scalar(
        select(Scan.risk_score).where(Scan.site_id == site_id, Scan.status == "completed")
        .order_by(Scan.id.desc()).limit(1)
    )


def _site_summary(site: Site, rt: Runtime, db: Session) -> dict:
    spec = rt.site_spec(site.id)
    live = rt.simulator.site_live(spec)
    alerts = _open_alert_counts(db, site.id)
    if alerts.get("critical") or alerts.get("high"):
        status = "alert"
    elif live["online_devices"] < live["inverters"] or alerts:
        status = "warning"
    else:
        status = "normal"
    point = live["point"] or {}
    return {
        **site_basic(site),
        "status": status,
        "live_kw": point.get("ac_power_kw", 0.0),
        "irradiance_wm2": point.get("irradiance_wm2", 0.0),
        "energy_today_kwh": point.get("energy_today_kwh", 0.0),
        "online_devices": live["online_devices"],
        "inverters": live["inverters"],
        "open_alerts": sum(alerts.values()),
        "open_alerts_by_severity": alerts,
        "risk_score": _risk_score(db, site.id),
        "integrity": rt.monitor.site_summary(site.id),
    }


def _get_site(db: Session, site_id: str) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(404, f"unknown site {site_id}")
    return site


@router.get("/overview")
def overview(rt: Runtime = Depends(get_rt), db: Session = Depends(get_db)):
    sites = [_site_summary(s, rt, db) for s in db.scalars(select(Site).order_by(Site.id))]
    alerts = _open_alert_counts(db)
    mttd = db.execute(
        select(Alert.detected_real, Alert.attack_started_real).where(Alert.attack_started_real.is_not(None))
    ).all()
    mttd_seconds = [(d - a).total_seconds() for d, a in mttd]
    return {
        "sim": rt.sim_status(),
        "kpis": {
            "mw_monitored": round(sum(s["capacity_kwp"] for s in sites) / 1000, 2),
            "live_mw": round(sum(s["live_kw"] for s in sites) / 1000, 3),
            "open_critical_alerts": alerts.get("critical", 0),
            "open_alerts": sum(alerts.values()),
            "avg_mttd_seconds": round(sum(mttd_seconds) / len(mttd_seconds), 1) if mttd_seconds else None,
            "telemetry_verified_pct": rt.monitor.site_summary()["integrity_pct"],
        },
        "sites": sites,
    }


@router.get("/sim")
def sim_status(rt: Runtime = Depends(get_rt)):
    return rt.sim_status()


@router.get("/sites")
def list_sites(rt: Runtime = Depends(get_rt), db: Session = Depends(get_db)):
    return [_site_summary(s, rt, db) for s in db.scalars(select(Site).order_by(Site.id))]


@router.get("/sites/{site_id}")
def get_site(site_id: str, rt: Runtime = Depends(get_rt), db: Session = Depends(get_db)):
    site = _get_site(db, site_id)
    live = rt.simulator.site_live(rt.site_spec(site_id))
    devices = []
    for d in site.devices:
        entry = device_dict(d)
        entry["latest"] = live["devices"].get(d.id)
        entry["online"] = rt.simulator.device_online(d.id) if entry["signs_telemetry"] else True
        entry["integrity"] = rt.monitor.device(d.id)
        devices.append(entry)
    return {**_site_summary(site, rt, db), "devices": devices}


@router.get("/sites/{site_id}/commands")
def site_commands(site_id: str, limit: int = Query(100, ge=1, le=1000),
                  writes_only: bool = False, db: Session = Depends(get_db)):
    _get_site(db, site_id)
    q = select(Command).where(Command.site_id == site_id)
    if writes_only:
        q = q.where(Command.is_write.is_(True))
    rows = db.scalars(q.order_by(Command.ts.desc(), Command.id.desc()).limit(limit))
    return [command_dict(c) for c in rows]


@router.get("/devices/{device_id}")
def get_device(device_id: str, rt: Runtime = Depends(get_rt), db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, f"unknown device {device_id}")
    return {
        **device_dict(device),
        "latest": rt.simulator.latest.get(device_id),
        "online": rt.simulator.device_online(device_id) if device.public_key else True,
        "integrity": rt.monitor.device(device_id),
    }
