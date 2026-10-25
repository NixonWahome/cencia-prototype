# Cencia AI — Prototype Build Spec (v1.1)

Oct 25, 2026 · @Nixon · Demo deadline: **Thursday 29 Oct 2026**

For Claude Code: this is the full spec for a working demo prototype. Build it in the order given in §12. Everything is simulated: no real devices, no real network scanning.

## Changes from v1.0

| # | Change | Why |
|---|--------|-----|
| 1 | **R2 compares against *expected* power** (physics model incl. the 0.8 system factor and temperature derate), not the theoretical max. | With the old definition a +30% inflation reached only 0.8 × 1.3 = 104% of max and R2 never fired. |
| 2 | **Sim clock starts at 09:00 EAT**, and the demo panel gets a **"Jump to time"** control (forward only, gap is backfilled). | At 60× a sim day is 24 real minutes; night-only attacks could not be demoed on cue. |
| 3 | `unauthorized_shutdown` no longer requires 02:00. It fires at the current sim time from an unknown IP. | R3 already fires on a non-allowlisted IP; a daytime shutdown also makes the power drop visible on the chart. |
| 4 | `spoof_night_generation` auto-jumps the clock to 01:00 if it is daytime. | R1 needs irradiance < 20 W/m². |
| 5 | **R4 window is 5 sim-minutes** (one interval), not 60 sim-seconds. | 60 sim-seconds = 1 real second at 60×; the rule was fragile and speed-dependent. |
| 6 | **R5 fires after > 2 silent intervals** (was > 3). | Matches the "alert within ~2 intervals" acceptance criterion. |
| 7 | **MTTD/MTTR stored in both real seconds and sim seconds.** The UI headline is real seconds. | "Detected in 4 s" is the honest, impressive number. |
| 8 | Attacker IPs come from **RFC 5737 documentation ranges** (`203.0.113.0/24`, `198.51.100.0/24`). | Guaranteed never to be a real host. |
| 9 | Each attack has a **fixed target device** (§10). | Repeatable demo. |
| 10 | Private keys live in a separate `edge_keys` table, read only by the simulated edge agent; the server verifier uses only `devices.public_key`. | Mirrors the real architecture; honest answer to "where are the keys?". |
| 11 | Only inverters stream telemetry. Site-level irradiance and ambient temperature are included **inside each inverter's signed payload**. | Physics checks then run on signed data. |
| 12 | Integrity is checked **per record** (signature, linkage to predecessor, hash, columns vs payload). A column-only tamper fails exactly one record; the rest of the chain stays verified. | Clear visual and a fair integrity %. |
| 13 | Reset restores tampered DB values (the injector stores the original). Reset does not rewind the clock. | §10 reset requirement. |
| 14 | SQLite runs in **WAL mode** with a **single process-wide write lock**. | Simulator + verifier + API writing concurrently would hit "database is locked". |
| 15 | Fixed RNG seed, ML threshold calibrated on held-out normal data (target ≈ 0 false positives over a demo hour). | No surprise alerts on stage. |
| 16 | Avoided-CO₂ uses a **per-site baseline**: grid factor for IPP/C&I, diesel-displacement factor for the mini-grid. Both are placeholders. | Kenya's grid is already low-carbon; the real carbon story for mini-grids is diesel displacement. |
| 17 | Added: MITRE ATT&CK for ICS tags on alerts, ML feature explanations, response actions, fraud-prevented panel, phone-friendly attacker panel (§15). | Contest differentiators. |

## Changes made during the build (v1.2)

| Change | Why |
|---|---|
| `inflate_output` ramps +8% per reading up to +30% (was ~10 readings). | R2 fires on reading 2–3 (~10 s) instead of ~30 s of dead air on stage. |
| ML is two-stage: the IsolationForest screens the most unusual 2% (held-out calibration), then a ≥ 5σ same-hour baseline deviation must confirm. A `perf_ratio` feature (reported ÷ physics-expected) was added. | A single forest threshold could not separate attacks from rare cloud dips (scores overlapped). Measured: 0 false positives over 12 normal sim-days across 3 seeds. |
| Cloud-cover suppression: if power tracks measured sunlight (perf_ratio within 3σ) while irradiance is unusually low, the reading is not flagged. | "We don't page an operator for a cloud." |
| ML scoring is skipped for intervals backfilled after a clock jump (rules still run). | Keeps a 16-hour jump fast on modest laptops. |
| R7 alerts offer **Restore from signed payload**; R3/R4 offer **Block source IP** (the SOC then restarts the device); others offer **Isolate device**. A blocked IP's later commands are logged as dropped. | Response actions make MTTR demoable. |
| Naivasha inventory tuned to score 92 (not capped at 100), so each remediation visibly lowers it: 92 → 67 after rotating default credentials. | Demo step 2. |
| The Integrity page centers the block strip on the first broken record. | The red block is always on screen. |
| FastAPI serves the built frontend; one process, one URL. | Simpler demo laptop and hosting. |

