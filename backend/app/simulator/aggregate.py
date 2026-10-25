"""Roll per-inverter readings up to one site-level point per timestamp."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from . import physics


def with_expected(reading: dict, capacity_kw: float) -> dict:
    """Attach the physics-expected power so charts can show reported vs possible."""
    expected = physics.expected_power_kw(reading["irradiance_wm2"], reading["ambient_temp_c"], capacity_kw)
    return {**reading, "expected_kw": round(expected, 2)}


def aggregate_site_points(readings: Iterable[dict], capacities: dict[str, float]) -> list[dict]:
    by_ts: dict[str, list[dict]] = defaultdict(list)
    for r in readings:
        by_ts[r["ts"]].append(with_expected(r, capacities[r["device_id"]]))

    points = []
    for ts in sorted(by_ts):
        rows = by_ts[ts]
        n = len(rows)
        points.append({
            "ts": ts,
            "ac_power_kw": round(sum(r["ac_power_kw"] for r in rows), 2),
            "expected_kw": round(sum(r["expected_kw"] for r in rows), 2),
            "irradiance_wm2": round(sum(r["irradiance_wm2"] for r in rows) / n, 1),
            "ambient_temp_c": round(sum(r["ambient_temp_c"] for r in rows) / n, 1),
            "ac_voltage_v": round(sum(r["ac_voltage_v"] for r in rows) / n, 1),
            "frequency_hz": round(sum(r["frequency_hz"] for r in rows) / n, 3),
            "temperature_c": round(max(r["temperature_c"] for r in rows), 1),
            "energy_today_kwh": round(sum(r["energy_today_kwh"] for r in rows), 2),
            "reporting_devices": n,
        })
    return points
