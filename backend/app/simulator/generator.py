"""Weather and inverter telemetry generation."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime

from . import physics
from .sites import InverterSpec

CLOUD_DIP_PROBABILITY = 0.06


@dataclass
class _Weather:
    dip_left: int = 0
    dip_depth: float = 1.0


class TelemetryGenerator:
    def __init__(self, rng: random.Random, interval_hours: float):
        self.rng = rng
        self.interval_hours = interval_hours
        self._weather: dict[str, _Weather] = {}
        self._energy: dict[str, tuple[date, float]] = {}

    def site_conditions(self, site_id: str, ts: datetime, ambient_base_c: float) -> tuple[float, float]:
        """Return (irradiance_wm2, ambient_temp_c) for a site at `ts`."""
        w = self._weather.setdefault(site_id, _Weather())
        if w.dip_left == 0 and self.rng.random() < CLOUD_DIP_PROBABILITY:
            w.dip_left = self.rng.randint(1, 4)
            w.dip_depth = self.rng.uniform(0.35, 0.75)
        factor = 1.0
        if w.dip_left > 0:
            factor = w.dip_depth
            w.dip_left -= 1
        irradiance = physics.clear_sky_irradiance(ts) * factor * (1 + self.rng.gauss(0, 0.01))
        ambient = physics.ambient_temp(ts, ambient_base_c) + self.rng.gauss(0, 0.3)
        return max(0.0, irradiance), ambient

    def inverter_reading(self, inv: InverterSpec, ts: datetime, irradiance: float, ambient: float) -> dict:
        rng = self.rng
        expected = physics.expected_power_kw(irradiance, ambient, inv.capacity_kw)
        power = min(inv.capacity_kw, max(0.0, expected * (1 + rng.gauss(0, 0.015))))
        if power < 0.5:
            power = 0.0
        ratio = power / inv.capacity_kw
        dc_voltage = 0.0 if power == 0 else 580 + 120 * min(irradiance, 1000) / 1000 + rng.gauss(0, 3)
        ac_voltage = inv.nominal_ac_v * (1 + max(-0.02, min(0.02, rng.gauss(0, 0.006))))
        frequency = 50 + max(-0.1, min(0.1, rng.gauss(0, 0.03)))
        temperature = ambient + 3 + 18 * ratio + rng.gauss(0, 0.5)
        return {
            "ts": ts.isoformat(timespec="seconds"),
            "device_id": inv.id,
            "site_id": inv.site_id,
            "ac_power_kw": round(power, 2),
            "dc_voltage_v": round(dc_voltage, 1),
            "ac_voltage_v": round(ac_voltage, 1),
            "frequency_hz": round(frequency, 3),
            "temperature_c": round(temperature, 1),
            "status": "producing" if power > 0 else "standby",
            "irradiance_wm2": round(irradiance, 1),
            "ambient_temp_c": round(ambient, 1),
        }

    def accumulate_energy(self, device_id: str, ts: datetime, power_kw: float) -> float:
        day, energy = self._energy.get(device_id, (ts.date(), 0.0))
        if day != ts.date():
            day, energy = ts.date(), 0.0
        energy += power_kw * self.interval_hours
        self._energy[device_id] = (day, energy)
        return round(energy, 2)

    def set_energy(self, device_id: str, ts: datetime, energy_kwh: float) -> None:
        self._energy[device_id] = (ts.date(), energy_kwh)
