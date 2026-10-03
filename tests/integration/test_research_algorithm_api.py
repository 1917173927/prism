from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.algorithm_routes import create_algorithm_router


def test_algorithm_api_explicit_missing_data_and_contract():
    app = FastAPI()
    app.include_router(create_algorithm_router(lambda: "server-owner"))
    with TestClient(app) as client:
        body = {"source": "uploaded returns", "as_of": "2026-10-01T00:00:00Z", "series": {}}
        response = client.post("/api/v1/research/algorithms/covariance", json=body)
        assert response.status_code == 200
        assert response.json()["reason"] == "INSUFFICIENT_ASSETS"
        assert client.post("/api/v1/research/algorithms/covariance", json={**body, "owner_id": "other"}).status_code == 422
        assert "/api/v1/research/algorithms/five-factors" in client.get("/openapi.json").json()["paths"]
