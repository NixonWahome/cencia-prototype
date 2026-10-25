from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app import db
from app.models import Command
from app.simulator import physics
from app.simulator.clock import SimClock
from conftest import telemetry_rows


class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_clear_sky_curve():
    day = datetime(2026, 10, 25)
    assert physics.clear_sky_irradiance(day.replace(hour=3)) == 0
    assert physics.clear_sky_irradiance(day.replace(hour=20)) == 0
    assert physics.clear_sky_irradiance(day.replace(hour=12)) == physics.PEAK_IRRADIANCE_WM2


def test_expected_power_includes_system_factor_and_derate():
    expected = physics.expected_power_kw(950, 28, 300)
    assert 0.6 * 300 < expected < 0.76 * 300  # below the 0.8 x 950/1000 ceiling once hot
    # +30% inflation must clear the R2 threshold (the v1.0 spec bug)
    assert expected * 1.30 > expected * 1.15


def test_clock_speed_and_forward_jump():
    fake = FakeTime()
    clock = SimClock(datetime(2026, 10, 25, 9, 0), speed=60, time_fn=fake)
    fake.t += 5
    assert clock.now() == datetime(2026, 10, 25, 9, 5)
    clock.set_speed(120)
    fake.t += 5
    assert clock.now() == datetime(2026, 10, 25, 9, 15)
    assert clock.jump_to_hour(1) == datetime(2026, 10, 26, 1, 0)  # next 01:00, never backwards
    assert clock.jump_to_hour(10.5) == datetime(2026, 10, 26, 10, 30)


def test_history_is_physically_plausible(rt):
    rows = telemetry_rows("KIB-INV-01")
    night = [r for r in rows if r.ts.hour < 5 or r.ts.hour >= 19]
    assert night and all(r.ac_power_kw == 0 and r.irradiance_wm2 == 0 for r in night)
    assert max(r.ac_power_kw for r in rows) > 0.5 * 300
    assert all(r.ac_power_kw <= 300 for r in rows)
    assert all(49.9 <= r.frequency_hz <= 50.1 for r in rows)
    assert all(392 <= r.ac_voltage_v <= 408 for r in rows)
    # energy resets at midnight and only goes up within a day
    by_day: dict = {}
    for r in rows:
        by_day.setdefault(r.ts.date(), []).append(r.energy_today_kwh)
    for values in by_day.values():
        assert values == sorted(values)


def test_normal_writes_are_allowlisted_and_in_window(rt, settings):
    with db.read_session() as s:
        cmds = s.scalars(select(Command)).all()
    assert any(c.command == "READ" for c in cmds)
    writes = [c for c in cmds if c.is_write]
    assert writes
    for c in writes:
        assert c.source_ip in settings.allowlist_for(c.site_id)
        assert settings.maintenance_start_hour <= c.ts.hour < settings.maintenance_end_hour


def test_jump_backfills_and_chains_stay_valid(rt):
    before = len(telemetry_rows("NAI-INV-01"))
    rt.clock.jump_to_hour((rt.clock.now().hour + 3) % 24)
    due = rt.simulator.catch_up()
    assert len(due) >= 3 * 12
    assert len(telemetry_rows("NAI-INV-01")) == before + len(due)
    rt.verify_recent()
    assert rt.monitor.site_summary()["ok"]


def test_offline_device_stops_reporting(rt):
    rt.simulator.offline.add("THK-INV-03")
    before = len(telemetry_rows("THK-INV-03"))
    rt.clock.advance(timedelta(minutes=30))
    rt.simulator.catch_up()
    assert len(telemetry_rows("THK-INV-03")) == before
    assert not rt.simulator.device_online("THK-INV-03")
    assert rt.simulator.device_online("THK-INV-01")


def test_source_modifier_output_is_validly_signed(rt):
    """Lying at the source passes integrity checks; that's why Monitor exists."""
    def inflate(reading, _ts):
        return {**reading, "ac_power_kw": round(reading["ac_power_kw"] * 1.3, 2)}

    rt.simulator.modifiers["KIB-INV-03"] = [inflate]
    rt.clock.advance(timedelta(minutes=15))
    rt.simulator.catch_up()
    rt.verify_recent()
    assert rt.monitor.device("KIB-INV-03")["ok"]
