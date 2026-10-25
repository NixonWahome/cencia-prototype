"""Runtime configuration.

Every scalar setting can be overridden with an environment variable named
CENCIA_<FIELD_NAME_UPPER>, e.g. CENCIA_SIM_SPEED=120.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # --- storage / process ---
    db_path: str = str(BACKEND_DIR / "cencia.db")
    reset_on_start: bool = True  # fresh seed on every boot keeps the demo clean
    run_background: bool = True  # simulator + verifier loops (off in tests)
    rng_seed: int = 42

    # --- simulation clock ---
    sim_speed: float = 60.0  # sim seconds per real second (60x: one day = 24 min)
    interval_minutes: int = 5
    history_days: int = 3
    sim_start_hour: float = 9.0  # EAT; start in the morning so power is rising
    tick_seconds: float = 0.5  # how often the loop checks for due intervals
    max_catchup_intervals: int = 2 * 24 * 12  # cap on backfill after a time jump

    # --- integrity ---
    verify_every_seconds: float = 3.0
    verify_recent_records: int = 36  # re-checked per device on every pass

    # --- operations / detection (thresholds used by detection/ from Tuesday) ---
    maintenance_start_hour: int = 8
    maintenance_end_hour: int = 17
    soc_ips: tuple[str, ...] = ("10.0.0.5",)  # central SOC, allowed at every site
    site_allowlists: dict[str, list[str]] = field(
        default_factory=lambda: {
            "kibwezi": ["10.20.0.10", "10.20.0.11"],
            "naivasha": ["10.30.0.10"],
            "thika": ["10.40.0.10", "10.40.0.11"],
        }
    )
    night_power_ratio: float = 0.05
    night_irradiance_wm2: float = 20.0
    physics_mismatch_ratio: float = 1.15
    physics_min_expected_ratio: float = 0.05
    flood_write_threshold: int = 5
    flood_window_minutes: int = 5
    silent_intervals: int = 2
    freq_min_hz: float = 49.5
    freq_max_hz: float = 50.5

    # --- reporting ---
    # PLACEHOLDER values: illustrative only, must be sourced and verified before
    # any real use. Kenya's grid is already low-carbon, so the grid factor is
    # deliberately small; mini-grids are credited against diesel displacement.
    emission_factors: dict[str, dict] = field(
        default_factory=lambda: {
            "grid": {
                "kg_co2_per_kwh": 0.10,
                "label": "Grid emission factor: PLACEHOLDER, verify before use",
            },
            "diesel": {
                "kg_co2_per_kwh": 0.70,
                "label": "Diesel-displacement factor: PLACEHOLDER, verify before use",
            },
        }
    )

    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    def allowlist_for(self, site_id: str) -> list[str]:
        return [*self.site_allowlists.get(site_id, []), *self.soc_ips]

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls()
        for f in fields(cls):
            raw = os.getenv(f"CENCIA_{f.name.upper()}")
            if raw is None:
                continue
            current = getattr(settings, f.name)
            if f.name == "cors_origins":  # comma-separated, e.g. a Vercel frontend URL
                setattr(settings, f.name, [o.strip() for o in raw.split(",") if o.strip()])
                continue
            if isinstance(current, bool):
                value = raw.strip().lower() in ("1", "true", "yes", "on")
            elif isinstance(current, (int, float, str)):
                value = type(current)(raw)
            else:
                continue  # structured settings are edited in code
            setattr(settings, f.name, value)
        return settings
