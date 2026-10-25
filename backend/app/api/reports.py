from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Site
from ..reports import build_report
from ..runtime import Runtime
from .deps import get_rt
from .telemetry import _to_sim_time

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{site_id}")
def report(site_id: str, from_: datetime | None = Query(None, alias="from"), to: datetime | None = None,
           rt: Runtime = Depends(get_rt), db_: Session = Depends(get_db)):
    if db_.get(Site, site_id) is None:
        raise HTTPException(404, f"unknown site {site_id}")
    end = _to_sim_time(to) or rt.clock.now()
    start = _to_sim_time(from_) or end - timedelta(days=rt.settings.history_days + 1)
    return build_report(db_, rt, site_id, start, end)
