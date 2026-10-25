"""Simulated vulnerability scanner.

It only reads the seeded device attributes in the database. No sockets are
ever opened and no IP address is contacted.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, Finding, Scan

CATALOG: dict[str, dict] = json.loads((Path(__file__).parent / "findings_catalog.json").read_text(encoding="utf-8"))
SEVERITY_WEIGHTS = {"critical": 25, "high": 15, "medium": 7, "low": 2}
SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def _service(device: Device, name: str) -> dict | None:
    return next((s for s in device.services if s["name"] == name), None)


def evaluate_device(device: Device) -> Iterator[tuple[str, str]]:
    """Yield (finding_type, evidence) for every weakness on the device."""
    if device.default_credentials:
        yield "default_credentials", f"Vendor default login accepted on the {device.vendor} {device.model} management interface."
    if 502 in device.open_ports and not device.protocol_auth:
        yield "modbus_no_auth", f"{device.ip}:502 accepts Modbus function codes without authentication."
    if 23 in device.open_ports:
        yield "telnet_open", f"Telnet listener on {device.ip}:23."
    mqtt = _service(device, "mqtt") or _service(device, "mqtts")
    if mqtt and mqtt.get("anonymous"):
        yield "mqtt_anonymous", f"Broker on {device.ip}:{mqtt['port']} accepted an anonymous CONNECT."
    if 80 in device.open_ports and _service(device, "http"):
        yield "http_no_tls", f"Management UI served over plain HTTP on {device.ip}:80."
    snmp = _service(device, "snmp")
    if snmp and snmp.get("version") in ("v1", "v2c") and snmp.get("community") == "public":
        yield "snmp_public", f"SNMP {snmp['version']} responds to community 'public' on {device.ip}:161."
    if device.firmware_version != device.latest_firmware:
        yield "outdated_firmware", f"Running {device.firmware_version}; vendor latest is {device.latest_firmware}."


def remediate_device(device: Device, finding_type: str, today: date) -> None:
    """Apply the fix to the device's simulated configuration."""
    if finding_type == "default_credentials":
        device.default_credentials = False
    elif finding_type == "modbus_no_auth":
        device.protocol_auth = True  # restricted to OT VLAN + allowlist
    elif finding_type == "telnet_open":
        device.open_ports = [p for p in device.open_ports if p != 23]
        device.services = [s for s in device.services if s["name"] != "telnet"]
    elif finding_type == "mqtt_anonymous":
        device.services = [
            {**s, "anonymous": False, "name": "mqtts", "port": 8883} if s["name"] in ("mqtt", "mqtts") else s
            for s in device.services
        ]
        device.open_ports = sorted({8883 if p == 1883 else p for p in device.open_ports})
        device.tls_enabled = True
    elif finding_type == "http_no_tls":
        device.open_ports = sorted({443 if p == 80 else p for p in device.open_ports})
        services = [s for s in device.services if s["name"] != "http"]
        if not any(s["name"] == "https" for s in services):
            services.append({"port": 443, "name": "https"})
        device.services = services
        device.tls_enabled = True
    elif finding_type == "snmp_public":
        device.services = [
            {"port": s["port"], "name": "snmp", "version": "v3"} if s["name"] == "snmp" else s
            for s in device.services
        ]
    elif finding_type == "outdated_firmware":
        device.firmware_version = device.latest_firmware
        device.last_patched = today


def risk_score(findings: list[Finding]) -> int:
    return min(100, sum(SEVERITY_WEIGHTS[f.severity] for f in findings if f.status == "open"))


def latest_scan(session: Session, site_id: str) -> Scan | None:
    return session.scalars(
        select(Scan).where(Scan.site_id == site_id, Scan.status == "completed").order_by(Scan.id.desc()).limit(1)
    ).first()


def recompute_risk(session: Session, scan: Scan) -> int:
    findings = session.scalars(select(Finding).where(Finding.scan_id == scan.id)).all()
    scan.risk_score = risk_score(findings)
    return scan.risk_score
