from __future__ import annotations

import pytest
from sqlalchemy import select

from app import db
from app.config import Settings
from app.models import Telemetry
from app.runtime import build_runtime


@pytest.fixture
def settings(tmp_path) -> Settings:
    # 1x clock: real time spent in a slow test must not add surprise intervals
    return Settings(db_path=str(tmp_path / "test.db"), history_days=1, run_background=False, sim_speed=1.0)


@pytest.fixture
def rt(settings):
    db.init_db(settings.db_path, reset=True)
    runtime = build_runtime(settings)
    yield runtime
    db.dispose()


@pytest.fixture
def client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as c:
        yield c


def telemetry_rows(device_id: str) -> list[Telemetry]:
    with db.read_session() as s:
        return s.scalars(select(Telemetry).where(Telemetry.device_id == device_id).order_by(Telemetry.seq)).all()
