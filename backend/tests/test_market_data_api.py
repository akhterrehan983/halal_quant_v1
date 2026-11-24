from io import BytesIO

from fastapi.testclient import TestClient

from app.data.sample_data import make_history
from app.main import app

client = TestClient(app)


def _csv_for_symbol(symbol: str) -> bytes:
    df = make_history(symbol, periods=75)
    buf = BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def test_v1_validate_csv():
    content = _csv_for_symbol("VALTEST")
    res = client.post(
        "/api/v1/market-data/validate",
        files={"file": ("VALTEST.csv", content, "text/csv")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total_rows"] == 75


def test_v1_import_csv_demo():
    content = _csv_for_symbol("IMPTST")
    res = client.post(
        "/api/v1/market-data/import/csv",
        files={"file": ("IMPTST.csv", content, "text/csv")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["inserted_rows"] >= 60
    assert "IMPTST" in body["symbols"]


def test_v1_quality_symbol():
    res = client.get("/api/v1/market-data/quality/TCS")
    assert res.status_code == 200
    assert res.json()["symbol"] == "TCS"