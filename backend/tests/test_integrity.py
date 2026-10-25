from __future__ import annotations

import json

from sqlalchemy import delete, update

from app import db
from app.integrity.chain import GENESIS_HASH, EdgeAgent, chain_hash
from app.integrity.keys import generate_keypair
from app.integrity.signing import canonical_json, sign, verify_signature
from app.integrity.keys import load_private_key
from app.integrity.verify import verify_device
from app.models import Telemetry
from conftest import telemetry_rows

DEVICE = "KIB-INV-01"


def verify(device_id: str = DEVICE):
    with db.read_session() as s:
        return verify_device(s, device_id).to_dict()


def test_canonical_json_ignores_key_order():
    assert canonical_json({"b": 1, "a": 2.5}) == canonical_json({"a": 2.5, "b": 1}) == '{"a":2.5,"b":1}'


def test_edge_agent_links_records():
    private_hex, public_hex = generate_keypair()
    agent = EdgeAgent("X", private_hex)
    first = agent.seal({"ac_power_kw": 1.0})
    second = agent.seal({"ac_power_kw": 2.0})
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash
    assert second.hash == chain_hash(first.hash, second.canonical, second.signature)
    assert verify_signature(public_hex, second.canonical, second.signature)


def test_seeded_chains_verify_clean(rt):
    expected = 24 * 12 + 1  # one history day, both ends inclusive
    for d in rt.monitor.devices():
        assert d["ok"], d["first_broken"]
        assert d["total"] == expected
        assert d["integrity_pct"] == 100.0
    assert rt.monitor.site_summary()["integrity_pct"] == 100.0


def test_column_tamper_reports_signed_vs_stored(rt):
    target = telemetry_rows(DEVICE)[150]
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(ac_power_kw=410.0))

    report = verify()
    assert not report["ok"]
    assert report["broken_count"] == 1  # the rest of the chain still verifies
    broken = report["first_broken"]
    assert broken["seq"] == target.seq
    columns = next(p for p in broken["problems"] if p["check"] == "columns")
    assert f"signed {target.ac_power_kw:.1f} kW, stored 410.0 kW" in columns["message"]
    assert columns["fields"][0] == {
        "field": "ac_power_kw", "signed": target.ac_power_kw, "stored": 410.0,
        "message": f"ac_power_kw: signed {target.ac_power_kw:.1f} kW, stored 410.0 kW",
    }
    assert report["integrity_pct"] < 100


def test_payload_rewrite_fails_signature(rt):
    """An attacker who edits the payload and the column consistently still can't forge the signature."""
    target = telemetry_rows(DEVICE)[150]
    payload = json.loads(target.payload)
    payload["ac_power_kw"] = 410.0
    forged = canonical_json(payload)
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(
            payload=forged, ac_power_kw=410.0,
            hash=chain_hash(target.prev_hash, forged, target.signature),
        ))

    report = verify()
    checks = {p["check"] for p in report["first_broken"]["problems"]}
    assert "signature" in checks
    # the recomputed hash no longer matches what the next record links to
    assert report["broken_count"] == 2
    assert {b["seq"] for b in report["broken"]} == {target.seq, target.seq + 1}


def test_resigning_with_another_key_fails(rt):
    target = telemetry_rows(DEVICE)[150]
    payload = json.loads(target.payload)
    payload["ac_power_kw"] = 410.0
    forged = canonical_json(payload)
    attacker_key = load_private_key(generate_keypair()[0])
    signature = sign(attacker_key, forged)
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(
            payload=forged, ac_power_kw=410.0, signature=signature,
            hash=chain_hash(target.prev_hash, forged, signature),
        ))

    problems = verify()["first_broken"]["problems"]
    assert problems[0]["check"] == "signature"


def test_deleted_record_breaks_linkage(rt):
    target = telemetry_rows(DEVICE)[100]
    with db.write_session() as s:
        s.execute(delete(Telemetry).where(Telemetry.id == target.id))

    report = verify()
    assert report["broken_count"] == 1
    assert report["first_broken"]["seq"] == target.seq + 1
    assert report["first_broken"]["problems"][0]["check"] == "linkage"


def test_other_devices_unaffected_by_tamper(rt):
    target = telemetry_rows(DEVICE)[10]
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(ac_power_kw=999.0))
    assert verify("KIB-INV-02")["ok"]


def test_background_pass_flags_recent_tamper_once(rt):
    rows = telemetry_rows(DEVICE)
    target = rows[-3]
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(ac_power_kw=410.0))

    new = rt.verify_recent()
    assert [(p["device_id"], p["seq"]) for p in new] == [(DEVICE, target.seq)]
    assert rt.verify_recent() == []  # already known: R7 must not fire twice
    state = rt.monitor.device(DEVICE)
    assert state["broken_count"] == 1 and state["total"] == len(rows)


def test_background_pass_clears_restored_record(rt):
    target = telemetry_rows(DEVICE)[-2]
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(ac_power_kw=410.0))
    rt.verify_recent()
    with db.write_session() as s:
        s.execute(update(Telemetry).where(Telemetry.id == target.id).values(ac_power_kw=target.ac_power_kw))
    rt.verify_recent()
    assert rt.monitor.device(DEVICE)["ok"]