## 1. What Cencia AI is

Cencia AI is a cybersecurity platform for Kenya's solar farms and mini-grids. These sites run networked OT (inverters, smart meters, SCADA gateways talking Modbus/MQTT), usually with weak or no authentication. Three pillars, all demoed:

- **Monitor**: watch live telemetry and device commands; detect unauthorized commands and physically impossible readings (spoofing) with rules + an ML anomaly model.
- **Identify**: scan site devices for vulnerabilities (open Modbus/Telnet, default credentials, old firmware) and give remediation steps.
- **Verify**: sign every telemetry reading at the edge and hash-chain it, so tampering with generation data (which drives carbon credits and investor reports) is detectable.

Plus an **Investor Report** showing verified generation (the "bankable" angle).

**Two lines of defence (say this in the pitch):** Verify catches data altered *after* it was signed (DB/report tampering). Monitor catches a device lying *at the source* (signatures are valid, but the physics are impossible). Hence both.

## 2. Scope

In scope: telemetry simulator for 3 sites, live dashboard, detection engine (rules + Isolation Forest), simulated vulnerability scanner, signing + hash-chain verification, investor report, demo control panel.

Out of scope: real device integration, real port scanning, real Modbus traffic, multi-tenant auth, payments, mobile app (the web app is responsive instead).

## 3. Stack (locked)

- Backend: Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2 + SQLite (WAL), scikit-learn (IsolationForest, CPU), cryptography (Ed25519), WebSockets, pytest.
- Frontend: React + TypeScript + Vite, Tailwind CSS, Recharts, React Router.
- No Docker, no GPU, **no CDN or web fonts at runtime** (the demo must work offline). `pip install -r requirements.txt` + `npm install`.

## 4. Repo layout

```
cencia-prototype/
  backend/
    app/
      main.py            # FastAPI app factory, routers, lifespan (seed + background tasks)
      config.py          # sim speed, thresholds, emission factors, allowlists (CENCIA_* env overrides)
      db.py, models.py   # engine (WAL + write lock), SQLAlchemy models
      runtime.py         # wires clock, simulator, integrity monitor, websocket broadcaster
      seed.py            # sites, devices, keys
      simulator/         # clock, physics, telemetry + command generators, sites, service loop
      detection/         # rules.py, anomaly.py (IsolationForest), engine.py
      scanner/           # inventory.py, findings_catalog.json, scan.py
      integrity/         # keys.py, signing.py, chain.py, verify.py
      demo/              # attack injectors + reset
      api/               # routers: sites, telemetry, alerts, scans, integrity, reports, demo, ws
    tests/
    requirements.txt
  frontend/
    src/pages/  src/components/  src/api/
  README.md
```

## 5. Simulated sites and devices

| Site (id) | Type | Capacity | Devices |
|---|---|---|---|
| Kibwezi Solar Park (Demo) (`kibwezi`) | Utility solar / IPP | 1.2 MWp | 4 inverters (300 kW), 1 SCADA gateway, 1 weather station |
| Naivasha Mini-Grid (Demo) (`naivasha`) | Mini-grid | 250 kWp | 2 inverters (125 kW), 1 battery controller, 1 smart-meter concentrator |
| Thika C&I Rooftop (Demo) (`thika`) | Commercial rooftop | 500 kWp | 3 inverters (166.7 kW), 1 IoT gateway |

Vendor and model names are fictional.

**Telemetry** (inverters only, every interval), all inside the signed payload: `ts, device_id, site_id, seq, ac_power_kw, dc_voltage_v, ac_voltage_v, frequency_hz, temperature_c, status, energy_today_kwh, irradiance_wm2, ambient_temp_c`.

