from __future__ import annotations

from datetime import date

from app.shariah.schemas import ActivityResult, BusinessActivityCheck
from app.shariah.standards import ScreeningStandard

# User-supplied classifications only (symbol -> categories). Not auto-filled in production paths.
USER_ACTIVITY: dict[str, list[dict]] = {}


def submit_activity(symbol: str, entries: list[dict]) -> None:
    USER_ACTIVITY[symbol.upper()] = entries


def evaluate_business_activity(symbol: str, standard: ScreeningStandard) -> list[BusinessActivityCheck]:
    entries = USER_ACTIVITY.get(symbol.upper(), [])
    if not entries:
        return [
            BusinessActivityCheck(
                category="overall",
                result=ActivityResult.UNKNOWN,
                source=None,
                notes="No business activity classification on file",
            )
        ]
    checks: list[BusinessActivityCheck] = []
    for e in entries:
        cat = e.get("category", "unknown")
        prohibited = cat in standard.business_exclusions or e.get("prohibited") is True
        result = ActivityResult.FAIL if prohibited else ActivityResult.PASS
        if e.get("confidence") == "low":
            result = ActivityResult.NEEDS_REVIEW
        checks.append(
            BusinessActivityCheck(
                category=cat,
                result=result,
                source=e.get("source"),
                verified_at=date.fromisoformat(e["verified_at"]) if e.get("verified_at") else None,
                notes=e.get("notes", ""),
            )
        )
    return checks


def activity_passes(checks: list[BusinessActivityCheck]) -> bool:
    return all(c.result == ActivityResult.PASS for c in checks) and len(checks) > 0


def activity_blocks(checks: list[BusinessActivityCheck]) -> bool:
    return any(c.result == ActivityResult.FAIL for c in checks)