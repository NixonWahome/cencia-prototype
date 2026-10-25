"""Normal operator command traffic. Attacks inject their own commands."""
from __future__ import annotations

import random
from datetime import datetime

from .sites import SiteSpec

WRITE_COMMANDS = frozenset({"SET_POWER_LIMIT", "FIRMWARE_UPDATE", "SHUTDOWN", "START"})

READ_PROBABILITY = 0.5
POWER_LIMIT_PROBABILITY = 0.03
FIRMWARE_PROBABILITY = 0.004


def make_command(site_id: str, device_id: str, ts: datetime, command: str, *, source_ip: str,
                 user: str, protocol: str, params: dict | None = None, attack_id: int | None = None) -> dict:
    return {
        "site_id": site_id,
        "device_id": device_id,
        "ts": ts,
        "command": command,
        "params": params or {},
        "source_ip": source_ip,
        "user": user,
        "protocol": protocol,
        "is_write": command in WRITE_COMMANDS,
        "attack_id": attack_id,
    }


class CommandGenerator:
    def __init__(self, rng: random.Random, maintenance_start_hour: int, maintenance_end_hour: int):
        self.rng = rng
        self.window = (maintenance_start_hour, maintenance_end_hour)

    def generate(self, site: SiteSpec, ts: datetime) -> list[dict]:
        rng = self.rng
        gateway_ip, ops_ip = site.allowlist[0], site.allowlist[min(1, len(site.allowlist) - 1)]
        out: list[dict] = []

        if rng.random() < READ_PROBABILITY:
            inv = rng.choice(site.inverters)
            out.append(make_command(
                site.id, inv.id, ts, "READ",
                source_ip=gateway_ip, user="scada-svc", protocol="Modbus/TCP",
                params={"register": rng.choice(["ac_power", "energy_today", "status", "temperature"])},
            ))

        if self.window[0] <= ts.hour < self.window[1]:
            if rng.random() < POWER_LIMIT_PROBABILITY:
                inv = rng.choice(site.inverters)
                out.append(make_command(
                    site.id, inv.id, ts, "SET_POWER_LIMIT",
                    source_ip=ops_ip, user="ops-engineer", protocol="Modbus/TCP",
                    params={"limit_pct": 100, "reason": "re-assert export limit"},
                ))
            if site.other_device_ids and rng.random() < FIRMWARE_PROBABILITY:
                out.append(make_command(
                    site.id, rng.choice(site.other_device_ids), ts, "FIRMWARE_UPDATE",
                    source_ip=ops_ip, user="om-contractor", protocol="HTTPS",
                    params={"action": "check-for-update"},
                ))
        return out
