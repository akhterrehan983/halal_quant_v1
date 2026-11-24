from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConflictPolicy(str, Enum):
    REJECT = "reject"
    SKIP = "skip"
    UPDATE = "update"


class CandleRow(BaseModel):
    symbol: str
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None
    exchange: str = "NSE"


class ValidationIssue(BaseModel):
    level: str  # error | warning
    code: str
    message: str
    symbol: str | None = None
    trading_date: date | None = None
    row_index: int | None = None


class ValidationReport(BaseModel):
    valid_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows_in_file: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    missing_sessions: dict[str, list[str]] = Field(default_factory=dict)
    missing_sessions_approximate: bool = True
    outliers: list[ValidationIssue] = Field(default_factory=list)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "valid_rows": self.valid_rows,
            "rejected_rows": self.rejected_rows,
            "duplicate_rows_in_file": self.duplicate_rows_in_file,
            "issue_count": len(self.issues),
            "warning_count": len(self.warnings),
            "outlier_count": len(self.outliers),
            "missing_sessions_approximate": self.missing_sessions_approximate,
        }


class ImportSummary(BaseModel):
    import_id: int | None = None
    status: str
    filename: str | None = None
    total_rows_received: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    skipped_rows: int = 0
    duplicate_rows: int = 0
    symbols: list[str] = Field(default_factory=list)
    date_range: dict[str, str | None] = Field(default_factory=dict)
    conflict_policy: str = "skip"
    validation: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None