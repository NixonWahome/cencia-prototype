"""Demo controls: attacks, reset, clock speed/jump, model retraining."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import db
from ..demo.attacks import AttackError
from ..models import Attack
from ..runtime import Runtime
from .deps import get_rt
from .serializers import attack_dict

router = APIRouter(prefix="/api/demo", tags=["demo"])


class SpeedIn(BaseModel):
    multiplier: float = Field(..., ge=1, le=600)


class JumpIn(BaseModel):
    hour: float = Field(..., ge=0, lt=24, description="EAT hour to jump forward to, e.g. 1.0 or 10.5")


@router.get("/attacks")
def attacks(rt: Runtime = Depends(get_rt)):
    with db.read_session() as s:
        active = [attack_dict(a) for a in s.scalars(select(Attack).where(Attack.active.is_(True)))]
    return {"catalog": rt.attacks.catalog(), "active": active, "blocklist": sorted(rt.attacks.blocklist)}


@router.post("/attack/{attack_type}")
async def attack(attack_type: str, rt: Runtime = Depends(get_rt)):
    try:
        result = await asyncio.to_thread(rt.attacks.launch, attack_type)
    except AttackError as e:
        raise HTTPException(404, str(e))
    await rt.ws.broadcast({"type": "attack", "attack": result})
    return result


@router.post("/reset")
async def reset(rt: Runtime = Depends(get_rt)):
    return await asyncio.to_thread(rt.attacks.reset)


@router.post("/retrain")
async def retrain(rt: Runtime = Depends(get_rt)):
    return await asyncio.to_thread(rt.retrain)


@router.post("/speed")
def set_speed(body: SpeedIn, rt: Runtime = Depends(get_rt)):
    rt.clock.set_speed(body.multiplier)
    return rt.sim_status()


@router.post("/jump")
async def jump(body: JumpIn, rt: Runtime = Depends(get_rt)):
    """Jump forward to the next occurrence of `hour`; the gap is backfilled."""
    rt.clock.jump_to_hour(body.hour)
    due = await asyncio.to_thread(rt.simulator.catch_up)
    rt.engine.flush()
    if due:
        await rt.ws.broadcast(rt.simulator.tick_message(len(due)))
    return {**rt.sim_status(), "backfilled_intervals": len(due)}
