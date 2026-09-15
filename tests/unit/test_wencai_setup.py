"""Credential replacement must never overwrite a working slot on failed probes."""
import asyncio

import pytest

from tools.wencai_setup import verify_and_save


@pytest.mark.parametrize("passed", [True, False])
def test_credential_replacement_is_verified_and_never_printed(monkeypatch, capsys, passed):
    writes = []
    class Store:
        def set(self, slot, value):
            writes.append((slot, value))
    class Provider:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "https://openapi.iwencai.com"
        async def probe_installed_skills(self):
            return [{"skill_id": str(i), "status": "SUCCESS" if passed else "FAILED", "item_count": 1 if passed else 0} for i in range(9)]
    monkeypatch.setattr("tools.wencai_setup.WencaiSkillHubProvider", Provider)
    assert asyncio.run(verify_and_save(Store(), {"api_key": "secret-not-for-output"}, save=True)) == passed
    assert len(writes) == int(passed)
    assert "secret-not-for-output" not in capsys.readouterr().out
