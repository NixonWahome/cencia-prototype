"""Detection engine: runs rules + ML on every interval and every command.

Alerts are de-duplicated: while an alert for the same (site, device, rule) is
open or acknowledged, new hits only bump its occurrence count. New alerts are
correlated with any active attack on the same device so MTTD is measurable.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import db
from ..api.serializers import alert_dict
from ..config import Settings
from ..models import Alert, Attack, Command, Device
from ..simulator.service import Simulator
from . import rules
from .anomaly import AnomalyDetector
from .rules import RULES, Candidate


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DetectionEngine:
    def __init__(self, settings: Settings, simulator: Simulator, anomaly: AnomalyDetector, publish):
        self.settings = settings
        self.simulator = simulator
        self.anomaly = anomaly
        self.interval = timedelta(minutes=settings.interval_minutes)
        self.capacities = {inv.id: inv.capacity_kw for site in simulator.sites for inv in site.inverters}
        self.allowlists = {site.id: site.allowlist for site in simulator.sites}
        self._publish = publish
        self._pending: list[dict] = []
        self._lock = threading.Lock()

    # ---- entry points ------------------------------------------------------

    def on_interval(self, session: Session, ts: datetime, readings: list[dict], fast_forward: bool = False) -> None:
        """Simulator listener: runs inside the interval's write transaction.

        Rules run on every interval; the ML pass is skipped while fast-forwarding.
        """
        quarantined = set(session.scalars(select(Device.id).where(Device.quarantined.is_(True))))
        candidates: list[Candidate] = []
        by_site: dict[str, list[dict]] = {}
        for r in readings:
            if r["device_id"] in quarantined:
                continue
            cap = self.capacities[r["device_id"]]
            for check in (rules.check_night_generation(r, cap, self.settings),
                          rules.check_physics(r, cap, self.settings),
                          rules.check_frequency(r, self.settings)):
                if check:
                    candidates.append(check)
            by_site.setdefault(r["site_id"], []).append(r)

        for site_id, site_readings in ({} if fast_forward else by_site).items():
            for r, score, explanation in self.anomaly.score(site_id, site_readings):
                candidates.append(Candidate(
                    "ML-ANOMALY", site_id, r["device_id"],
                    f"Anomalous behaviour on {r['device_id']}",
                    "IsolationForest flagged this reading as unlike the site's normal pattern: "
                    + "; ".join(e["text"] for e in explanation) + ".",
                    {"ts": r["ts"], "score": round(score, 4),
                     "threshold": round(self.anomaly.models[site_id].threshold, 4),
                     "explanation": explanation, "ac_power_kw": r["ac_power_kw"],
                     "irradiance_wm2": r["irradiance_wm2"]},
                    ml_score=round(score, 4),
                ))

        for site in self.simulator.sites:
            for inv in site.inverters:
                if inv.id in quarantined:
                    continue
                latest = self.simulator.latest.get(inv.id)
                last_ts = datetime.fromisoformat(latest["ts"]) if latest else None
                hit = rules.check_silent(inv.id, site.id, last_ts, ts, self.interval, self.settings)
                if hit:
                    candidates.append(hit)

        commands = session.scalars(select(Command).where(Command.ts == ts, Command.is_write.is_(True))).all()
        for cmd in commands:
            candidates.extend(self._command_candidates(session, cmd))

        for c in candidates:
            self._raise(session, c, ts)

    def on_commands(self, session: Session, commands: list[Command]) -> None:
        """Commands injected outside the simulator loop (attacks, responses)."""
        session.flush()
        for cmd in commands:
            for c in self._command_candidates(session, cmd):
                self._raise(session, c, cmd.ts)

    def on_integrity_failures(self, problems: list[dict], now: datetime) -> None:
        with db.write_session() as session:
            for p in problems:
                self._raise(session, rules.integrity_candidate(p), now)
        self.flush()

    def flush(self) -> None:
        """Publish alerts raised since the last flush (call after commit)."""
        with self._lock:
            pending, self._pending = self._pending, []
        for alert in pending:
            self._publish({"type": "alert", "alert": alert})

    def discard_pending(self) -> None:
        with self._lock:
            self._pending = []

    # ---- internals ----------------------------------------------------------

    def _command_candidates(self, session: Session, cmd: Command) -> list[Candidate]:
        if not cmd.is_write:
            return []
        out = []
        hit = rules.check_unauthorized_command(cmd, self.allowlists[cmd.site_id], self.settings)
        if hit:
            out.append(hit)
        window_start = cmd.ts - timedelta(minutes=self.settings.flood_window_minutes)
        count = session.scalar(
            select(func.count()).select_from(Command).where(
                Command.site_id == cmd.site_id, Command.is_write.is_(True),
                Command.ts > window_start, Command.ts <= cmd.ts,
            )
        )
        hit = rules.check_flood(cmd, count, self.settings)
        if hit:
            out.append(hit)
        return out

    def _raise(self, session: Session, c: Candidate, detected_at: datetime) -> Alert | None:
        existing = session.scalars(
            select(Alert).where(
                Alert.site_id == c.site_id, Alert.device_id == c.device_id,
                Alert.rule_id == c.rule_id, Alert.status != "resolved",
            ).limit(1)
        ).first()
        if existing is not None:
            evidence = dict(existing.evidence)
            evidence["occurrences"] = evidence.get("occurrences", 1) + 1
            evidence["last_seen"] = c.evidence.get("ts", detected_at.isoformat(timespec="seconds"))
            existing.evidence = evidence
            return None

        attack = session.scalars(
            select(Attack).where(Attack.active.is_(True), Attack.device_id == c.device_id)
            .order_by(Attack.started_at).limit(1)
        ).first()
        meta = RULES[c.rule_id]
        alert = Alert(
            site_id=c.site_id, device_id=c.device_id, rule_id=c.rule_id, severity=meta["severity"],
            title=c.title, description=c.description, evidence={**c.evidence, "occurrences": 1},
            recommended_action=meta["action"], mitre_technique=meta["mitre"], ml_score=c.ml_score,
            status="open", detected_at=detected_at, detected_real=utcnow(),
            attack_id=attack.id if attack else None,
            attack_started_at=attack.started_at if attack else None,
            attack_started_real=attack.started_real if attack else None,
        )
        session.add(alert)
        session.flush()
        with self._lock:
            self._pending.append(alert_dict(alert))
        return alert
