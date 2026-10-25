"""The three demo sites. Names, vendors and locations are fictional."""
from __future__ import annotations

from dataclasses import dataclass, field

SITES: list[dict] = [
    {
        "id": "kibwezi",
        "name": "Kibwezi Solar Park (Demo)",
        "site_type": "Utility solar / IPP",
        "capacity_kwp": 1200.0,
        "location": "Makueni County (demo)",
        "latitude": -2.41,
        "longitude": 37.96,
        "ambient_base_c": 24.0,
        "nominal_ac_v": 400.0,
        "emission_baseline": "grid",
        "devices": [
            ("KIB-INV-01", "inverter", "Inverter 1", 300.0),
            ("KIB-INV-02", "inverter", "Inverter 2", 300.0),
            ("KIB-INV-03", "inverter", "Inverter 3", 300.0),
            ("KIB-INV-04", "inverter", "Inverter 4", 300.0),
            ("KIB-SCADA-01", "scada_gateway", "SCADA gateway", None),
            ("KIB-WX-01", "weather_station", "Weather station", None),
        ],
    },
    {
        "id": "naivasha",
        "name": "Naivasha Mini-Grid (Demo)",
        "site_type": "Mini-grid",
        "capacity_kwp": 250.0,
        "location": "Nakuru County (demo)",
        "latitude": -0.72,
        "longitude": 36.43,
        "ambient_base_c": 18.0,
        "nominal_ac_v": 230.0,
        "emission_baseline": "diesel",
        "devices": [
            ("NAI-INV-01", "inverter", "Inverter 1", 125.0),
            ("NAI-INV-02", "inverter", "Inverter 2", 125.0),
            ("NAI-BAT-01", "battery_controller", "Battery controller", None),
            ("NAI-MTR-01", "meter_concentrator", "Smart-meter concentrator", None),
        ],
    },
    {
        "id": "thika",
        "name": "Thika C&I Rooftop (Demo)",
        "site_type": "Commercial rooftop",
        "capacity_kwp": 500.0,
        "location": "Kiambu County (demo)",
        "latitude": -1.03,
        "longitude": 37.07,
        "ambient_base_c": 20.0,
        "nominal_ac_v": 400.0,
        "emission_baseline": "grid",
        "devices": [
            ("THK-INV-01", "inverter", "Inverter 1", 166.7),
            ("THK-INV-02", "inverter", "Inverter 2", 166.7),
            ("THK-INV-03", "inverter", "Inverter 3", 166.6),
            ("THK-IOT-01", "iot_gateway", "IoT gateway", None),
        ],
    },
]


@dataclass(frozen=True)
class InverterSpec:
    id: str
    site_id: str
    capacity_kw: float
    nominal_ac_v: float


@dataclass(frozen=True)
class SiteSpec:
    id: str
    capacity_kwp: float
    ambient_base_c: float
    nominal_ac_v: float
    allowlist: list[str]
    inverters: list[InverterSpec] = field(default_factory=list)
    other_device_ids: list[str] = field(default_factory=list)
