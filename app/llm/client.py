"""Async LLM client supporting OpenAI-compatible streaming endpoints with robust fallback."""

from __future__ import annotations

import json
import re
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for LLM endpoints."""

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.deepseek.com/v1")
    model: str = Field(default="deepseek-chat")
    temperature: float = Field(default=0.2)
    timeout_seconds: float = Field(default=30.0)

    @classmethod
    def from_env(cls) -> LLMConfig:
        api_key = (
            os.getenv("PRISM_LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or ""
        )
        base_url = (
            os.getenv("PRISM_LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if "DASHSCOPE_API_KEY" in os.environ else "https://api.deepseek.com/v1")
        )
        model = os.getenv("PRISM_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-chat"
        return cls(api_key=api_key, base_url=base_url.rstrip("/"), model=model)


class AsyncLLMClient:
    """Async client for OpenAI-compatible streaming LLM calls."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key.strip())

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat completions from OpenAI-compatible API or fallback engine."""

        if not self.is_configured:
            # When API Key is not set, run smart local ReAct simulation
            async for chunk in self._stream_offline_simulation(messages, tools):
                yield chunk
            return

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        endpoint = f"{self.config.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            try:
                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        yield {
                            "type": "error",
                            "message": f"LLM API Error {response.status_code}: {err_body.decode('utf-8', errors='ignore')}",
                        }
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")
                            tool_calls = delta.get("tool_calls", [])

                            if reasoning:
                                yield {"type": "reasoning", "delta": reasoning}
                            if content:
                                yield {"type": "content", "delta": content}
                            if tool_calls:
                                yield {"type": "tool_call_delta", "delta": tool_calls}
                        except json.JSONDecodeError:
                            continue
            except Exception as exc:
                yield {"type": "error", "message": f"LLM Connection Error: {exc}"}

    async def _stream_offline_simulation(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Intelligent local fallback generator when API key is not configured."""
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = str(m.get("content", ""))
                break

        # Emit simulated thought process
        yield {
            "type": "reasoning",
            "delta": "【Prism 智能体思考流】\n1. 正在分析用户自然语言意图...\n2. 识别到关注标的/持仓风险，准备调度底层数据工具验证数据真实性...\n",
        }

        # Check intent
        explicit_code = re.search(r"(?<!\d)\d{6}(?:\.(?:SH|SZ|BJ))?(?!\d)", user_msg, re.IGNORECASE)
        if explicit_code:
            symbol = explicit_code.group().upper()
            is_fund = symbol.startswith(("510", "512", "513", "515", "588", "159")) or any(k in user_msg for k in ("基金", "ETF", "etf"))
            yield {"type": "tool_call", "name": "query_fund_lookthrough" if is_fund else "query_stock_quote",
                   "arguments": {"fund_code" if is_fund else "symbol": symbol}}
        elif any(k in user_msg for k in ("宁德", "比亚迪", "寒武纪", "茅台")):
            symbol = next(code for name, code in (("宁德", "300750"), ("比亚迪", "002594"), ("寒武纪", "688256"), ("茅台", "600519")) if name in user_msg)
            yield {
                "type": "tool_call",
                "name": "query_stock_quote",
                "arguments": {"symbol": symbol},
            }
        elif any(k in user_msg for k in ("科创50", "半导体ETF", "沪深300ETF")):
            code = "588000" if "科创50" in user_msg else "510300" if "沪深300ETF" in user_msg else "512480"
            yield {
                "type": "tool_call",
                "name": "query_fund_lookthrough",
                "arguments": {"fund_code": code},
            }
        elif any(k in user_msg for k in ("股票", "个股", "基金", "ETF", "etf", "穿透")):
            yield {"type": "content", "delta": "请提供要查询的证券代码，以免查询到其他标的。"}
        elif any(k in user_msg for k in ("体检", "持仓", "风险", "集中度", "超标")):
            yield {
                "type": "tool_call",
                "name": "run_portfolio_health_check",
                "arguments": {},
            }
        elif any(k in user_msg for k in ("调仓", "再平衡", "优化", "方案")):
            yield {
                "type": "tool_call",
                "name": "generate_portfolio_rebalance",
                "arguments": {"target_sector_cap": 0.30},
            }
        else:
            yield {
                "type": "tool_call",
                "name": "query_wencai_semantic",
                "arguments": {"query": user_msg},
            }
