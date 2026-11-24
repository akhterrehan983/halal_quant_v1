from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class SimEvent:
    kind: str
    date: date
    symbol: str = ""
    detail: dict | None = None