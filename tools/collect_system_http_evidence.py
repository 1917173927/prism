import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import socket
from threading import Thread
import time
from uuid import uuid4

import httpx
import uvicorn

from tools.http_load_test import measure


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "output/system-test-report" / uuid4().hex
WORK.mkdir(parents=True)
os.environ["PRISM_SECRET_STORE_PATH"] = str(WORK / "secrets.json")
os.environ["PRISM_DB_PATH"] = str(WORK / "http.sqlite3")
for key in ("PRISM_DATABASE_URL", "PRISM_AUTH_ACCOUNTS_FILE", "PRISM_DEV_NO_AUTH"):
    os.environ.pop(key, None)

from app.api.main import app


async def collect(base):
    records = []

    def check(case_id, title, expected, response):
        actual = response.status_code
        records.append(dict(id=case_id, title=title, expected=expected, actual=actual,
                            status="PASS" if expected == actual else "FAIL"))
        assert actual == expected, (case_id, actual)

    async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=30,
                                 limits=httpx.Limits(max_connections=100, max_keepalive_connections=100)) as client:
        check("HTTP-01", "未登录访问受保护接口", 401,
              await client.get("/api/v1/advisor/profile/questionnaire-template"))
        password = token_urlsafe(24)
        response = await client.post("/api/v1/auth/register", json=dict(
            username="report-reader", password=password, password_confirmation=password))
        check("HTTP-02", "真实本地账户注册", 201, response)
        response = await client.get("/api/v1/advisor/profile/questionnaire-template")
        check("HTTP-03", "登录后读取问卷", 200, response)
        payload = response.json()
        assert len(payload["questions"]) == 19
        check("HTTP-04", "伪造账户标识被拒绝", 403,
              await client.get("/api/v1/advisor/profile/questionnaire-template", headers={"X-Owner-ID": "report-other-owner"}))
        check("HTTP-05", "跨站写入被拒绝", 403,
              await client.post("/api/v1/user/preferences", headers={"Origin": "https://untrusted.invalid"}, json={}))
        check("HTTP-06", "普通账户不能修改服务配置", 403,
              await client.post("/api/v1/runtime/data-mode", json={"mode": "LIVE"}))
        failures = []
        for endpoint in ("query-template", "research-matrix-template", "stock-research-template",
                         "fund-research-template", "convertible-bond-research-template", "scenario-simulation-template"):
            response = await client.get("/api/v1/advisor/" + endpoint)
            check("HTTP-07-" + str(len(failures)+1), endpoint, 409, response)
            failures.append(dict(endpoint=endpoint, response=response.json()))
        performance = await measure(client, base + "/api/v1/advisor/profile/questionnaire-template",
                                    concurrency=100, requests=1000)
        assert performance["failed"] == 0
        check("HTTP-08", "退出登录", 200, await client.post("/api/v1/auth/logout"))
        check("HTTP-09", "退出后访问被拒绝", 401,
              await client.get("/api/v1/advisor/profile/questionnaire-template"))
    output = dict(generated_at=datetime.now(UTC).isoformat(), tests=records,
                  unavailable_routes=failures, performance=performance,
                  scope="真实 TCP HTTP，独立 SQLite，单个已登录账户，问卷读取接口，100 并发任务及 1000 请求，不含模型和金融查询。")
    target = ROOT / "docs/submission/test-evidence/http-results.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(tests=len(records), performance=performance), ensure_ascii=False))


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 20
        try:
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("报告测试服务未启动")
                time.sleep(.05)
            asyncio.run(collect(f"http://127.0.0.1:{port}"))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "报告测试服务未终止"


if __name__ == "__main__":
    main()
