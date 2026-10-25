"""SQLAlchemy models.

Sim timestamps (`ts`, `*_at`) are naive datetimes on the simulated EAT clock.
Real timestamps (`*_real`) are naive UTC wall-clock times, used for the
headline MTTD/MTTR numbers.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    site_type: Mapped[str] = mapped_column(String(60))
    capacity_kwp: Mapped[float] = mapped_column(Float)
    location: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    ambient_base_c: Mapped[float] = mapped_column(Float)
    nominal_ac_v: Mapped[float] = mapped_column(Float)
    emission_baseline: Mapped[str] = mapped_column(String(20))  # key into emission_factors

    devices: Mapped[list["Device"]] = relationship(
        back_populates="site", order_by="Device.id"
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    vendor: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    ip: Mapped[str] = mapped_column(String(45))
    capacity_kw: Mapped[float | None] = mapped_column(Float, nullable=True)

    # security posture, read by the simulated scanner
    firmware_version: Mapped[str] = mapped_column(String(20))
    latest_firmware: Mapped[str] = mapped_column(String(20))
    open_ports: Mapped[list] = mapped_column(JSON, default=list)
    services: Mapped[list] = mapped_column(JSON, default=list)
    default_credentials: Mapped[bool] = mapped_column(Boolean, default=False)
    protocol_auth: Mapped[bool] = mapped_column(Boolean, default=True)
    tls_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_patched: Mapped[date] = mapped_column(Date)

    # Ed25519 public key (hex) of the device's edge agent; all the server needs
    # to verify telemetry.
    public_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)

    site: Mapped[Site] = relationship(back_populates="devices")


class EdgeKey(Base):
    """Private signing key held by the device's edge agent.

    In a real deployment this never leaves the edge gateway's secure element.
    It is stored here only because the edge is simulated, and is read solely
    by the simulator, never by the verifier or the API.
    """

    __tablename__ = "edge_keys"

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    private_key: Mapped[str] = mapped_column(String(64))


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        UniqueConstraint("device_id", "seq"),
        Index("ix_telemetry_site_ts", "site_id", "ts"),
        Index("ix_telemetry_device_ts", "device_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime)

    # parsed columns used by charts and detection
    ac_power_kw: Mapped[float] = mapped_column(Float)
    dc_voltage_v: Mapped[float] = mapped_column(Float)
    ac_voltage_v: Mapped[float] = mapped_column(Float)
    frequency_hz: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    energy_today_kwh: Mapped[float] = mapped_column(Float)
    irradiance_wm2: Mapped[float] = mapped_column(Float)
    ambient_temp_c: Mapped[float] = mapped_column(Float)

    # integrity envelope
    payload: Mapped[str] = mapped_column(Text)  # canonical JSON exactly as signed
    signature: Mapped[str] = mapped_column(String(128))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_site_ts", "site_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    ts: Mapped[datetime] = mapped_column(DateTime)
    command: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    source_ip: Mapped[str] = mapped_column(String(45))
    user: Mapped[str] = mapped_column(String(60))
    protocol: Mapped[str] = mapped_column(String(30))
    is_write: Mapped[bool] = mapped_column(Boolean)
    attack_id: Mapped[int | None] = mapped_column(ForeignKey("attacks.id"), nullable=True)


class Attack(Base):
    __tablename__ = "attacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    started_real: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    original: Mapped[dict] = mapped_column(JSON, default=dict)  # what reset restores


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_site_status", "site_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_action: Mapped[str] = mapped_column(Text)
    mitre_technique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")

    attack_id: Mapped[int | None] = mapped_column(ForeignKey("attacks.id"), nullable=True)
    attack_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attack_started_real: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    detected_real: Mapped[datetime] = mapped_column(DateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_real: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    status: Mapped[str] = mapped_column(String(20), default="running")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_device: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"))
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    finding_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(160))
    evidence: Mapped[str] = mapped_column(Text)
    remediation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    remediated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
