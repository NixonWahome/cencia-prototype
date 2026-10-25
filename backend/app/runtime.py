"""Wires the clock, simulator, integrity monitor and websocket together."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select

from . import db
from .api.ws import Broadcaster
from .config import Settings
from .demo.attacks import AttackService
from .detection.anomaly import AnomalyDetector
from .detection.engine import DetectionEngine
from .integrity.chain import EdgeAgent
from .integrity.verify import IntegrityMonitor
from .models import Attack, Device, EdgeKey, Site, Telemetry
from .scanner.service import ScanService
from .seed import seed_static
from .simulator.clock import SimClock, default_sim_start
from .simulator.service import Simulator
from .simulator.sites import InverterSpec, SiteSpec

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    settings: Settings
    clock: SimClock
    simulator: Simulator
    monitor: IntegrityMonitor
    ws: Broadcaster
    engine: DetectionEngine = None
    attacks: AttackService = None
    scans: ScanService = None
    _tasks: list[asyncio.Task] = field(default_factory=list)

    def __post_init__(self):
        self.engine = DetectionEngine(self.settings, self.simulator,
                                      AnomalyDetector({i.id: i.capacity_kw for s in self.simulator.sites for i in s.inverters},
                                                      self.settings.rng_seed),
                                      self.ws.publish)
        self.attacks = AttackService(self)
        self.scans = ScanService(self)
        self.retrain()
        self.simulator.listeners.append(self.engine.on_interval)

    def retrain(self) -> dict:
        """Fit the per-site models on history, leaving out known attack windows."""
        with db.read_session() as session:
            exclude = [(a.device_id, a.started_at, a.ended_at or self.clock.now())
                       for a in session.scalars(select(Attack))]
            summary = self.engine.anomaly.train(session, [s.id for s in self.simulator.sites], exclude)
        return {"retrained": summary, "excluded_attack_windows": len(exclude)}

    def sim_status(self) -> dict:
        return {
            "sim_time": self.clock.now().isoformat(timespec="seconds"),
            "last_interval": self.simulator.last_ts.isoformat(timespec="seconds"),
            "speed": self.clock.speed,
            "interval_minutes": self.settings.interval_minutes,
            "timezone": "EAT (UTC+3)",
            "simulated": True,
        }

    def site_spec(self, site_id: str) -> SiteSpec | None:
        return next((s for s in self.simulator.sites if s.id == site_id), None)

    async def start(self) -> None:
        self.ws.bind(asyncio.get_running_loop())
        if self.settings.run_background:
            self._tasks = [
                asyncio.create_task(self._simulate_forever(), name="simulator"),
                asyncio.create_task(self._verify_forever(), name="verifier"),
            ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def _simulate_forever(self) -> None:
        while True:
            await asyncio.sleep(self.settings.tick_seconds)
            try:
                due = await asyncio.to_thread(self.simulator.catch_up)
            except Exception:
                self.engine.discard_pending()
                log.exception("simulator tick failed")
                continue
            self.engine.flush()
            if due:
                await self.ws.broadcast(self.simulator.tick_message(len(due)))

    async def _verify_forever(self) -> None:
        while True:
            await asyncio.sleep(self.settings.verify_every_seconds)
            try:
                problems = await asyncio.to_thread(self.verify_recent)
            except Exception:
                log.exception("integrity pass failed")
                continue
            if problems:
                await self.ws.broadcast({"type": "integrity_failure", "problems": problems})

    def verify_recent(self) -> list[dict]:
        """Background integrity pass; newly broken records raise R7."""
        with db.read_session() as session:
            problems = self.monitor.incremental(session)
        if problems:
            self.engine.on_integrity_failures(problems, self.clock.now())
        return problems


def _load_site_specs(settings: Settings) -> list[SiteSpec]:
    with db.read_session() as session:
        specs = []
        for site in session.scalars(select(Site).order_by(Site.id)):
            inverters = [
                InverterSpec(d.id, site.id, d.capacity_kw, site.nominal_ac_v)
                for d in site.devices if d.kind == "inverter"
            ]
            others = [d.id for d in site.devices if d.kind != "inverter"]
            specs.append(SiteSpec(site.id, site.capacity_kwp, site.ambient_base_c, site.nominal_ac_v,
                                  settings.allowlist_for(site.id), inverters, others))
        return specs


def _load_agents() -> dict[str, EdgeAgent]:
    with db.read_session() as session:
        return {k.device_id: EdgeAgent(k.device_id, k.private_key) for k in session.scalars(select(EdgeKey))}


def build_runtime(settings: Settings) -> Runtime:
    """Seed if the DB is empty, load state, and verify every chain once."""
    with db.write_session() as session:
        fresh = session.scalar(select(func.count()).select_from(Site)) == 0
        if fresh:
            seed_static(session)

    sites = _load_site_specs(settings)
    agents = _load_agents()
    rng = random.Random(settings.rng_seed)

    if fresh:
        start = default_sim_start(settings.sim_start_hour)
    else:
        with db.read_session() as session:
            start = session.scalar(select(func.max(Telemetry.ts))) or default_sim_start(settings.sim_start_hour)

    clock = SimClock(start, settings.sim_speed)
    simulator = Simulator(settings, clock, sites, agents, rng)
    if fresh:
        simulator.backfill_history(start - timedelta(days=settings.history_days), start)
    else:
        simulator.resync_from_db()

    with db.read_session() as session:
        telemetry_devices = [
            (d.id, d.site_id) for d in session.scalars(
                select(Device).where(Device.public_key.is_not(None)).order_by(Device.id)
            )
        ]
    monitor = IntegrityMonitor(telemetry_devices, settings.verify_recent_records)
    with db.read_session() as session:
        monitor.full_check_all(session)

    return Runtime(settings, clock, simulator, monitor, Broadcaster())
