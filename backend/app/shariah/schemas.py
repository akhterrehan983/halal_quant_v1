from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class EligibilityStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    EXPIRED = "EXPIRED"


class PolicyMode(str, Enum):
    ALL_STANDARDS = "ALL_STANDARDS"
    ANY_STANDARD = "ANY_STANDARD"
    PRIMARY = "PRIMARY"


class ActivityResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ScreeningProfile(BaseModel):
    profile_id: str
    name: str
    standard_ids: list[str]
    policy: PolicyMode = PolicyMode.PRIMARY
    primary_standard_id: str | None = None
    review_days: int = 90


class RatioDetail(BaseModel):
    name: str
    numerator: Decimal | None = None
    denominator: Decimal | None = None
    value: Decimal | None = None
    threshold: Decimal | None = None
    result: str = "UNKNOWN"
    reporting_period: str | None = None
    data_source: str | None = None


class BusinessActivityCheck(BaseModel):
    category: str
    result: ActivityResult
    source: str | None = None
    verified_at: date | None = None
    notes: str = ""


class EligibilityRecord(BaseModel):
    symbol: str
    standard_id: str
    standard_version: str
    status: EligibilityStatus
    business_activity: list[BusinessActivityCheck] = Field(default_factory=list)
    ratios: list[RatioDetail] = Field(default_factory=list)
    effective_date: date | None = None
    verified_at: date | None = None
    next_review_date: date | None = None
    explanation: str = ""
    sources: list[str] = Field(default_factory=list)


class ScreeningSnapshot(BaseModel):
    snapshot_id: int | None = None
    symbol: str
    standard_id: str
    standard_version: str
    screening_date: date
    reporting_period: str | None = None
    status: EligibilityStatus
    payload: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class PurificationRecord(BaseModel):
    symbol: str
    income_amount: Decimal
    purification_ratio: Decimal | None = None
    purification_amount: Decimal | None = None
    methodology: str
    standard_id: str
    reporting_period: str | None = None
    note: str = "Display only — not a payment instruction."


class OwnershipPossessionState(str, Enum):
    NOT_OWNED = "NOT_OWNED"
    ORDER_PENDING = "ORDER_PENDING"
    EXECUTED_UNSETTLED = "EXECUTED_UNSETTLED"
    SETTLED_PENDING_VERIFICATION = "SETTLED_PENDING_VERIFICATION"
    OWNERSHIP_VERIFIED = "OWNERSHIP_VERIFIED"
    POSSESSION_VERIFIED = "POSSESSION_VERIFIED"
    SELL_AUTHORIZED = "SELL_AUTHORIZED"
    OWNERSHIP_REVERSED = "OWNERSHIP_REVERSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class OwnershipEvent(BaseModel):
    event_id: int | None = None
    symbol: str
    state: OwnershipPossessionState
    timestamp: datetime | None = None
    evidence: str = ""
    policy_id: str = "conservative_delivery"
    verifier: str | None = None
    reason: str = ""