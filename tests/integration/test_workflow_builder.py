from datetime import UTC, datetime
import asyncio

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.service.specialist_matrix import FixtureResearchSpecialistMatrixService


def test_workflow_cycles_scope_revision_and_bounded_execution(tmp_path):
    path = tmp_path / "workflows.sqlite3"
    headers = {"X-Owner-ID":"workflow-owner"}
    with TestClient(create_app(database_path=path, clock=lambda: datetime.now(UTC))) as client:
        initial = client.get("/api/v1/advisor/workflow", headers=headers).json()
        definition = initial["definition"]
        assert initial["revision"] == 0 and initial["data_mode"] == "MOCK"
        nodes = definition["nodes"]
        nodes[0]["dependencies"] = [nodes[1]["node_id"]]
        nodes[1]["dependencies"] = [nodes[0]["node_id"]]
        assert client.post("/api/v1/advisor/workflow", headers=headers,
                           json={"definition":definition, "expected_revision":0}).status_code == 422
        nodes[1]["dependencies"] = []
        saved = client.post("/api/v1/advisor/workflow", headers=headers,
                            json={"definition":definition, "expected_revision":0})
        assert saved.status_code == 200, saved.text
        assert client.post("/api/v1/advisor/workflow", headers={"X-Owner-ID":"other"},
                           json={"definition":definition, "expected_revision":0}).status_code == 403
        assert client.post("/api/v1/advisor/workflow", headers=headers,
                           json={"definition":definition, "expected_revision":0}).status_code == 409
        result = client.post("/api/v1/advisor/workflow-runs", headers=headers, json={"expected_revision":1})
        assert result.status_code == 200, result.text
        assert result.json()["is_synthetic"] is True
        assert result.json()["definition_revision"] == 1
        run = result.json()["result"]["execution"]["state"]
        assert run["status"] == "COMPLETED"
        node = next(n for n in run["nodes"] if n["node_id"] == nodes[0]["node_id"])
        assert node["dependencies"] == nodes[0]["dependencies"]
        assert client.post("/api/v1/advisor/workflow-runs", headers=headers, json={"expected_revision":2}).status_code == 409
    with TestClient(create_app(database_path=path)) as client:
        assert client.get("/api/v1/advisor/workflow", headers=headers).json()["revision"] == 1
        assert client.get("/api/v1/advisor/workflow", headers={"X-Owner-ID":"other"}).json()["revision"] == 0


def test_workflow_deadline_cancels_executor(tmp_path):
    class SlowService(FixtureResearchSpecialistMatrixService):
        closed = False

        async def run(self, request, *, matrix_override=None):
            try:
                await asyncio.sleep(10)
            finally:
                self.closed = True

    service = SlowService()
    with TestClient(create_app(database_path=tmp_path / "deadline.sqlite3", specialist_service=service)) as client:
        headers = {"X-Owner-ID":"deadline-owner"}
        definition = client.get("/api/v1/advisor/workflow", headers=headers).json()["definition"]
        definition["budget_ms"] = 1000
        saved = client.post("/api/v1/advisor/workflow", headers=headers,
                            json={"definition":definition, "expected_revision":0})
        assert saved.status_code == 200, saved.text
        result = client.post("/api/v1/advisor/workflow-runs", headers=headers, json={"expected_revision":1})
        assert result.status_code == 408
        assert result.json()["error_code"] == "WORKFLOW_DEADLINE"
        assert service.closed
