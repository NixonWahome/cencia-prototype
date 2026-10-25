"""Chain verification and the background integrity monitor.

Every record is checked on its own merits:
  signature  - Ed25519 signature over the stored canonical payload
  linkage    - prev_hash equals the predecessor's stored hash, seq is contiguous
  hash       - stored hash equals sha256(prev_hash + payload + signature)
  columns    - parsed columns used by charts equal the signed payload values
A column-only edit therefore breaks exactly one record; deleting or rewriting
a record also breaks its successor's linkage.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Device, Telemetry
from .chain import GENESIS_HASH, chain_hash
from .keys import load_public_key
from .signing import verify_signature

# field -> (unit, decimals) for human-readable "signed X, stored Y" messages
NUMERIC_FIELDS: dict[str, tuple[str, int]] = {
    "ac_power_kw": ("kW", 1),
    "dc_voltage_v": ("V", 1),
    "ac_voltage_v": ("V", 1),
    "frequency_hz": ("Hz", 3),
    "temperature_c": ("°C", 1),
    "energy_today_kwh": ("kWh", 1),
    "irradiance_wm2": ("W/m²", 1),
    "ambient_temp_c": ("°C", 1),
}
MAX_BROKEN_REPORTED = 50


def _fmt(value, unit: str, decimals: int) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f} {unit}"
    return f"{value!r}"


def compare_columns(row: Telemetry, signed: dict) -> list[dict]:
    mismatches = []
    for name, (unit, decimals) in NUMERIC_FIELDS.items():
        signed_v, stored_v = signed.get(name), getattr(row, name)
        same = (
            isinstance(signed_v, (int, float))
            and stored_v is not None
            and math.isclose(signed_v, stored_v, rel_tol=0, abs_tol=1e-6)
        )
        if not same:
            mismatches.append({
                "field": name,
                "signed": signed_v,
                "stored": stored_v,
                "message": f"{name}: signed {_fmt(signed_v, unit, decimals)}, stored {_fmt(stored_v, unit, decimals)}",
            })
    for name, stored_v in (
        ("status", row.status),
        ("device_id", row.device_id),
        ("seq", row.seq),
        ("ts", row.ts.isoformat(timespec="seconds")),
    ):
        if signed.get(name) != stored_v:
            mismatches.append({
                "field": name,
                "signed": signed.get(name),
                "stored": stored_v,
                "message": f"{name}: signed {signed.get(name)!r}, stored {stored_v!r}",
            })
    return mismatches


def check_record(row: Telemetry, expected_prev_hash: str, expected_seq: int, public_key) -> list[dict]:
    problems: list[dict] = []
    if not verify_signature(public_key, row.payload, row.signature):
        problems.append({
            "check": "signature",
            "message": "Signature does not match the device's public key: the signed payload was altered or signed by another key.",
        })
    if row.prev_hash != expected_prev_hash or row.seq != expected_seq:
        problems.append({
            "check": "linkage",
            "message": (
                f"Chain link broken: expected seq {expected_seq} after hash {expected_prev_hash[:12]}…, "
                f"found seq {row.seq} pointing to {row.prev_hash[:12]}…. A record was removed, inserted or rewritten."
            ),
        })
    if chain_hash(row.prev_hash, row.payload, row.signature) != row.hash:
        problems.append({
            "check": "hash",
            "message": "Stored record hash does not match its contents.",
        })
    try:
        signed = json.loads(row.payload)
    except ValueError:
        problems.append({"check": "payload", "message": "Signed payload is not valid JSON."})
        return problems
    mismatches = compare_columns(row, signed)
    if mismatches:
        problems.append({
            "check": "columns",
            "message": "Stored values differ from what the device signed: "
            + "; ".join(m["message"] for m in mismatches),
            "fields": mismatches,
        })
    return problems


@dataclass
class DeviceReport:
    device_id: str
    from_seq: int
    checked: int = 0
    last_seq: int = 0
    chain_head: str | None = None
    broken: dict[int, dict] = field(default_factory=dict)  # seq -> broken record

    @property
    def ok(self) -> bool:
        return not self.broken

    def to_dict(self) -> dict:
        broken = [self.broken[s] for s in sorted(self.broken)]
        return {
            "device_id": self.device_id,
            "ok": self.ok,
            "checked": self.checked,
            "verified": self.checked - len(self.broken),
            "integrity_pct": _pct(self.checked, len(self.broken)),
            "chain_head": self.chain_head,
            "first_broken": broken[0] if broken else None,
            "broken": broken[:MAX_BROKEN_REPORTED],
            "broken_count": len(broken),
        }


def _pct(total: int, broken: int) -> float:
    return 100.0 if total == 0 else round((total - broken) / total * 100, 3)


def verify_device(session: Session, device_id: str, from_seq: int = 1) -> DeviceReport:
    device = session.get(Device, device_id)
    if device is None or device.public_key is None:
        raise ValueError(f"{device_id} has no signing key")
    public_key = load_public_key(device.public_key)

    from_seq = max(1, from_seq)
    expected_prev = GENESIS_HASH
    if from_seq > 1:
        expected_prev = session.scalar(
            select(Telemetry.hash).where(Telemetry.device_id == device_id, Telemetry.seq == from_seq - 1)
        ) or GENESIS_HASH

    report = DeviceReport(device_id=device_id, from_seq=from_seq)
    expected_seq = from_seq
    rows = session.scalars(
        select(Telemetry)
        .where(Telemetry.device_id == device_id, Telemetry.seq >= from_seq)
        .order_by(Telemetry.seq)
    )
    for row in rows:
        problems = check_record(row, expected_prev, expected_seq, public_key)
        if problems:
            report.broken[row.seq] = {
                "telemetry_id": row.id,
                "seq": row.seq,
                "ts": row.ts.isoformat(timespec="seconds"),
                "hash": row.hash,
                "problems": problems,
                "summary": problems[0]["message"],
            }
        report.checked += 1
        report.last_seq = row.seq
        report.chain_head = row.hash
        expected_prev = row.hash
        expected_seq = row.seq + 1
    return report


@dataclass
class DeviceIntegrity:
    device_id: str
    site_id: str
    total: int = 0
    last_seq: int = 0
    chain_head: str | None = None
    broken: dict[int, dict] = field(default_factory=dict)
    last_checked: str | None = None

    def to_dict(self) -> dict:
        broken = [self.broken[s] for s in sorted(self.broken)]
        return {
            "device_id": self.device_id,
            "site_id": self.site_id,
            "ok": not broken,
            "total": self.total,
            "verified": self.total - len(broken),
            "integrity_pct": _pct(self.total, len(broken)),
            "chain_head": self.chain_head,
            "first_broken": broken[0] if broken else None,
            "broken_count": len(broken),
            "last_checked": self.last_checked,
        }


class IntegrityMonitor:
    """Keeps a live integrity picture per device.

    `full_check` re-verifies a whole chain (the Verify button). `incremental`
    is the background pass: it checks new records and re-checks the most
    recent window, returning only newly broken records so R7 fires once.
    """

    def __init__(self, devices: list[tuple[str, str]], recent_window: int):
        self._lock = threading.Lock()
        self._recent_window = recent_window
        self._state = {d: DeviceIntegrity(device_id=d, site_id=s) for d, s in devices}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def full_check(self, session: Session, device_id: str) -> dict:
        report = verify_device(session, device_id, 1)
        with self._lock:
            state = self._state[device_id]
            state.total = report.checked
            state.last_seq = report.last_seq
            state.chain_head = report.chain_head
            state.broken = dict(report.broken)
            state.last_checked = self._now()
        return {**report.to_dict(), "site_id": state.site_id}

    def full_check_all(self, session: Session) -> None:
        for device_id in list(self._state):
            self.full_check(session, device_id)

    def incremental(self, session: Session) -> list[dict]:
        newly_broken: list[dict] = []
        for device_id, state in self._state.items():
            from_seq = max(1, state.last_seq - self._recent_window + 1)
            report = verify_device(session, device_id, from_seq)
            if report.checked == 0:
                continue
            with self._lock:
                for seq in range(from_seq, report.last_seq + 1):
                    if seq in report.broken:
                        if seq not in state.broken:
                            newly_broken.append({**report.broken[seq], "device_id": device_id, "site_id": state.site_id})
                        state.broken[seq] = report.broken[seq]
                    else:
                        state.broken.pop(seq, None)
                state.total = session.scalar(
                    select(func.count()).select_from(Telemetry).where(Telemetry.device_id == device_id)
                )
                state.last_seq = report.last_seq
                state.chain_head = report.chain_head
                state.last_checked = self._now()
        return newly_broken

    def device(self, device_id: str) -> dict | None:
        with self._lock:
            state = self._state.get(device_id)
            return state.to_dict() if state else None

    def broken_records(self, device_id: str) -> list[dict]:
        with self._lock:
            state = self._state.get(device_id)
            return [state.broken[s] for s in sorted(state.broken)] if state else []

    def devices(self, site_id: str | None = None) -> list[dict]:
        with self._lock:
            return [s.to_dict() for s in self._state.values() if site_id in (None, s.site_id)]

    def site_summary(self, site_id: str | None = None) -> dict:
        devices = self.devices(site_id)
        total = sum(d["total"] for d in devices)
        broken = sum(d["broken_count"] for d in devices)
        return {
            "total": total,
            "verified": total - broken,
            "integrity_pct": _pct(total, broken),
            "ok": broken == 0,
        }
