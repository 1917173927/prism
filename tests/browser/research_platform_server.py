"""Isolated browser-test API: temporary storage, empty environment, no network providers."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    # Preserve only operating-system execution paths, never provider credentials.
    operating_environment = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT"}}
    os.environ.clear()
    os.environ.update(operating_environment)
    with TemporaryDirectory(prefix="prism-browser-test-") as temporary:
        os.environ.update({"PRISM_DB_PATH": str(Path(temporary) / "module.sqlite3"), "PRISM_SECRET_STORE_PATH": str(Path(temporary) / "empty-secrets.json"), "PRISM_DEV_NO_AUTH": "1"})
        from app.api.main import create_app
        from app.providers.contracts import ProviderRecord, ProviderResult
        from app.providers.fingerprint import compute_request_fingerprint
        from app.providers.live_market import MarketDataProvider
        from app.providers.skillhub import WencaiSkillHubProvider
        import uvicorn

        class NoMarket(MarketDataProvider):
            async def get_quote(self, code):
                return None

            async def get_index_quote(self, symbol):
                return None

        class Unavailable:
            is_configured = False

        class BrowserProbe(WencaiSkillHubProvider):
            async def execute(self, request, **kwargs):
                return ProviderResult(request_id=request.request_id, request_fingerprint=compute_request_fingerprint(request), provider=self.name, status="SUCCESS", retrieved_at=datetime.now(UTC), records=(ProviderRecord(source="isolated browser-test stub", fields={"items": [{"name": "test observation"}]}),))

        application = create_app(database_path=Path(temporary) / "browser.sqlite3", auth_enabled=False, market_provider=NoMarket(), yahoo_finance_provider=Unavailable(), etnet_provider=Unavailable(), wencai_provider=BrowserProbe())
        uvicorn.run(application, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
