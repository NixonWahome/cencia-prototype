from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Site, Telemetry
from ..runtime import Runtime
from ..simulator.aggregate import aggregate_site_points, with_expected
from ..simulator.clock import EAT
from .deps import get_rt
from .serializers import telemetry_dict

router = APIRouter(prefix="/api", tags=["telemetry"])

MAX_RANGE = timedelta(days=7)


def _to_sim_time(value: datetime | None) -> datetime | None:
    """Sim timestamps are naive EAT; convert any timezone-aware input."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(EAT).replace(tzinfo=None)


@router.get("/sites/{site_id}/telemetry")
def site_telemetry(
    site_id: str,
    from_: datetime | None = Query(None, alias="from", description="sim time, default 24 h before `to`"),
    to: datetime | None = Query(None, description="sim time, default now"),
    view: Literal["site", "device"] = "site",
    device_id: str | None = None,
    rt: Runtime = Depends(get_rt),
    db: Session = Depends(get_db),
):
    if db.get(Site, site_id) is None:
        raise HTTPException(404, f"unknown site {site_id}")
    to = _to_sim_time(to) or rt.clock.now()
    from_ = _to_sim_time(from_) or to - timedelta(hours=24)
    if to - from_ > MAX_RANGE:
        raise HTTPException(400, "range is limited to 7 days")

    q = select(Telemetry).where(Telemetry.site_id == site_id, Telemetry.ts >= from_, Telemetry.ts <= to)
    if device_id:
        q = q.where(Telemetry.device_id == device_id)
    rows = [telemetry_dict(r) for r in db.scalars(q.order_by(Telemetry.ts, Telemetry.device_id))]

    body = {"site_id": site_id, "from": from_.isoformat(timespec="seconds"),
            "to": to.isoformat(timespec="seconds"), "view": view}
    caps = rt.simulator.capacities
    if view == "site":
        return {**body, "points": aggregate_site_points(rows, caps)}
    return {**body, "readings": [with_expected(r, caps[r["device_id"]]) for r in rows]}
