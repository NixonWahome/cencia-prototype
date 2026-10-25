from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app import db
from app.models import Alert, Command


def step(rt, intervals: int = 1) -> None:
    rt.clock.advance(timedelta(minutes=rt.settings.interval_minutes * intervals))
    rt.simulator.catch_up()
    rt.engine.flush()


def alerts(rule_id: str | None = None, device_id: str | None = None) -> list[Alert]:
    with db.read_session() as s:
        q = select(Alert)
        if rule_id:
            q = q.where(Alert.rule_id == rule_id)
        if device_id:
            q = q.where(Alert.device_id == device_id)
        return s.scalars(q).all()


def test_no_false_positives_over_a_full_day(rt):
    for _ in range(24 * 12 // 2):  # two intervals at a time so the ML pass runs on every one
        step(rt, 2)
    assert [(a.rule_id, a.device_id, a.title) for a in alerts()] == []


def test_spoof_night_generation_triggers_r1_and_ml(rt):
    result = rt.attacks.launch("spoof_night_generation")
    assert result["jumped_to"] is not None  # started in daylight, so the clock jumped to night
    step(rt, 2)
    r1 = alerts("R1", "KIB-INV-02")
    assert len(r1) == 1 and r1[0].severity == "high"
    assert r1[0].attack_id == result["id"] and r1[0].attack_started_real is not None
    assert r1[0].mitre_technique.startswith("T0856")
    ml = alerts("ML-ANOMALY", "KIB-INV-02")
    assert ml and ml[0].ml_score is not None
    assert ml[0].evidence["explanation"][0]["z"] > 4


def test_inflate_output_triggers_r2_and_ml(rt):
    result = rt.attacks.launch("inflate_output")
    step(rt, 3)
    r2 = alerts("R2", "KIB-INV-03")
    assert len(r2) == 1 and r2[0].attack_id == result["id"]
    assert r2[0].evidence["ratio"] > 1.15
    step(rt, 2)
    assert alerts("ML-ANOMALY", "KIB-INV-03")
    assert not alerts("R2", "KIB-INV-01")  # only the attacked inverter


def test_unauthorized_shutdown_triggers_r3_immediately(rt):
    rt.attacks.launch("unauthorized_shutdown")
    r3 = alerts("R3", "NAI-INV-01")
    assert len(r3) == 1 and r3[0].severity == "critical"
    assert r3[0].evidence["source_ip"] == "203.0.113.45"
    step(rt)
    latest = rt.simulator.latest["NAI-INV-01"]
    assert latest["ac_power_kw"] == 0 and latest["status"] == "shutdown"


def test_command_flood_triggers_r4(rt):
    rt.attacks.launch("command_flood")
    r4 = alerts("R4", "THK-INV-02")
    assert len(r4) == 1 and r4[0].evidence["write_count"] > 5
    assert alerts("R3", "THK-INV-02")  # unknown source too
    with db.read_session() as s:
        assert s.query(Command).filter(Command.attack_id.is_not(None)).count() == 20


def test_tamper_triggers_r7_with_signed_vs_stored(rt):
    result = rt.attacks.launch("tamper_stored_record")
    assert rt.verify_recent()
    r7 = alerts("R7", "KIB-INV-01")
    assert len(r7) == 1 and r7[0].attack_id == result["id"]
    field = r7[0].evidence["fields"][0]
    assert field["field"] == "ac_power_kw"
    assert field["stored"] == result["params"]["tampered_kw"]
    assert "signed" in r7[0].description and "stored" in r7[0].description


def test_device_offline_triggers_r5(rt):
    rt.attacks.launch("device_offline")
    step(rt, 2)
    assert not alerts("R5")
    step(rt)
    r5 = alerts("R5", "THK-INV-03")
    assert len(r5) == 1 and r5[0].evidence["missed_intervals"] >= 3


def test_alerts_deduplicate_while_open(rt):
    rt.attacks.launch("spoof_night_generation")
    step(rt, 4)
    r1 = alerts("R1", "KIB-INV-02")
    assert len(r1) == 1 and r1[0].evidence["occurrences"] >= 3


def test_block_ip_resolves_restores_and_blocks_refire(rt):
    rt.attacks.launch("unauthorized_shutdown")
    alert = alerts("R3", "NAI-INV-01")[0]
    result = rt.attacks.respond(alert.id, "block_ip")
    assert result["restored_devices"] == ["NAI-INV-01"]
    resolved = result["resolved"][0]
    assert resolved["status"] == "resolved" and resolved["mttr_seconds"] is not None
    step(rt)
    assert rt.simulator.latest["NAI-INV-01"]["status"] != "shutdown"

    refire = rt.attacks.launch("unauthorized_shutdown")
    assert "blocked" in refire["note"]
    assert len(alerts("R3")) == 1  # dropped at the firewall, no new alert


def test_restore_record_fixes_integrity(rt):
    rt.attacks.launch("tamper_stored_record")
    rt.verify_recent()
    alert = alerts("R7")[0]
    result = rt.attacks.respond(alert.id, "restore_record")
    assert result["integrity"]["ok"] and result["resolved"]


def test_reset_returns_clean_state(rt):
    for attack in ("spoof_night_generation", "tamper_stored_record", "device_offline", "command_flood"):
        rt.attacks.launch(attack)
    rt.verify_recent()
    step(rt, 3)
    assert alerts()
    rt.attacks.reset()
    assert alerts() == []
    assert rt.monitor.site_summary()["ok"]
    assert not rt.simulator.modifiers and not rt.simulator.offline
    step(rt, 3)
    rt.verify_recent()
    assert alerts() == []


def test_retrain_excludes_attack_windows(rt):
    rt.attacks.launch("inflate_output")
    step(rt, 2)
    summary = rt.retrain()
    assert summary["excluded_attack_windows"] == 1
    assert set(summary["retrained"]) == {"kibwezi", "naivasha", "thika"}