**Physics model** (`simulator/physics.py`, shared with detection):
- Daylight 06:00–18:00 EAT: `irradiance = 950 · sin(π(h−6)/12) · cloud_factor`; 0 at night. Cloud dips are random (≈6%/interval chance, depth 35–75%, 1–4 intervals).
- `module_temp = ambient + 25 · irradiance/800`; `derate = 1 − 0.004 · max(0, module_temp − 25)`.
- `expected_power = (irradiance/1000) · capacity · 0.8 · derate`; `ac_power = expected · (1 + N(0, 1.5%))`.
- Frequency 50 Hz ± 0.1; AC voltage nominal (400 V, or 230 V at Naivasha) ± 2%.

**Sim clock:** default 60× (one sim day = 24 real min), interval 5 sim-minutes (= 5 real seconds). Starts at **09:00 EAT today** with **3 days of history** seeded. `POST /api/demo/jump {hour}` moves forward to the next occurrence of that hour and backfills the gap so charts and chains stay continuous.

**Command log:** normal READ polling (`scada-svc`, any hour) plus occasional SET_POWER_LIMIT and FIRMWARE_UPDATE from allowlisted IPs during the maintenance window 08:00–17:00. Write commands = SET_POWER_LIMIT, FIRMWARE_UPDATE, SHUTDOWN, START. SHUTDOWN/START are only issued by attacks or operator response actions.

## 6. Monitor: detection engine

| ID | Rule | Severity | MITRE ATT&CK for ICS |
|---|---|---|---|
| R1 | Night generation: power > 5% of capacity while irradiance < 20 W/m² | High | T0856 Spoof Reporting Message |
| R2 | Physics mismatch: power > 115% of *expected* power, when expected > 5% of capacity | High | T0856 Spoof Reporting Message |
| R3 | Unauthorized command: write command from a non-allowlisted IP or outside 08:00–17:00 | Critical | T0855 Unauthorized Command Message |
| R4 | Command flood: > 5 write commands to one site within 5 sim-minutes | High | T0814 Denial of Service |
| R5 | Device silent: no telemetry for > 2 intervals | Medium | T0814 Denial of Service |
| R6 | Grid frequency outside 49.5–50.5 Hz | Medium | T0831 Manipulation of Control |
| R7 | Integrity failure: signature, linkage, hash or column check fails | Critical | T0856 / data tampering |

Each alert has `rule_id, severity, title, description, evidence (json), recommended_action, mitre_technique`.

**ML layer:** one IsolationForest per site, trained on seeded history. Features: `power_ratio, irradiance, temperature_c, ac_voltage_v, frequency_hz, hour_sin, hour_cos`. The threshold is calibrated on a held-out 20% of normal history (score quantile ≈ 0.1%). Below threshold → `ML-ANOMALY` (Medium). **Explanation:** the alert shows the anomaly score and the top 3 features by |z-score| against that site's same-hour baseline (e.g. "power_ratio 4.1σ above normal for 02:00"). There is a retrain endpoint for the demo. Alerts for the same device and rule are de-duplicated while one is open.

**Alert model:** `id, site_id, device_id, rule_id, severity, title, description, evidence, recommended_action, mitre_technique, ml_score, status (open/acknowledged/resolved), attack_id, attack_started_at (+_real), detected_at (+_real), acknowledged_at, resolved_at (+_real)`.
MTTD = detected − attack_started; MTTR = resolved − detected. Both are stored in real and sim seconds; **real seconds are shown in the headline**.

**Response actions** (alert drawer): *Block IP* (adds to blocklist, resolves R3/R4) and *Isolate device* (marks it quarantined). Either one resolves the alert, so MTTR is demoed live.

## 7. Identify: vulnerability scanner (simulated)

Device attributes (seeded in `scanner/inventory.py`): `open_ports, services, firmware_version, latest_firmware, default_credentials, protocol_auth, tls_enabled, last_patched`. Mix: Naivasha bad (demo target), Kibwezi medium, Thika mostly clean.

`findings_catalog.json` (generic finding types, not CVE IDs):

