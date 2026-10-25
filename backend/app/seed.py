"""Seed static data: sites, devices and edge signing keys."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .integrity.keys import generate_keypair
from .models import Device, EdgeKey, Site
from .scanner.inventory import INVENTORY
from .simulator.sites import SITES


def seed_static(session: Session) -> None:
    for spec in SITES:
        site = Site(**{k: v for k, v in spec.items() if k != "devices"})
        session.add(site)
        session.flush()
        for device_id, kind, name, capacity_kw in spec["devices"]:
            device = Device(id=device_id, site_id=site.id, kind=kind, name=name,
                            capacity_kw=capacity_kw, **INVENTORY[device_id])
            if kind == "inverter":  # inverters are the devices that stream signed telemetry
                private_hex, device.public_key = generate_keypair()
            session.add(device)
            if kind == "inverter":
                session.flush()  # EdgeKey has no ORM relationship, so insert the device first
                session.add(EdgeKey(device_id=device_id, private_key=private_hex))
