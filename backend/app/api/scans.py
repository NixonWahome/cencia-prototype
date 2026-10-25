from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import db
from ..db import get_db
from ..models import Device, Finding, Scan, Site
from ..runtime import Runtime
from ..scanner.scan import SEVERITY_ORDER, latest_scan, recompute_risk, remediate_device
from .deps import get_rt
from .serializers import device_dict, finding_dict, scan_dict

router = APIRouter(prefix="/api", tags=["scans"])


class ScanIn(BaseModel):
    site_id: str


def _scan_body(s: Session, scan: Scan) -> dict:
    findings = s.scalars(select(Finding).where(Finding.scan_id == scan.id)).all()
    findings = sorted(findings, key=lambda f: (SEVERITY_ORDER.index(f.severity), f.device_id))
    return {**scan_dict(scan), "findings": [finding_dict(f) for f in findings],
            "counts": {sev: sum(1 for f in findings if f.severity == sev and f.status == "open") for sev in SEVERITY_ORDER}}


@router.post("/scans")
async def start_scan(body: ScanIn, rt: Runtime = Depends(get_rt)):
    try:
        return await rt.scans.start(body.site_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/scans/{scan_id}")
def get_scan(scan_id: int, db_: Session = Depends(get_db)):
    scan = db_.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, "scan not found")
    return _scan_body(db_, scan)


@router.get("/sites/{site_id}/security")
def site_security(site_id: str, db_: Session = Depends(get_db)):
    """Latest completed scan with findings, any running scan, and device inventory."""
    site = db_.get(Site, site_id)
    if site is None:
        raise HTTPException(404, f"unknown site {site_id}")
    scan = latest_scan(db_, site_id)
    running = db_.scalars(select(Scan).where(Scan.site_id == site_id, Scan.status == "running")
                          .order_by(Scan.id.desc()).limit(1)).first()
    return {
        "site_id": site_id,
        "latest_scan": _scan_body(db_, scan) if scan else None,
        "running_scan": scan_dict(running) if running else None,
        "devices": [device_dict(d) for d in site.devices],
    }


@router.post("/findings/{finding_id}/remediate")
def remediate(finding_id: int, rt: Runtime = Depends(get_rt)):
    with db.write_session() as s:
        finding = s.get(Finding, finding_id)
        if finding is None:
            raise HTTPException(404, "finding not found")
        if finding.status != "open":
            raise HTTPException(400, f"finding is {finding.status}")
        device = s.get(Device, finding.device_id)
        remediate_device(device, finding.finding_type, rt.clock.now().date())
        finding.status, finding.remediated_at = "remediated", rt.clock.now()
        scan = s.get(Scan, finding.scan_id)
        score = recompute_risk(s, scan)
        result = {"finding": finding_dict(finding), "risk_score": score, "device": device_dict(device)}
    rt.ws.publish({"type": "finding_remediated", "site_id": result["finding"]["site_id"], **result})
    return result
