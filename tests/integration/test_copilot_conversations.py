from fastapi.testclient import TestClient

from app.api.main import create_app


def _headers(owner: str) -> dict[str, str]:
    return {"X-Owner-ID": owner}


def test_server_conversations_persist_follow_up_history_and_restart(tmp_path):
    database = tmp_path / "copilot-conversations.db"
    with TestClient(create_app(database_path=database)) as client:
        created = client.post(
            "/api/v1/copilot/conversations",
            headers=_headers("alice"),
            json={"title": "新对话"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["conversation_id"]

        first = client.post(
            "/api/v1/copilot/chat",
            headers=_headers("alice"),
            json={
                "owner_id": "alice",
                "conversation_id": conversation_id,
                "message": "什么是市盈率",
                "model_mode": "MOCK",
            },
        )
        assert first.status_code == 200
        assert '"persisted": true' in first.text

        follow_up = client.post(
            "/api/v1/copilot/chat",
            headers=_headers("alice"),
            json={
                "owner_id": "alice",
                "conversation_id": conversation_id,
                "message": "那市净率呢",
                "model_mode": "MOCK",
                "history": [
                    {"role": "user", "content": "客户端伪造问题"},
                    {"role": "assistant", "content": "客户端伪造回复"},
                ],
            },
        )
        assert follow_up.status_code == 200
        assert "最近 **2 条历史消息**" in follow_up.text
        assert "什么是市盈率" in follow_up.text
        assert "客户端伪造问题" not in follow_up.text

        detail = client.get(
            f"/api/v1/copilot/conversations/{conversation_id}",
            headers=_headers("alice"),
        )
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["title"] == "什么是市盈率"
        assert [item["role"] for item in payload["messages"]] == [
            "user", "assistant", "user", "assistant"
        ]
        assert payload["messages"][0]["content"] == "什么是市盈率"
        assert payload["messages"][2]["content"] == "那市净率呢"
        assert payload["answer_count"] == 2
        assert payload["message_count"] == 4

        assert client.get(
            f"/api/v1/copilot/conversations/{conversation_id}",
            headers=_headers("bob"),
        ).status_code == 404

    with TestClient(create_app(database_path=database)) as reopened:
        listing = reopened.get(
            "/api/v1/copilot/conversations", headers=_headers("alice")
        )
        assert listing.status_code == 200
        assert listing.json()["items"][0]["conversation_id"] == conversation_id
        assert listing.json()["items"][0]["answer_count"] == 2


def test_conversations_support_multiple_threads_rename_delete_and_owner_scope(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "threads.db")) as client:
        first = client.post(
            "/api/v1/copilot/conversations", headers=_headers("alice"), json={}
        ).json()
        second = client.post(
            "/api/v1/copilot/conversations",
            headers=_headers("alice"),
            json={"title": "第二组研究"},
        ).json()
        assert [item["conversation_id"] for item in client.get(
            "/api/v1/copilot/conversations", headers=_headers("alice")
        ).json()["items"]] == [second["conversation_id"], first["conversation_id"]]

        renamed = client.patch(
            f"/api/v1/copilot/conversations/{first['conversation_id']}",
            headers=_headers("alice"),
            json={"title": "估值概念学习"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "估值概念学习"

        assert client.delete(
            f"/api/v1/copilot/conversations/{second['conversation_id']}",
            headers=_headers("bob"),
        ).status_code == 404
        assert client.delete(
            f"/api/v1/copilot/conversations/{second['conversation_id']}",
            headers=_headers("alice"),
        ).status_code == 200
        remaining = client.get(
            "/api/v1/copilot/conversations", headers=_headers("alice")
        ).json()["items"]
        assert [item["conversation_id"] for item in remaining] == [first["conversation_id"]]
