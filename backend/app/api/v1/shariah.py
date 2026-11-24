from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.shariah import business_activity
from app.shariah.policies import list_profiles, upsert_profile
from app.shariah.purification import calculate_purification
from app.shariah.schemas import ScreeningProfile
from app.shariah.screening import run_screening
from app.shariah.snapshots import append_snapshot  # noqa: F401
from app.shariah.standards import list_standards
from app.shariah import store
from app.shariah.store import list_snapshots

router = APIRouter(tags=["shariah"])


class EvaluateBody(BaseModel):
    profile_id: str = "default"
    financials: dict | None = None
    business_activity: list[dict] | None = None


class PurificationBody(BaseModel):
    income_amount: float
    purification_ratio: float | None = None
    methodology: str = "user_supplied"
    standard_id: str = "aaoifi_demo_v1"
    reporting_period: str | None = None


@router.get("/shariah/standards")
def shariah_standards():
    return {"items": list_standards()}


@router.get("/shariah/profiles")
def shariah_profiles():
    return {"items": [p.model_dump() for p in list_profiles()]}


@router.post("/shariah/profiles")
def create_profile(body: ScreeningProfile):
    return upsert_profile(body).model_dump()


@router.patch("/shariah/profiles/{profile_id}")
def patch_profile(profile_id: str, body: ScreeningProfile):
    body.profile_id = profile_id
    return upsert_profile(body).model_dump()


@router.get("/shariah/screening/{symbol}")
def get_screening(symbol: str):
    rec = store.get_latest_eligibility(symbol.upper())
    if not rec:
        raise HTTPException(404, "No screening — POST evaluate with financial data")
    return rec.model_dump(mode="json")


@router.post("/shariah/screening/{symbol}/evaluate")
def evaluate_screening(symbol: str, body: EvaluateBody | None = None):
    body = body or EvaluateBody()
    if body.financials:
        store.save_financials(symbol.upper(), body.financials)
    if body.business_activity:
        business_activity.submit_activity(symbol.upper(), body.business_activity)
    rec = run_screening(symbol.upper(), profile_id=body.profile_id, financials=body.financials)
    return rec.model_dump(mode="json")


@router.get("/shariah/snapshots/{symbol}")
def snapshots(symbol: str):
    return {"symbol": symbol.upper(), "snapshots": [s.model_dump(mode="json") for s in list_snapshots(symbol.upper())]}


@router.get("/shariah/purification")
def purification_query(symbol: str, income_amount: float, purification_ratio: float | None = None):
    rec = calculate_purification(
        symbol,
        income_amount,
        purification_ratio=purification_ratio,
        methodology="user_supplied",
        standard_id="aaoifi_demo_v1",
    )
    return rec.model_dump(mode="json")


@router.post("/shariah/purification")
def purification_calc(body: PurificationBody, symbol: str):
    rec = calculate_purification(
        symbol.upper(),
        body.income_amount,
        purification_ratio=body.purification_ratio,
        methodology=body.methodology,
        standard_id=body.standard_id,
        reporting_period=body.reporting_period,
    )
    return rec.model_dump(mode="json")