"""Demo attack injectors, SOC response actions and reset.

Lock order everywhere: simulator lock, then the DB write lock (the simulator
takes them in that order during catch-up, so doing the same here avoids
deadlocks).
"""
from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update

from .. import db
from ..api.serializers import alert_dict, attack_dict
from ..detection.engine import utcnow
from ..models import Alert, Attack, Command, Device, Finding, Scan, Telemetry
from ..scanner.inventory import INVENTORY
from ..simulator.commands import make_command

if TYPE_CHECKING:
    from ..runtime import Runtime

ATTACKS: dict[str, dict] = {
    "spoof_night_generation": {
        "site_id": "kibwezi", "device_id": "KIB-INV-02", "label": "Spoof night generation",
        "expects": ["R1", "ML-ANOMALY"],
        "story": "A compromised data logger reports output at night to pad generation figures.",
    },
    "inflate_output": {
        "site_id": "kibwezi", "device_id": "KIB-INV-03", "label": "Inflate output (+30%)",
        "expects": ["R2", "ML-ANOMALY"],
        "story": "Reported power is ramped up 30%: carbon-credit fraud that is validly signed at the source.",
    },
    "unauthorized_shutdown": {
        "site_id": "naivasha", "device_id": "NAI-INV-01", "label": "Unauthorized shutdown",
        "expects": ["R3"], "source_ip": "203.0.113.45",
        "story": "An unknown host sends a Modbus SHUTDOWN to a mini-grid inverter.",
    },
    "command_flood": {
        "site_id": "thika", "device_id": "THK-INV-02", "label": "Command flood",
        "expects": ["R4", "R3"], "source_ip": "198.51.100.23",
        "story": "20 SET_POWER_LIMIT writes in seconds throttle the inverter to near zero.",
    },
    "tamper_stored_record": {
        "site_id": "kibwezi", "device_id": "KIB-INV-01", "label": "Tamper stored record",
        "expects": ["R7"],
        "story": "Someone with database access edits a stored reading without the device's key.",
    },
    "device_offline": {
        "site_id": "thika", "device_id": "THK-INV-03", "label": "Device offline",
        "expects": ["R5"],
        "story": "An inverter's telemetry link is cut.",
    },
}

ACTIONS_BY_RULE = {
    "R1": ["isolate"], "R2": ["isolate"], "ML-ANOMALY": ["isolate"], "R5": ["isolate"], "R6": ["isolate"],
    "R3": ["block_ip"], "R4": ["block_ip"], "R7": ["restore_record"],
}


class AttackError(ValueError):
    pass


