"""Deterministic detection rules R1–R7. Each check returns a Candidate or None."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import Settings
from ..simulator import physics

RULES: dict[str, dict] = {
    "R1": {
        "name": "Night generation",
        "severity": "high",
        "mitre": "T0856 Spoof Reporting Message",
        "action": "Treat this device's output as untrusted. Isolate the inverter's data link, check the data logger "
                  "for unauthorized firmware or configuration changes, and exclude the readings from generation reports.",
    },
    "R2": {
        "name": "Physics mismatch",
        "severity": "high",
        "mitre": "T0856 Spoof Reporting Message",
        "action": "Reported output exceeds what the measured irradiance allows. Quarantine the readings from "
                  "investor and carbon reporting, cross-check against the revenue meter, and audit the device.",
    },
    "R3": {
        "name": "Unauthorized command",
        "severity": "critical",
        "mitre": "T0855 Unauthorized Command Message",
        "action": "Block the source IP at the site firewall, restart the affected device from the SOC, rotate "
                  "operator credentials, and review how the source reached the OT network.",
    },
    "R4": {
        "name": "Command flood",
        "severity": "high",
        "mitre": "T0814 Denial of Service",
        "action": "Rate-limit or block the source, verify the device's current setpoints, and restore the "
                  "approved power limit.",
    },
    "R5": {
        "name": "Device silent",
        "severity": "medium",
        "mitre": "T0814 Denial of Service",
        "action": "Check power and network to the device and its data logger. If the link is up, inspect for "
                  "a jammed or reconfigured communication interface.",
    },
    "R6": {
        "name": "Grid frequency out of range",
        "severity": "medium",
        "mitre": "T0831 Manipulation of Control",
        "action": "Confirm against the utility's frequency feed. If the grid is normal, the inverter's control "
                  "settings or measurements may have been manipulated.",
    },
    "R7": {
        "name": "Integrity failure",
        "severity": "critical",
        "mitre": "T0856 Spoof Reporting Message (stored data tampering)",
        "action": "Stored telemetry no longer matches what the device signed. Freeze report exports, restore the "
                  "record from the signed payload, and audit database access.",
    },
    "ML-ANOMALY": {
        "name": "ML anomaly",
        "severity": "medium",
        "mitre": "T0856 Spoof Reporting Message",
        "action": "The reading is statistically unlike this site's normal behaviour at this hour. Review the "
                  "explanation below and correlate with rule alerts on the same device.",
    },
}


@dataclass
class Candidate:
    rule_id: str
    site_id: str
    device_id: str | None
    title: str
    description: str
    evidence: dict = field(default_factory=dict)
    ml_score: float | None = None


def check_night_generation(reading: dict, capacity_kw: float, s: Settings) -> Candidate | None:
    power, irr = reading["ac_power_kw"], reading["irradiance_wm2"]
    if irr < s.night_irradiance_wm2 and power > s.night_power_ratio * capacity_kw:
        return Candidate(
            "R1", reading["site_id"], reading["device_id"],
            f"{reading['device_id']} reports {power:.1f} kW in the dark",
            f"Power is {power / capacity_kw:.0%} of capacity while irradiance is {irr:.0f} W/m². "
            "Solar inverters cannot generate without sunlight; the reading is spoofed.",
            {"ac_power_kw": power, "irradiance_wm2": irr, "capacity_kw": capacity_kw, "ts": reading["ts"],
             "threshold": f"> {s.night_power_ratio:.0%} of capacity below {s.night_irradiance_wm2:.0f} W/m²"},
        )
    return None


def check_physics(reading: dict, capacity_kw: float, s: Settings) -> Candidate | None:
    expected = physics.expected_power_kw(reading["irradiance_wm2"], reading["ambient_temp_c"], capacity_kw)
    power = reading["ac_power_kw"]
    if expected > s.physics_min_expected_ratio * capacity_kw and power > s.physics_mismatch_ratio * expected:
        ratio = power / expected
        return Candidate(
            "R2", reading["site_id"], reading["device_id"],
            f"{reading['device_id']} reports {ratio - 1:.0%} more power than physically possible",
            f"Measured irradiance of {reading['irradiance_wm2']:.0f} W/m² supports about {expected:.1f} kW, "
            f"but the device reports {power:.1f} kW. Inflated output like this would overstate generation "
            "in investor and carbon-credit reports.",
            {"ac_power_kw": power, "expected_kw": round(expected, 1), "ratio": round(ratio, 3),
             "irradiance_wm2": reading["irradiance_wm2"], "ambient_temp_c": reading["ambient_temp_c"],
             "ts": reading["ts"], "threshold": f"> {s.physics_mismatch_ratio:.0%} of expected"},
        )
    return None


def check_frequency(reading: dict, s: Settings) -> Candidate | None:
    f = reading["frequency_hz"]
    if not (s.freq_min_hz <= f <= s.freq_max_hz):
        return Candidate(
            "R6", reading["site_id"], reading["device_id"],
            f"{reading['device_id']} grid frequency {f:.2f} Hz",
            f"Frequency is outside the {s.freq_min_hz}–{s.freq_max_hz} Hz operating band.",
            {"frequency_hz": f, "ts": reading["ts"]},
        )
    return None


def check_unauthorized_command(cmd, allowlist: list[str], s: Settings) -> Candidate | None:
    if not cmd.is_write:
        return None
    reasons = []
    if cmd.source_ip not in allowlist:
        reasons.append(f"source {cmd.source_ip} is not on the site allowlist")
    in_window = s.maintenance_start_hour <= cmd.ts.hour < s.maintenance_end_hour
    if not in_window and cmd.source_ip not in s.soc_ips:  # the SOC may respond at any hour
        reasons.append(f"issued at {cmd.ts:%H:%M}, outside the "
                       f"{s.maintenance_start_hour:02d}:00–{s.maintenance_end_hour:02d}:00 maintenance window")
    if not reasons:
        return None
    return Candidate(
        "R3", cmd.site_id, cmd.device_id,
        f"Unauthorized {cmd.command} sent to {cmd.device_id}",
        f"A {cmd.command} write command arrived via {cmd.protocol} from user '{cmd.user}': "
        + "; ".join(reasons) + ".",
        {"command": cmd.command, "params": cmd.params, "source_ip": cmd.source_ip, "user": cmd.user,
         "protocol": cmd.protocol, "ts": cmd.ts.isoformat(timespec="seconds"), "reasons": reasons,
         "command_id": cmd.id},
    )


def check_flood(cmd, write_count: int, s: Settings) -> Candidate | None:
    if write_count <= s.flood_write_threshold:
        return None
    return Candidate(
        "R4", cmd.site_id, cmd.device_id,
        f"Command flood: {write_count} writes to {cmd.site_id} in {s.flood_window_minutes} min",
        f"{write_count} write commands reached the site within {s.flood_window_minutes} sim-minutes "
        f"(threshold {s.flood_write_threshold}). Latest: {cmd.command} from {cmd.source_ip}.",
        {"write_count": write_count, "window_minutes": s.flood_window_minutes, "source_ip": cmd.source_ip,
         "last_command": cmd.command, "ts": cmd.ts.isoformat(timespec="seconds")},
    )


def check_silent(device_id: str, site_id: str, last_ts: datetime | None, now: datetime,
                 interval: timedelta, s: Settings) -> Candidate | None:
    if last_ts is None or now - last_ts <= s.silent_intervals * interval:
        return None
    missed = int((now - last_ts) / interval)
    return Candidate(
        "R5", site_id, device_id,
        f"{device_id} has gone silent",
        f"No telemetry for {missed} intervals (last reading {last_ts:%H:%M}).",
        {"last_seen": last_ts.isoformat(timespec="seconds"), "missed_intervals": missed},
    )


def integrity_candidate(problem: dict) -> Candidate:
    columns = next((p for p in problem["problems"] if p["check"] == "columns"), None)
    return Candidate(
        "R7", problem["site_id"], problem["device_id"],
        f"Tampered telemetry record on {problem['device_id']}",
        problem["summary"],
        {"seq": problem["seq"], "telemetry_id": problem["telemetry_id"], "ts": problem["ts"],
         "checks_failed": [p["check"] for p in problem["problems"]],
         "fields": columns["fields"] if columns else []},
    )
