"""PV physics model. Shared by the simulator and the R1/R2 detection rules."""
from __future__ import annotations

import math
from datetime import datetime

PEAK_IRRADIANCE_WM2 = 950.0
SYSTEM_FACTOR = 0.8  # inverter + wiring + soiling losses
TEMP_COEFF_PER_C = 0.004
NOCT_RISE_C = 25.0  # module temperature rise at 800 W/m²


def hour_of_day(ts: datetime) -> float:
    return ts.hour + ts.minute / 60 + ts.second / 3600


def clear_sky_irradiance(ts: datetime) -> float:
    h = hour_of_day(ts)
    if 6.0 < h < 18.0:
        return PEAK_IRRADIANCE_WM2 * math.sin(math.pi * (h - 6.0) / 12.0)
    return 0.0


def ambient_temp(ts: datetime, base_c: float, amplitude_c: float = 6.0) -> float:
    """Daily curve peaking mid-afternoon (14:30) and bottoming before dawn."""
    h = hour_of_day(ts)
    return base_c + amplitude_c * math.cos(2 * math.pi * (h - 14.5) / 24)


def module_temp(ambient_c: float, irradiance_wm2: float) -> float:
    return ambient_c + NOCT_RISE_C * irradiance_wm2 / 800.0


def temp_derate(module_c: float) -> float:
    return 1.0 - TEMP_COEFF_PER_C * max(0.0, module_c - 25.0)


def expected_power_kw(irradiance_wm2: float, ambient_c: float, capacity_kw: float) -> float:
    if irradiance_wm2 <= 0:
        return 0.0
    derate = temp_derate(module_temp(ambient_c, irradiance_wm2))
    return min(capacity_kw, irradiance_wm2 / 1000.0 * capacity_kw * SYSTEM_FACTOR * derate)