| Finding | Severity | Remediation |
|---|---|---|
| Default credentials active | Critical | Rotate credentials, enforce unique passwords |
| Modbus TCP (502) exposed without auth | High | Restrict to OT VLAN, firewall allowlist, VPN |
| Telnet (23) open | High | Disable Telnet, use SSH |
| MQTT broker allows anonymous clients | High | Require client auth + TLS |
| Web management over HTTP (no TLS) | Medium | Enable HTTPS, disable HTTP |
| SNMP v1/v2 with 'public' community | Medium | Move to SNMPv3 |
| Outdated firmware | Medium | Schedule vendor firmware update |

Flow: `POST /api/scans {site_id}` runs async with per-device progress (~1 s fake delay) and stores findings. Risk score 0–100 = Critical 25 + High 15 + Medium 7 per open finding, capped at 100. "Mark remediated" updates the device attributes and closes the finding; a rescan reflects it. **Never open real sockets.**

## 8. Verify: telemetry integrity

- Each inverter gets an Ed25519 keypair at seed. The private key goes in `edge_keys` (the simulated edge agent); the public key goes in `devices.public_key`.
- Per reading: canonical JSON (sorted keys, `(",", ":")` separators, floats pre-rounded) → Ed25519 sign → `prev_hash` = previous record's hash (genesis = 64 zeros) → `hash = sha256(prev_hash + canonical_json + signature_hex)`.
- Stored: the signed canonical payload, signature, prev_hash, hash, plus parsed columns for charts.
- Verify (`POST /api/integrity/verify/{device|site}/{id}`): each record is checked for (a) signature, (b) prev_hash = predecessor's stored hash and contiguous seq, (c) recomputed hash, (d) parsed columns = signed payload. Returns `ok`, `first_broken` and all broken records with human messages, e.g. `signed 312.4 kW, stored 410.0 kW`.
- Integrity % = (records − broken) / records.
- A background verifier (every 3 s) checks new records and re-checks the most recent 36 per device; newly broken records raise R7.
- `GET /api/integrity/records/{device_id}` returns the latest chain blocks for the block visual.

## 9. Investor report

Per site + date range: total kWh, % records cryptographically verified, chain head hash, open critical findings, MTTD/MTTR, estimated avoided CO₂ = kWh × baseline factor.

⚠️ Emission factors are config values, labelled **"PLACEHOLDER — verify before use"**: `grid` (IPP, C&I) and `diesel` (mini-grid displacement). Avoided-CO₂ is illustrative only.

**Fraud-prevented panel:** kWh that injected/inflated readings would have added, shown next to verified kWh.

Rendered as a printable page + JSON download.

## 10. Demo attacks

`POST /api/demo/attack/{type}`. Each attack records `attack_started_at` (sim + real).

| Type | Target | What it does | Should trigger |
|---|---|---|---|
| `spoof_night_generation` | KIB-INV-02 | Auto-jumps to 01:00 if needed; injects high power at night (applied at source, validly signed) | R1, ML-ANOMALY |
| `inflate_output` | KIB-INV-03 | Ramps reported power to +30% over ~10 readings (at source) | R2, ML-ANOMALY |
| `unauthorized_shutdown` | NAI-INV-01 | SHUTDOWN from 203.0.113.45 via Modbus/TCP; inverter output → 0 | R3 |
| `command_flood` | THK-INV-02 | 20 SET_POWER_LIMIT writes from 198.51.100.23 in one interval | R4 (+R3) |
| `tamper_stored_record` | KIB-INV-01 | Edits a recent stored row's `ac_power_kw` without re-signing | R7 (verify shows signed vs stored) |
| `device_offline` | THK-INV-03 | Stops the device's telemetry | R5 |

`POST /api/demo/reset` clears attacks, alerts and blocklist; restores tampered rows; brings devices online. `POST /api/demo/speed {multiplier}` (1–600). `POST /api/demo/jump {hour}`.

## 11. API and frontend

Endpoints: `GET /api/overview`, `GET /api/sim`, `GET /api/sites`, `GET /api/sites/{id}`, `GET /api/sites/{id}/telemetry?from&to&view=site|device&device_id`, `GET /api/sites/{id}/commands`, `GET /api/devices/{id}`, `GET/PATCH /api/alerts`, `POST /api/alerts/{id}/actions/{block_ip|isolate}`, `POST /api/scans`, `GET /api/scans/{id}`, `POST /api/findings/{id}/remediate`, `POST /api/integrity/verify/{scope}/{id}`, `GET /api/integrity/status`, `GET /api/integrity/records/{device_id}`, `GET /api/reports/{site_id}`, `POST /api/demo/*`, `WS /ws/live` (messages: `hello`, `tick`, `alert`, `integrity_failure`).

