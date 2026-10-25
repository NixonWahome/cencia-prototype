"""Runs simulated scans as background tasks with per-device progress."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from .. import db
from ..api.serializers import finding_dict, scan_dict
from ..detection.engine import utcnow
from ..models import Device, Finding, Scan, Site
from .scan import CATALOG, evaluate_device, risk_score

if TYPE_CHECKING:
    from ..runtime import Runtime

DEVICE_DELAY_SECONDS = 0.9


class ScanService:
    def __init__(self, rt: "Runtime"):
        self.rt = rt
        self._tasks: dict[int, asyncio.Task] = {}

    def _create(self, site_id: str) -> dict:
        with db.write_session() as s:
            if s.get(Site, site_id) is None:
                raise LookupError(f"unknown site {site_id}")
            scan = Scan(site_id=site_id, status="running", progress=0.0, started_at=self.rt.clock.now())
            s.add(scan)
            s.flush()
            return scan_dict(scan)

    async def start(self, site_id: str) -> dict:
        scan = await asyncio.to_thread(self._create, site_id)
        self._tasks[scan["id"]] = asyncio.create_task(self._run(scan["id"], site_id))
        return scan

    async def _run(self, scan_id: int, site_id: str) -> None:
        with db.read_session() as s:
            device_ids = [d for d in s.scalars(select(Device.id).where(Device.site_id == site_id).order_by(Device.id))]
        try:
            for i, device_id in enumerate(device_ids):
                await self._progress(scan_id, device_id, i / len(device_ids))
                await asyncio.sleep(DEVICE_DELAY_SECONDS)
                found = await asyncio.to_thread(self._scan_device, scan_id, site_id, device_id)
                await self.rt.ws.broadcast({"type": "scan_progress", "scan_id": scan_id, "site_id": site_id,
                                            "device_id": device_id, "progress": (i + 1) / len(device_ids),
                                            "findings": found})
            result = await asyncio.to_thread(self._finish, scan_id, site_id)
            await self.rt.ws.broadcast({"type": "scan_complete", "scan": result})
        finally:
            self._tasks.pop(scan_id, None)

    async def _progress(self, scan_id: int, device_id: str, progress: float) -> None:
        def write():
            with db.write_session() as s:
                s.execute(update(Scan).where(Scan.id == scan_id).values(current_device=device_id, progress=progress))
        await asyncio.to_thread(write)

    def _scan_device(self, scan_id: int, site_id: str, device_id: str) -> list[dict]:
        with db.write_session() as s:
            device = s.get(Device, device_id)
            now = self.rt.clock.now()
            rows = []
            for finding_type, evidence in evaluate_device(device):
                meta = CATALOG[finding_type]
                rows.append(Finding(scan_id=scan_id, site_id=site_id, device_id=device_id, finding_type=finding_type,
                                    severity=meta["severity"], title=meta["title"], evidence=evidence,
                                    remediation=meta["remediation"], status="open", detected_at=now))
            s.add_all(rows)
            s.flush()
            return [finding_dict(f) for f in rows]

    def _finish(self, scan_id: int, site_id: str) -> dict:
        with db.write_session() as s:
            # Findings from earlier scans are replaced by this one.
            s.execute(update(Finding).where(Finding.site_id == site_id, Finding.scan_id != scan_id,
                                            Finding.status == "open").values(status="superseded"))
            scan = s.get(Scan, scan_id)
            findings = s.scalars(select(Finding).where(Finding.scan_id == scan_id)).all()
            scan.status, scan.progress, scan.current_device = "completed", 1.0, None
            scan.finished_at = self.rt.clock.now()
            scan.risk_score = risk_score(findings)
            return {**scan_dict(scan), "finished_real": utcnow().isoformat(timespec="seconds")}

    def cancel_all(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()
