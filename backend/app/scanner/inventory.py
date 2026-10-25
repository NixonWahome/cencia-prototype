"""Seeded device inventory and security posture (all fictional).

Naivasha is the deliberately weak site used in the demo scan, Kibwezi is
middling and Thika is mostly clean. IPs are private-range placeholders and
are never contacted.
"""
from __future__ import annotations

from datetime import date


def _svc(port: int, name: str, **extra) -> dict:
    return {"port": port, "name": name, **extra}


HTTPS = _svc(443, "https")
MODBUS = _svc(502, "modbus-tcp")

INVENTORY: dict[str, dict] = {
    # ---- Kibwezi: medium risk ----
    "KIB-INV-01": dict(vendor="SunForge", model="SF-300K", ip="10.20.1.11",
                       firmware_version="4.2.1", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 8, 14)),
    "KIB-INV-02": dict(vendor="SunForge", model="SF-300K", ip="10.20.1.12",
                       firmware_version="4.2.1", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 8, 14)),
    "KIB-INV-03": dict(vendor="SunForge", model="SF-300K", ip="10.20.1.13",
                       firmware_version="3.9.0", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2025, 11, 2)),
    "KIB-INV-04": dict(vendor="SunForge", model="SF-300K", ip="10.20.1.14",
                       firmware_version="4.2.1", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 8, 14)),
    "KIB-SCADA-01": dict(vendor="GridMate", model="GM-Edge 500", ip="10.20.0.2",
                         firmware_version="2.7.3", latest_firmware="2.8.0",
                         open_ports=[80, 161, 443, 502],
                         services=[_svc(80, "http"), _svc(161, "snmp", version="v2c", community="public"), HTTPS, MODBUS],
                         default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 3, 9)),
    "KIB-WX-01": dict(vendor="AeroSense", model="AS-WX2", ip="10.20.0.30",
                      firmware_version="1.4.0", latest_firmware="1.4.0", open_ports=[80], services=[_svc(80, "http")],
                      default_credentials=False, protocol_auth=True, tls_enabled=False, last_patched=date(2026, 5, 21)),

    # ---- Naivasha: high risk (demo scan target) ----
    # Scores to 92/100 so each remediation visibly lowers it (the cap is 100).
    "NAI-INV-01": dict(vendor="VoltaLink", model="VL-125", ip="10.30.1.11",
                       firmware_version="2.3.0", latest_firmware="2.3.0", open_ports=[443, 502],
                       services=[HTTPS, MODBUS],
                       default_credentials=True, protocol_auth=False, tls_enabled=True, last_patched=date(2025, 2, 11)),
    "NAI-INV-02": dict(vendor="VoltaLink", model="VL-125", ip="10.30.1.12",
                       firmware_version="2.3.0", latest_firmware="2.3.0", open_ports=[502], services=[MODBUS],
                       default_credentials=False, protocol_auth=False, tls_enabled=True, last_patched=date(2026, 1, 18)),
    "NAI-BAT-01": dict(vendor="StoreCell", model="SC-BMS 200", ip="10.30.0.20",
                       firmware_version="1.1.2", latest_firmware="1.5.0", open_ports=[23, 443],
                       services=[_svc(23, "telnet"), HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2023, 12, 5)),
    "NAI-MTR-01": dict(vendor="MeterHub", model="MH-C64", ip="10.30.0.40",
                       firmware_version="5.0.1", latest_firmware="5.0.1", open_ports=[1883, 443],
                       services=[_svc(1883, "mqtt", anonymous=True), HTTPS],
                       default_credentials=False, protocol_auth=False, tls_enabled=True, last_patched=date(2026, 4, 2)),

    # ---- Thika: mostly clean ----
    "THK-INV-01": dict(vendor="SunForge", model="SF-170K", ip="10.40.1.11",
                       firmware_version="4.2.1", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 9, 1)),
    "THK-INV-02": dict(vendor="SunForge", model="SF-170K", ip="10.40.1.12",
                       firmware_version="4.2.1", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 9, 1)),
    "THK-INV-03": dict(vendor="SunForge", model="SF-170K", ip="10.40.1.13",
                       firmware_version="4.2.1", latest_firmware="4.2.1", open_ports=[443], services=[HTTPS],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2026, 9, 1)),
    "THK-IOT-01": dict(vendor="LinkNode", model="LN-G3", ip="10.40.0.5",
                       firmware_version="3.1.0", latest_firmware="3.4.2", open_ports=[443, 8883],
                       services=[HTTPS, _svc(8883, "mqtts", anonymous=False)],
                       default_credentials=False, protocol_auth=True, tls_enabled=True, last_patched=date(2025, 10, 12)),
}