class AttackService:
    def __init__(self, rt: "Runtime"):
        self.rt = rt
        self.blocklist: set[str] = set()
        self._undo: dict[int, Callable[[], None]] = {}

    @property
    def sim(self):
        return self.rt.simulator

    # ---- launching ----------------------------------------------------------

    def catalog(self) -> list[dict]:
        return [{"type": t, **spec} for t, spec in ATTACKS.items()]

    def launch(self, attack_type: str) -> dict:
        if attack_type not in ATTACKS:
            raise AttackError(f"unknown attack {attack_type}")
        spec = ATTACKS[attack_type]
        with self.sim.lock:
            jumped_to = self._prepare_clock(attack_type)
            try:
                with db.write_session() as s:
                    self._stop(s, lambda a: a.type == attack_type)
                    now = self.rt.clock.now()
                    attack = Attack(type=attack_type, site_id=spec["site_id"], device_id=spec["device_id"],
                                    started_at=now, started_real=utcnow(), active=True,
                                    params={k: spec[k] for k in ("source_ip",) if k in spec}, original={})
                    s.add(attack)
                    s.flush()
                    note = getattr(self, f"_launch_{attack_type}")(s, attack, now)
                    result = attack_dict(attack)
            except Exception:
                self.rt.engine.discard_pending()
                raise
        self.rt.engine.flush()
        return {**result, "label": spec["label"], "expects": spec["expects"], "story": spec["story"],
                "jumped_to": jumped_to, "note": note}

    def _prepare_clock(self, attack_type: str) -> str | None:
        """Night attacks need night, inflation needs strong sun: jump forward if needed."""
        hour = self.rt.clock.now().hour
        target = None
        if attack_type == "spoof_night_generation" and 5 <= hour < 19:
            target = 1.0
        elif attack_type == "inflate_output" and not 9 <= hour < 15:
            target = 10.0
        if target is None:
            return None
        self.rt.clock.jump_to_hour(target)
        self.sim.catch_up()
        self.rt.engine.flush()
        return self.rt.clock.now().isoformat(timespec="seconds")

    def _add_modifier(self, attack: Attack, fn) -> None:
        mods = self.sim.modifiers.setdefault(attack.device_id, [])
        mods.append(fn)

        def undo():
            if fn in mods:
                mods.remove(fn)
        self._undo[attack.id] = undo

    def _capacity(self, device_id: str) -> float:
        return self.rt.engine.capacities[device_id]

    def _launch_spoof_night_generation(self, s, attack: Attack, now: datetime) -> str:
        cap, rng = self._capacity(attack.device_id), random.Random(attack.id)

        def spoof(r: dict, _ts) -> dict:
            p = round(cap * rng.uniform(0.55, 0.62), 2)
            return {**r, "ac_power_kw": p, "status": "producing", "dc_voltage_v": round(rng.uniform(640, 660), 1),
                    "temperature_c": round(r["ambient_temp_c"] + 3 + 18 * p / cap, 1)}
        self._add_modifier(attack, spoof)
        return "Spoofed readings start with the next interval."

    def _launch_inflate_output(self, s, attack: Attack, now: datetime) -> str:
        step = {"n": 0}

        def inflate(r: dict, _ts) -> dict:
            step["n"] += 1
            factor = 1 + min(0.30, 0.08 * step["n"])
            return {**r, "ac_power_kw": round(r["ac_power_kw"] * factor, 2)}
        self._add_modifier(attack, inflate)
        return "Output ramps +8% per reading up to +30%."

    def _inject(self, s, attack: Attack, commands: list[dict]) -> list[Command]:
        rows = [Command(**c) for c in commands]
        s.add_all(rows)
        if attack.params.get("source_ip") in self.blocklist:
            return rows  # dropped at the firewall: logged, never reaches the device
        self.rt.engine.on_commands(s, rows)
        return rows

    def _blocked(self, s, attack: Attack) -> bool:
        if attack.params.get("source_ip") not in self.blocklist:
            return False
        attack.active, attack.ended_at = False, attack.started_at
        attack.params = {**attack.params, "blocked": True}
        return True

    def _launch_unauthorized_shutdown(self, s, attack: Attack, now: datetime) -> str:
        ip = attack.params["source_ip"]
        self._inject(s, attack, [make_command(
            attack.site_id, attack.device_id, now, "SHUTDOWN", source_ip=ip, user="unknown",
            protocol="Modbus/TCP", params={"register": 40100, "value": 0, "blocked": ip in self.blocklist},
            attack_id=attack.id,
        )])
        if self._blocked(s, attack):
            return f"{ip} is blocked: the command was dropped at the firewall."

        def shutdown(r: dict, _ts) -> dict:
            return {**r, "ac_power_kw": 0.0, "dc_voltage_v": 0.0, "status": "shutdown"}
        self._add_modifier(attack, shutdown)
        return "Inverter output drops to 0 from the next interval."

    def _launch_command_flood(self, s, attack: Attack, now: datetime) -> str:
        ip, rng = attack.params["source_ip"], random.Random(attack.id)
        limits = [rng.randint(0, 10) for _ in range(20)]
        self._inject(s, attack, [
            make_command(attack.site_id, attack.device_id, now - timedelta(seconds=8 * (19 - i)), "SET_POWER_LIMIT",
                         source_ip=ip, user="unknown", protocol="Modbus/TCP",
                         params={"limit_pct": limit, "blocked": ip in self.blocklist}, attack_id=attack.id)
            for i, limit in enumerate(limits)
        ])
        if self._blocked(s, attack):
            return f"{ip} is blocked: all 20 commands were dropped at the firewall."
        cap, limit = self._capacity(attack.device_id), limits[-1]
        attack.params = {**attack.params, "limit_pct": limit}

        def throttle(r: dict, _ts) -> dict:
            capped = min(r["ac_power_kw"], round(cap * limit / 100, 2))
            return {**r, "ac_power_kw": capped, "status": "limited" if capped > 0 else "standby"}
        self._add_modifier(attack, throttle)
        return f"Inverter throttled to {limit}% of capacity."

    def _launch_tamper_stored_record(self, s, attack: Attack, now: datetime) -> str:
        row = s.scalars(
            select(Telemetry).where(Telemetry.device_id == attack.device_id)
            .order_by(Telemetry.seq.desc()).offset(2).limit(1)
        ).one()
        tampered = round(row.ac_power_kw * 1.3 + 60, 1)
        attack.original = {"telemetry_id": row.id, "seq": row.seq, "ac_power_kw": row.ac_power_kw}
        attack.params = {**attack.params, "seq": row.seq, "tampered_kw": tampered}
        row.ac_power_kw = tampered  # no re-signing: the attacker doesn't hold the edge key
        return f"Record #{row.seq} changed from {attack.original['ac_power_kw']:.1f} kW to {tampered:.1f} kW."

    def _launch_device_offline(self, s, attack: Attack, now: datetime) -> str:
        self.sim.offline.add(attack.device_id)
        self._undo[attack.id] = lambda: self.sim.offline.discard(attack.device_id)
        return "Telemetry stops; R5 fires after 2 silent intervals."

    # ---- stopping, response, reset -------------------------------------------

    def _stop(self, s, predicate) -> list[Attack]:
        stopped = []
        for attack in s.scalars(select(Attack).where(Attack.active.is_(True))):
            if predicate(attack):
                attack.active, attack.ended_at = False, self.rt.clock.now()
                undo = self._undo.pop(attack.id, None)
                if undo:
                    undo()
                stopped.append(attack)
        return stopped

    def _resolve(self, alerts: list[Alert]) -> list[dict]:
        now, real = self.rt.clock.now(), utcnow()
        for a in alerts:
            a.status, a.resolved_at, a.resolved_real = "resolved", now, real
        return [alert_dict(a) for a in alerts]

    def respond(self, alert_id: int, action: str) -> dict:
        with self.sim.lock:
            with db.write_session() as s:
                alert = s.get(Alert, alert_id)
                if alert is None:
                    raise LookupError(f"alert {alert_id} not found")
                if action not in ACTIONS_BY_RULE.get(alert.rule_id, []):
                    raise AttackError(f"{action} is not available for {alert.rule_id}")
                result = getattr(self, f"_respond_{action}")(s, alert)
            self.rt.engine.flush()
        for a in result["resolved"]:
            self.rt.ws.publish({"type": "alert_updated", "alert": a})
        return result

    def _respond_block_ip(self, s, alert: Alert) -> dict:
        ip = alert.evidence.get("source_ip")
        if not ip:
            raise AttackError("alert has no source IP")
        self.blocklist.add(ip)
        stopped = self._stop(s, lambda a: a.params.get("source_ip") == ip)
        soc_ip, now = self.rt.settings.soc_ips[0], self.rt.clock.now()
        restore = []
        for attack in stopped:  # SOC restores the device it had been told to do
            cmd = "START" if attack.type == "unauthorized_shutdown" else "SET_POWER_LIMIT"
            params = {"reason": "SOC recovery"} | ({"limit_pct": 100} if cmd == "SET_POWER_LIMIT" else {})
            restore.append(Command(**make_command(attack.site_id, attack.device_id, now, cmd, source_ip=soc_ip,
                                                  user="soc-responder", protocol="Modbus/TCP", params=params)))
        s.add_all(restore)
        self.rt.engine.on_commands(s, restore)
        open_alerts = [a for a in s.scalars(select(Alert).where(Alert.status != "resolved"))
                       if a.evidence.get("source_ip") == ip]
        return {"action": "block_ip", "ip": ip, "blocklist": sorted(self.blocklist),
                "restored_devices": [a.device_id for a in stopped], "resolved": self._resolve(open_alerts)}

    def _respond_isolate(self, s, alert: Alert) -> dict:
        device = s.get(Device, alert.device_id)
        device.quarantined = True
        self._stop(s, lambda a: a.device_id == device.id)
        open_alerts = s.scalars(select(Alert).where(Alert.device_id == device.id, Alert.status != "resolved")).all()
        return {"action": "isolate", "device_id": device.id, "resolved": self._resolve(open_alerts)}

    def _respond_restore_record(self, s, alert: Alert) -> dict:
        row = s.get(Telemetry, alert.evidence["telemetry_id"])
        signed = json.loads(row.payload)
        for f in ("ac_power_kw", "dc_voltage_v", "ac_voltage_v", "frequency_hz", "temperature_c",
                  "energy_today_kwh", "irradiance_wm2", "ambient_temp_c", "status"):
            setattr(row, f, signed[f])
        self._stop(s, lambda a: a.type == "tamper_stored_record" and a.device_id == row.device_id)
        s.flush()
        report = self.rt.monitor.full_check(s, row.device_id)
        open_alerts = s.scalars(select(Alert).where(Alert.device_id == row.device_id, Alert.rule_id == "R7",
                                                    Alert.status != "resolved")).all()
        return {"action": "restore_record", "seq": row.seq, "restored_kw": row.ac_power_kw,
                "integrity": {k: report[k] for k in ("ok", "integrity_pct")}, "resolved": self._resolve(open_alerts)}

    def reset(self) -> dict:
        self.rt.scans.cancel_all()
        with self.sim.lock:
            with db.write_session() as s:
                for attack in s.scalars(select(Attack).where(Attack.type == "tamper_stored_record")):
                    if attack.original.get("telemetry_id"):
                        s.execute(update(Telemetry).where(Telemetry.id == attack.original["telemetry_id"])
                                  .values(ac_power_kw=attack.original["ac_power_kw"]))
                counts = {
                    "alerts": s.execute(delete(Alert)).rowcount,
                    "attack_commands": s.execute(delete(Command).where(Command.attack_id.is_not(None))).rowcount,
                    "attacks": s.execute(delete(Attack)).rowcount,
                    "findings": s.execute(delete(Finding)).rowcount,
                    "scans": s.execute(delete(Scan)).rowcount,
                }
                for device in s.scalars(select(Device)):
                    for key, value in INVENTORY[device.id].items():
                        setattr(device, key, value)
                    device.quarantined = False
            for undo in self._undo.values():
                undo()
            self._undo.clear()
            self.sim.modifiers.clear()
            self.sim.offline.clear()
            self.blocklist.clear()
            self.rt.engine.discard_pending()
            with db.read_session() as s:
                self.rt.monitor.full_check_all(s)
        self.rt.ws.publish({"type": "reset"})
        return {"ok": True, "cleared": counts, **self.rt.sim_status()}
