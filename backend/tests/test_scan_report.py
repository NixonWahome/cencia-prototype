from __future__ import annotations

import time

import pytest

from app.scanner import service as scan_service


@pytest.fixture(autouse=True)
def fast_scans(monkeypatch):
    monkeypatch.setattr(scan_service, "DEVICE_DELAY_SECONDS", 0)


def run_scan(client, site_id: str) -> dict:
    scan = client.post("/api/scans", json={"site_id": site_id}).json()
    for _ in range(100):
        body = client.get(f"/api/scans/{scan['id']}").json()
        if body["status"] == "completed":
            return body
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


def test_scan_remediate_rescan_lowers_risk(client):
    first = run_scan(client, "naivasha")
    types = {(f["device_id"], f["finding_type"]) for f in first["findings"]}
    assert ("NAI-INV-01", "default_credentials") in types
    assert ("NAI-INV-01", "modbus_no_auth") in types
    assert first["risk_score"] == 92
    assert first["findings"][0]["severity"] == "critical"  # sorted most severe first

    creds = next(f for f in first["findings"] if f["finding_type"] == "default_credentials")
    remediated = client.post(f"/api/findings/{creds['id']}/remediate").json()
    assert remediated["risk_score"] == 67
    assert remediated["device"]["default_credentials"] is False

    second = run_scan(client, "naivasha")
    assert second["risk_score"] == 67
    assert "default_credentials" not in {f["finding_type"] for f in second["findings"]}
    assert client.get("/api/sites/naivasha").json()["risk_score"] == 67


def test_site_risk_spread(client):
    assert run_scan(client, "kibwezi")["risk_score"] == 35
    assert run_scan(client, "thika")["risk_score"] == 7


def test_reset_restores_inventory(client):
    first = run_scan(client, "naivasha")
    creds = next(f for f in first["findings"] if f["finding_type"] == "default_credentials")
    client.post(f"/api/findings/{creds['id']}/remediate")
    client.post("/api/demo/reset")
    assert run_scan(client, "naivasha")["risk_score"] == 92


def test_report_flags_inflated_generation(client):
    clean = client.get("/api/reports/kibwezi").json()
    assert clean["generation"]["flagged_kwh"] == 0
    assert clean["integrity"]["verified_pct"] == 100.0
    assert "PLACEHOLDER" in clean["carbon"]["label"]

    client.post("/api/demo/attack/inflate_output")
    client.post("/api/demo/jump", json={"hour": 12})  # backfills ~3 h of inflated readings
    report = client.get("/api/reports/kibwezi").json()
    gen = report["generation"]
    assert gen["spoofed_kwh"] > 0
    assert gen["verified_kwh"] == pytest.approx(gen["reported_kwh"] - gen["flagged_kwh"], abs=0.2)
    assert report["security"]["alerts_total"] >= 1


def test_report_excludes_tampered_energy(client):
    attack = client.post("/api/demo/attack/tamper_stored_record").json()
    client.post("/api/integrity/verify/site/kibwezi")
    report = client.get("/api/reports/kibwezi").json()
    delta_kwh = (attack["params"]["tampered_kw"] - 0) * 5 / 60  # upper bound: signed value >= 0
    assert 0 < report["generation"]["tampered_kwh"] <= delta_kwh
    assert report["integrity"]["verified_pct"] < 100
    assert not report["integrity"]["all_chains_ok"]


def test_alert_api_actions_and_patch(client):
    client.post("/api/demo/attack/unauthorized_shutdown")
    alerts = client.get("/api/alerts", params={"status": "active"}).json()
    r3 = next(a for a in alerts if a["rule_id"] == "R3")
    assert r3["actions"] == ["block_ip"] and r3["mttd_seconds"] is not None
    assert client.post(f"/api/alerts/{r3['id']}/actions/isolate").status_code == 400
    ack = client.patch(f"/api/alerts/{r3['id']}", json={"status": "acknowledged"}).json()
    assert ack["status"] == "acknowledged" and ack["acknowledged_at"]
    done = client.post(f"/api/alerts/{r3['id']}/actions/block_ip").json()
    assert done["resolved"][0]["id"] == r3["id"]
    assert client.get("/api/overview").json()["kpis"]["open_critical_alerts"] == 0
