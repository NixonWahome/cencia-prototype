from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import db
from ..db import get_db
from ..demo.attacks import ACTIONS_BY_RULE, AttackError
from ..detection.engine import utcnow
from ..detection.rules import RULES
from ..models import Alert
from ..runtime import Runtime
from .deps import get_rt
from .serializers import alert_dict

router = APIRouter(prefix="/api", tags=["alerts"])

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _with_actions(a: dict) -> dict:
    return {**a, "actions": ACTIONS_BY_RULE.get(a["rule_id"], []) if a["status"] != "resolved" else [],
            "rule_name": RULES[a["rule_id"]]["name"]}


@router.get("/alerts")
def list_alerts(site_id: str | None = None, status: str | None = Query(None, description="open|acknowledged|resolved|active"),
                severity: str | None = None, rule_id: str | None = None,
                limit: int = Query(200, ge=1, le=1000), db_: Session = Depends(get_db)):
    q = select(Alert)
    if site_id:
        q = q.where(Alert.site_id == site_id)
    if status == "active":
        q = q.where(Alert.status != "resolved")
    elif status:
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)
    if rule_id:
        q = q.where(Alert.rule_id == rule_id)
    rows = db_.scalars(q.order_by(Alert.detected_real.desc(), Alert.id.desc()).limit(limit)).all()
    return [_with_actions(alert_dict(a)) for a in rows]


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, db_: Session = Depends(get_db)):
    alert = db_.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return _with_actions(alert_dict(alert))


class AlertPatch(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]


@router.patch("/alerts/{alert_id}")
def patch_alert(alert_id: int, body: AlertPatch, rt: Runtime = Depends(get_rt)):
    with db.write_session() as s:
        alert = s.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(404, "alert not found")
        alert.status = body.status
        if body.status == "acknowledged" and alert.acknowledged_at is None:
            alert.acknowledged_at = rt.clock.now()
        if body.status == "resolved":
            alert.resolved_at, alert.resolved_real = rt.clock.now(), utcnow()
        elif body.status == "open":
            alert.resolved_at = alert.resolved_real = None
        result = _with_actions(alert_dict(alert))
    rt.ws.publish({"type": "alert_updated", "alert": result})
    return result


@router.post("/alerts/{alert_id}/actions/{action}")
def respond(alert_id: int, action: Literal["block_ip", "isolate", "restore_record"], rt: Runtime = Depends(get_rt)):
    try:
        return rt.attacks.respond(alert_id, action)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except AttackError as e:
        raise HTTPException(400, str(e))


@router.get("/detection/rules")
def detection_rules():
    return [{"rule_id": k, **v} for k, v in RULES.items()]


@router.get("/detection/models")
def detection_models(rt: Runtime = Depends(get_rt)):
    return rt.engine.anomaly.describe()