Pages:
1. **Overview**: KPI strip (MW monitored, open critical alerts, avg MTTD, % telemetry verified); site cards (live kW, status, risk score, integrity %, open alerts).
2. **Site detail**: live charts (power vs irradiance, voltage, frequency, temperature), device table, command log, site alerts.
3. **Alerts**: filterable table; detail drawer with evidence, ML score + feature explanation, MITRE tag, recommended action, MTTD, response actions, acknowledge/resolve.
4. **Vulnerabilities**: scan with progress, findings by severity, remediate, risk gauge.
5. **Integrity**: per-device chain status, **block-chain visual** (broken block in red), Verify button, signed vs stored value.
6. **Investor report**: printable, with the fraud-prevented panel.
7. **Demo panel** (`/demo`, phone-friendly, usable as a remote from a second device): attack buttons, jump to time, reset, sim speed. Toasts when alerts fire, plus a mock SMS card showing the operator notification.

Look: dark green `#1B4332` primary, orange `#D97706` accent, off-white `#F7F5F0` background, fully responsive, top-right badge **"Simulated demo data"**. Fonts are bundled locally.

## 12. Build order (Sun → Thu)

1. **Sun/Mon:** backend skeleton, models, seed, simulator + history, signing + hash chain + verify, core read endpoints, WebSocket, clock speed/jump. Tests for chain + tamper detection.
2. **Tue:** rules engine, IsolationForest (+ explanations), alerts + MTTD/MTTR, response actions, scanner, all 6 demo attacks + reset, report endpoint. Tests for each rule firing on its attack.
3. **Wed:** frontend: all 7 pages wired to the API + live updates.
4. **Thu AM:** polish, README, `start.bat`, offline check (Wi-Fi off), record a backup video, rehearse §13.

**Cut order if behind:** Thika site → retrain endpoint → SNMP/HTTP findings → standalone Alerts page (use site detail + toasts). Never cut anything in §13.

## 13. Demo script (~5 min)

1. Overview: 3 sites live, all green (sim ≈ 09:00–11:00, power rising).
2. Vulnerabilities: scan Naivasha → default creds + open Modbus → remediate one → risk score drops.
3. Fire `unauthorized_shutdown` (from the phone) → critical alert in seconds, power drops to 0, MTTD shown. Click *Block IP* → MTTR shown.
4. Fire `inflate_output` → R2 + ML alert with explanation: "this is carbon-credit fraud being caught, even though the data is validly signed".
5. Fire `tamper_stored_record` → Integrity page: red block, signed vs stored value.
6. Investor report: verified %, kWh, fraud-prevented panel, why investors care.
7. Reset.

## 14. Acceptance checklist

- [ ] uvicorn + `npm run dev` start cleanly from README steps, no Docker
- [ ] 3 sites stream live telemetry; charts update without refresh
- [ ] Each of the 6 attacks raises the expected alert within ~2 sim-intervals (R5: within 3)
- [ ] Tamper is detected and shows signed vs stored value
- [ ] Scan → remediate → rescan changes the risk score
- [ ] Reset returns the system to a clean state
- [ ] No false-positive alerts during 30 real minutes of normal running
- [ ] Usable at phone width
- [ ] Works with Wi-Fi off
- [ ] pytest passes (chain, tamper, each rule)
- [ ] Nothing performs real network activity beyond localhost

## 15. Judge Q&A prep

- *How do you sign on legacy inverters?* An edge gateway (Pi-class with a secure element) next to the data logger reads Modbus locally and signs. In the prototype the edge is simulated and its keys sit in a separate table.
- *Why IsolationForest?* It runs on a CPU, needs no labelled attacks, and is explainable via feature z-scores. Physics rules carry the high-confidence cases.
- *Kenya's grid is clean, so why carbon?* Mini-grids displace diesel, and investors and results-based-financing programmes pay on verified kWh either way.
- *Is it all simulated?* Yes, as the badge says. Next step: a pilot on one site's data logger.
