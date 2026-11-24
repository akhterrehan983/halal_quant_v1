from datetime import date

from fastapi import APIRouter, HTTPException

from app.regime.classifier import classify_market

router = APIRouter(tags=["regime"])


@router.get("/regime/current")
def regime_current():
    classification = classify_market()
    return classification.model_dump(mode="json")


@router.get("/regime/history")
def regime_history(limit: int = 30):
    """Historical as-of classifications on benchmark index (no look-ahead)."""
    points = []
    for i in range(-limit, 0):
        c = classify_market(as_of_index=i)
        points.append(c.model_dump(mode="json"))
    return {"count": len(points), "history": points}