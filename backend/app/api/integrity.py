from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Device, Site, Telemetry
from ..runtime import Runtime
from .deps import get_rt
from .serializers import iso

router = APIRouter(prefix="/api/integrity", tags=["integrity"])


@router.post("/verify/{scope}/{target_id}")
def verify(scope: Literal["device", "site"], target_id: str,
           rt: Runtime = Depends(get_rt), db: Session = Depends(get_db)):
    """Full re-verification of one device chain, or every chain at a site."""
    if scope == "device":
        device = db.get(Device, target_id)
        if device is None or device.public_key is None:
            raise HTTPException(404, f"{target_id} is not a telemetry-signing device")
        return rt.monitor.full_check(db, target_id)

    site = db.get(Site, target_id)
    if site is None:
        raise HTTPException(404, f"unknown site {target_id}")
    reports = [rt.monitor.full_check(db, d.id) for d in site.devices if d.public_key]
    return {
        "site_id": target_id,
        **rt.monitor.site_summary(target_id),
        "devices": reports,
    }


@router.get("/status")
def status(site_id: str | None = None, rt: Runtime = Depends(get_rt)):
    return {"summary": rt.monitor.site_summary(site_id), "devices": rt.monitor.devices(site_id)}


@router.get("/records/{device_id}")
def recent_blocks(device_id: str, limit: int = Query(20, ge=1, le=200),
                  around_broken: bool = Query(True, description="center the window on the first broken record"),
                  rt: Runtime = Depends(get_rt), db: Session = Depends(get_db)):
    """Chain blocks for the Integrity page visual, oldest first.

    Shows the latest blocks, or a window around the first broken record so the
    red block is always on screen.
    """
    state = rt.monitor.device(device_id)
    if state is None:
        raise HTTPException(404, f"{device_id} is not a telemetry-signing device")
    broken = {b["seq"]: b for b in rt.monitor.broken_records(device_id)}
    q = select(Telemetry).where(Telemetry.device_id == device_id)
    if around_broken and broken:
        start = max(1, min(broken) - limit // 2)
        rows = db.scalars(q.where(Telemetry.seq >= start).order_by(Telemetry.seq).limit(limit)).all()
    else:
        rows = list(reversed(db.scalars(q.order_by(Telemetry.seq.desc()).limit(limit)).all()))
    blocks = []
    for row in rows:
        problem = broken.get(row.seq)
        blocks.append({
            "seq": row.seq,
            "ts": iso(row.ts),
            "ac_power_kw": row.ac_power_kw,
            "prev_hash": row.prev_hash,
            "hash": row.hash,
            "signature": row.signature,
            "ok": problem is None,
            "problem": problem,
        })
    # Broken records outside the window are still surfaced so the UI can jump to them.
    return {"device_id": device_id, "state": state, "blocks": blocks,
            "broken_records": [broken[s] for s in sorted(broken)]}
