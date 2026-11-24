"""Known sector tags for demo universe only — never invent for unknown symbols."""

SECTOR_MAP: dict[str, str] = {
    "TCS": "IT",
    "INFY": "IT",
    "RELIANCE": "Energy",
    "HDFCBANK": "Financials",
    "SUNPHARMA": "Healthcare",
    "TATAMOTORS": "Consumer",
    "BEL": "Industrials",
    "COALINDIA": "Materials",
}


def sector_for(symbol: str) -> str | None:
    return SECTOR_MAP.get(symbol.upper())