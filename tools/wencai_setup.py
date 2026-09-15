"""Local Windows deployment helper for testing and replacing Wencai credentials.

Run ``python -m tools.wencai_setup`` to test the existing credential, or add
``--configure`` to enter a replacement without echoing it or using shell history.
Only a credential passing all nine installed skill probes replaces the old one.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
import warnings

from app.providers.skillhub import WencaiSkillHubProvider
from app.security import ProtectedSecretStore, SecretProtectionError


async def verify_and_save(store, config: dict, *, save: bool) -> bool:
    provider = WencaiSkillHubProvider(api_key=config["api_key"], base_url="https://openapi.iwencai.com")
    results = await provider.probe_installed_skills()
    for row in results:
        print(f"{row['skill_id']}: {row['status']} ({row.get('error_code') or 'OK'})")
    passed = len(results) == 9 and all(row["status"] in {"SUCCESS", "PARTIAL"} and row.get("item_count", 0) > 0 for row in results)
    if passed and save:
        store.set("provider:wencai", json.dumps({
            "api_key": config["api_key"], "base_url": "https://openapi.iwencai.com", "contract_verified": True,
            "verified_skills": [row["skill_id"] for row in results],
        }))
        print("PASS：已使用 Windows 加密存储保存。请重新启动 Prism，使服务读取新配置。")
    elif passed:
        print("PASS：现有凭据与九项数据能力验证通过。")
    else:
        print("FAILED：凭据或数据权限未通过验证，原配置未修改。")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="验证或更新本机问财凭据，不显示密钥。")
    parser.add_argument("--configure", action="store_true", help="安全输入新 Key，验证通过后保存")
    args = parser.parse_args()
    path = os.getenv("PRISM_SECRET_STORE_PATH") or str(Path(__file__).resolve().parents[1] / "data/private/prism-secrets.json")
    try:
        store = ProtectedSecretStore(path)
        if args.configure:
            # Refuse getpass's echoing fallback in redirected/noninteractive shells.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("请输入问财 API Key（输入不显示）：").strip()
            config = {"api_key": key}
        else:
            encoded = store.get("provider:wencai")
            config = json.loads(encoded) if encoded else {}
        if not isinstance(config, dict) or not isinstance(config.get("api_key"), str) or not config["api_key"].strip():
            print("未配置有效 Key；请使用 --configure 输入问财凭据。")
            return 1
        return 0 if asyncio.run(verify_and_save(store, config, save=args.configure)) else 1
    except (SecretProtectionError, ValueError, OSError, getpass.GetPassWarning):
        print("未能完成配置，请在本机交互式终端运行并检查 Windows 安全存储。原配置未替换。")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("已取消。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
