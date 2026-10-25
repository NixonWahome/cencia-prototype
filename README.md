# Cencia AI: Prototype

Cybersecurity demo for Kenyan solar farms and mini-grids:

- **Monitor**: rules R1–R7 plus a physics-informed IsolationForest on live telemetry and commands.
- **Identify**: a simulated vulnerability scan with remediation steps and a risk score.
- **Verify**: every reading is Ed25519-signed at the edge and hash-chained, so tampering is provable.
- **Investor report**: verified kWh, fraud excluded, and integrity anchors.

> **Everything is simulated.** No real devices, no network scanning, nothing leaves localhost. Full spec: [SPEC.md](SPEC.md).

## Quick start (Windows)

Double-click **`start.bat`**, then open http://localhost:8000.

The first run creates the Python venv, installs packages and builds the frontend (a few minutes). After that it starts in about 10 s. For the phone remote, open `http://<laptop-ip>:8000/demo` on a phone on the same Wi-Fi. Find the laptop IP with `ipconfig`.

## Manual start / development

```bash
# backend (Python 3.11+, tested on 3.12)
cd backend
py -3.12 -m venv .venv            # macOS/Linux: python3 -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# frontend with hot reload (second terminal); proxies /api and /ws to :8000
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

`npm run build` writes `frontend/dist`, which FastAPI serves at http://localhost:8000. That way one process runs the whole demo.

Settings can be overridden with `CENCIA_*` env vars, e.g. `CENCIA_SIM_SPEED=120`, `CENCIA_RESET_ON_START=false`, `CENCIA_CORS_ORIGINS=https://your-frontend.vercel.app`.

## Tests

```bash
cd backend
.venv\Scripts\python -m pytest
```

The suite covers the hash chain and tamper detection, each rule firing on its attack, no false positives over a normal simulated day, response actions, reset, scan → remediate → rescan, and the report.

## Demo script (~5 min)

The same script is on the Demo page.

1. **Overview**: 3 sites live, all green.
2. **Vulnerabilities → Naivasha → Run scan**: default credentials + open Modbus. Risk 92. Remediate the default creds → 67.
3. **Demo → Unauthorized shutdown**: critical R3 alert in milliseconds, inverter drops to 0. Open the alert → **Block source IP**: resolved, MTTR shown, inverter restarted.
4. **Demo → Inflate output**: open Kibwezi, pick KIB-INV-03. Reported power climbs above the physics-expected line; R2 + ML alerts follow. *"Carbon-credit fraud, validly signed at the source, caught by physics."*
5. **Demo → Tamper stored record → Integrity**: a red block shows signed 171.3 kW vs stored 282.7 kW. **Restore from signed payload.**
6. **Investor report**: verified kWh, records verified, fraud prevented, chain heads.
7. **Reset.**

Before presenting: plug the laptop in, close heavy apps (torrent clients, extra Chrome tabs) and test with Wi-Fi off. The demo needs no internet.

## Hosting (optional)

The backend is a long-running process (simulator loop, WebSockets, in-memory chain heads). It needs an always-on container host, not serverless functions.

- **One service (recommended):** deploy the root `Dockerfile` on Render (`render.yaml` included), Railway or Fly.io. It builds the frontend and serves everything from one URL. Point a custom domain at it with a CNAME.
- **Split:** frontend on Vercel (`frontend/vercel.json` included), with `VITE_API_URL=https://your-api-host` at build time. On the API, set `CENCIA_CORS_ORIGINS` to the Vercel URL.

A public URL is shared state: anyone with the link can fire attacks or reset.
