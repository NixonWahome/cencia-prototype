"""Simulation service: weather → inverter readings → edge signing → DB.

`catch_up` generates every interval that is due on the sim clock, so a time
jump is backfilled and charts and hash chains stay continuous.
"""
from __future__ import annotations

import json
import logging
import random
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import db
from ..config import Settings
from ..integrity.chain import GENESIS_HASH, EdgeAgent, SealedRecord
from ..models import Command, Telemetry
from .aggregate import aggregate_site_points
from .clock import SimClock
from .commands import CommandGenerator
from .generator import TelemetryGenerator
from .sites import SiteSpec

log = logging.getLogger(__name__)

# Applied at the source, before signing: used by attacks that make a device lie.
ReadingModifier = Callable[[dict, datetime], dict]
# Called inside the write transaction after each live interval (detection hooks).
# `fast_forward` is True for intervals backfilled after a clock jump, except the
# last few, so expensive checks can be skipped while catching up.
IntervalListener = Callable[[Session, datetime, list[dict], bool], None]
LIVE_TAIL_INTERVALS = 2

HISTORY_COMMIT_INTERVALS = 288  # one sim day per transaction while seeding


def telemetry_row(record: SealedRecord, ts: datetime) -> Telemetry:
    p = record.payload
    return Telemetry(
        device_id=p["device_id"],
        site_id=p["site_id"],
        seq=record.seq,
        ts=ts,
        ac_power_kw=p["ac_power_kw"],
        dc_voltage_v=p["dc_voltage_v"],
        ac_voltage_v=p["ac_voltage_v"],
        frequency_hz=p["frequency_hz"],
        temperature_c=p["temperature_c"],
        status=p["status"],
        energy_today_kwh=p["energy_today_kwh"],
        irradiance_wm2=p["irradiance_wm2"],
        ambient_temp_c=p["ambient_temp_c"],
        payload=record.canonical,
        signature=record.signature,
        prev_hash=record.prev_hash,
        hash=record.hash,
    )


class Simulator:
    def __init__(self, settings: Settings, clock: SimClock, sites: list[SiteSpec],
                 agents: dict[str, EdgeAgent], rng: random.Random):
        self.settings = settings
        self.clock = clock
        self.sites = sites
        self.agents = agents
        self.interval = timedelta(minutes=settings.interval_minutes)
        self.generator = TelemetryGenerator(rng, settings.interval_minutes / 60)
        self.commands = CommandGenerator(rng, settings.maintenance_start_hour, settings.maintenance_end_hour)

        self.offline: set[str] = set()
        self.modifiers: dict[str, list[ReadingModifier]] = {}
        self.listeners: list[IntervalListener] = []
        self.latest: dict[str, dict] = {}  # device_id -> last signed payload
        self.capacities = {inv.id: inv.capacity_kw for site in sites for inv in site.inverters}
        self.last_ts: datetime | None = None
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Held while generating; take it before the DB write lock."""
        return self._lock

    # ---- generation -------------------------------------------------------

    def _generate(self, session: Session, ts: datetime, notify: bool, fast_forward: bool = False) -> list[dict]:
        batch: list[dict] = []
        for site in self.sites:
            irradiance, ambient = self.generator.site_conditions(site.id, ts, site.ambient_base_c)
            for inv in site.inverters:
                if inv.id in self.offline:
                    continue
                reading = self.generator.inverter_reading(inv, ts, irradiance, ambient)
                for modify in list(self.modifiers.get(inv.id, ())):
                    reading = modify(reading, ts)
                reading["energy_today_kwh"] = self.generator.accumulate_energy(inv.id, ts, reading["ac_power_kw"])
                record = self.agents[inv.id].seal(reading)
                session.add(telemetry_row(record, ts))
                self.latest[inv.id] = record.payload
                batch.append(record.payload)
            for cmd in self.commands.generate(site, ts):
                session.add(Command(**cmd))
        self.last_ts = ts
        if notify:
            session.flush()
            for listener in list(self.listeners):
                listener(session, ts, batch, fast_forward)
        return batch

    def backfill_history(self, start: datetime, end: datetime) -> int:
        """Seed history from `start` to `end` inclusive. No detection hooks run."""
        with self._lock:
            count, ts = 0, start
            while ts <= end:
                with db.write_session() as session:
                    for _ in range(HISTORY_COMMIT_INTERVALS):
                        if ts > end:
                            break
                        self._generate(session, ts, notify=False)
                        ts += self.interval
                        count += 1
            return count

    def catch_up(self) -> list[datetime]:
        """Generate every interval that is due on the sim clock."""
        with self._lock:
            now = self.clock.now()
            due: list[datetime] = []
            ts = self.last_ts + self.interval
            while ts <= now:
                due.append(ts)
                ts += self.interval
            if not due:
                return []
            if len(due) > self.settings.max_catchup_intervals:
                due = due[-self.settings.max_catchup_intervals:]
            try:
                with db.write_session() as session:
                    for i, ts in enumerate(due):
                        self._generate(session, ts, notify=True,
                                       fast_forward=i < len(due) - LIVE_TAIL_INTERVALS)
            except Exception:
                # The transaction rolled back but the agents advanced their chain
                # heads; realign them with what is actually stored.
                self.resync_from_db()
                raise
            return due

    def resync_from_db(self) -> None:
        with self._lock, db.read_session() as session:
            last_ts = None
            for device_id, agent in self.agents.items():
                row = session.scalars(
                    select(Telemetry).where(Telemetry.device_id == device_id)
                    .order_by(Telemetry.seq.desc()).limit(1)
                ).first()
                if row is None:
                    agent.reset_head(0, GENESIS_HASH)
                    continue
                agent.reset_head(row.seq, row.hash)
                self.latest[device_id] = _payload_of(row)
                self.generator.set_energy(device_id, row.ts, row.energy_today_kwh)
                last_ts = row.ts if last_ts is None else max(last_ts, row.ts)
            if last_ts is not None:
                self.last_ts = last_ts

    # ---- live view --------------------------------------------------------

    def device_online(self, device_id: str) -> bool:
        latest = self.latest.get(device_id)
        if latest is None or device_id in self.offline or self.last_ts is None:
            return False
        return datetime.fromisoformat(latest["ts"]) >= self.last_ts - self.interval

    def site_live(self, site: SiteSpec) -> dict:
        readings = [self.latest[i.id] for i in site.inverters if self.device_online(i.id)]
        current = [r for r in readings if r["ts"] == self.last_ts.isoformat(timespec="seconds")]
        points = aggregate_site_points(current, self.capacities)
        return {
            "point": points[-1] if points else None,
            "online_devices": len(readings),
            "inverters": len(site.inverters),
            "devices": {
                inv.id: {**self.latest[inv.id], "online": self.device_online(inv.id)}
                for inv in site.inverters if inv.id in self.latest
            },
        }

    def tick_message(self, intervals: int) -> dict:
        return {
            "type": "tick",
            "sim_time": self.clock.now().isoformat(timespec="seconds"),
            "ts": self.last_ts.isoformat(timespec="seconds"),
            "intervals": intervals,
            "sites": {site.id: self.site_live(site) for site in self.sites},
        }


def _payload_of(row: Telemetry) -> dict:
    return json.loads(row.payload)
