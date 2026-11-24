from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.portfolio import store
from app.portfolio.schemas import AllocationProposal
from app.risk import manager as risk_manager
from app.risk.schemas import RiskConfiguration, RiskEvent

router = APIRouter(tags=["risk"])


@router.get("/risk/config")
def get_risk_config():
    return risk_manager.get_config().model_dump(mode="json")


class RiskConfigPatch(BaseModel):
    swing_capital_pct: float | None = None
    positional_capital_pct: float | None = None
    cash_reserve_pct: float | None = None


@router.patch("/risk/config")
def patch_risk_config(body: RiskConfigPatch):
    cfg = risk_manager.get_config()
    data = cfg.model_dump()
    for k, v in body.model_dump(exclude_none=True).items():
        data[k] = str(v)
    updated = RiskConfiguration.model_validate(data)
    try:
        return risk_manager.update_config(updated).model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/risk/exposure")
def risk_exposure():
    return risk_manager.exposure_report()


@router.get("/risk/limits")
def risk_limits():
    cfg = risk_manager.get_config()
    return {
        "swing": cfg.swing.model_dump(mode="json"),
        "positional": cfg.positional.model_dump(mode="json"),
        "notice": "Initial defaults — not empirically validated.",
    }


@router.get("/risk/events")
def risk_events():
    state = store.load_book()
    return {"events": [e.model_dump(mode="json") for e in state.risk_events[-50:]]}


class ValidateAllocationBody(BaseModel):
    proposal: dict


@router.post("/risk/validate-allocation")
def validate_allocation_endpoint(body: ValidateAllocationBody):
    prop = AllocationProposal.model_validate(body.proposal)
    result = risk_manager.validate_proposal(prop)
    return result.model_dump(mode="json")