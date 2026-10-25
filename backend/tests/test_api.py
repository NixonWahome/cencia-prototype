from __future__ import annotations


def test_sites_listed_with_live_values(client):
    sites = client.get("/api/sites").json()
    assert [s["id"] for s in sites] == ["kibwezi", "naivasha", "thika"]
    assert all(s["name"].endswith("(Demo)") for s in sites)
    assert all(s["integrity"]["integrity_pct"] == 100.0 for s in sites)
    assert all(s["status"] == "normal" for s in sites)


def test_overview_kpis(client):
    body = client.get("/api/overview").json()
    assert body["kpis"]["mw_monitored"] == 1.95
    assert body["kpis"]["telemetry_verified_pct"] == 100.0
    assert body["sim"]["simulated"] is True


def test_site_detail_includes_devices(client):
    site = client.get("/api/sites/naivasha").json()
    ids = [d["id"] for d in site["devices"]]
    assert ids == ["NAI-BAT-01", "NAI-INV-01", "NAI-INV-02", "NAI-MTR-01"]
    inverter = next(d for d in site["devices"] if d["id"] == "NAI-INV-01")
    assert inverter["online"] and inverter["latest"]["device_id"] == "NAI-INV-01"
    assert client.get("/api/sites/nope").status_code == 404


def test_telemetry_views(client):
    site_view = client.get("/api/sites/kibwezi/telemetry").json()
    assert len(site_view["points"]) > 200
    assert site_view["points"][-1]["reporting_devices"] == 4
    device_view = client.get("/api/sites/kibwezi/telemetry", params={"view": "device", "device_id": "KIB-INV-02"}).json()
    assert {r["device_id"] for r in device_view["readings"]} == {"KIB-INV-02"}


def test_commands_endpoint(client):
    cmds = client.get("/api/sites/thika/commands", params={"limit": 5}).json()
    assert len(cmds) == 5
    assert cmds[0]["ts"] >= cmds[-1]["ts"]


def test_verify_endpoints(client):
    site = client.post("/api/integrity/verify/site/naivasha").json()
    assert site["ok"] and len(site["devices"]) == 2
    device = client.post("/api/integrity/verify/device/KIB-INV-01").json()
    assert device["ok"] and device["first_broken"] is None
    assert client.post("/api/integrity/verify/device/KIB-SCADA-01").status_code == 404
    blocks = client.get("/api/integrity/records/KIB-INV-01", params={"limit": 5}).json()["blocks"]
    assert len(blocks) == 5 and blocks[1]["prev_hash"] == blocks[0]["hash"]


def test_demo_clock_controls(client):
    assert client.post("/api/demo/speed", json={"multiplier": 120}).json()["speed"] == 120
    assert client.post("/api/demo/speed", json={"multiplier": 0}).status_code == 422
    jumped = client.post("/api/demo/jump", json={"hour": 1}).json()
    assert jumped["sim_time"][11:13] in ("01", "00") or jumped["backfilled_intervals"] > 0
    assert jumped["backfilled_intervals"] > 0


def test_websocket_hello(client):
    with client.websocket_connect("/ws/live") as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello" and hello["simulated"] is True
