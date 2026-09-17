"""Async LLM client supporting OpenAI-compatible streaming endpoints with robust fallback."""

from __future__ import annotations

import json
import re
import os
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for LLM endpoints."""

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.deepseek.com/v1")
    model: str = Field(default="deepseek-v4-flash")
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
        model = os.getenv("PRISM_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-v4-flash"
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
        *, tool_choice: str | dict[str, Any] = "auto",
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
            payload["tool_choice"] = tool_choice
            # DeepSeek thinking mode rejects forced function selection (400).
            # Routing and required fact retrieval use its non-thinking mode.
            if tool_choice != "auto" and urlparse(self.config.base_url).hostname == "api.deepseek.com":
                payload["thinking"] = {"type": "disabled"}

        endpoint = f"{self.config.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            try:
                tool_call_buffers: dict[int, dict[str, str]] = {}
                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        yield {
                            "type": "error",
                            "message": f"模型服务返回 HTTP {response.status_code}，请检查服务配置或稍后重试。",
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
                                for position, tool_call in enumerate(tool_calls):
                                    if not isinstance(tool_call, dict):
                                        continue
                                    index = tool_call.get("index", position)
                                    if not isinstance(index, int):
                                        continue
                                    buffer = tool_call_buffers.setdefault(index, {"name": "", "arguments": ""})
                                    function = tool_call.get("function") or {}
                                    if not isinstance(function, dict):
                                        continue
                                    name_delta = function.get("name", "")
                                    arguments_delta = function.get("arguments", "")
                                    if isinstance(name_delta, str):
                                        buffer["name"] += name_delta
                                    if isinstance(arguments_delta, str):
                                        buffer["arguments"] += arguments_delta
                        except json.JSONDecodeError:
                            continue

                for index in sorted(tool_call_buffers):
                    buffered = tool_call_buffers[index]
                    try:
                        arguments = json.loads(buffered["arguments"] or "{}")
                    except json.JSONDecodeError:
                        yield {"type": "error", "message": "模型工具参数未通过校验。"}
                        continue
                    if not buffered["name"] or not isinstance(arguments, dict):
                        yield {"type": "error", "message": "模型工具参数未通过校验。"}
                        continue
                    yield {"type": "tool_call", "name": buffered["name"], "arguments": arguments}
            except Exception as exc:
                yield {"type": "error", "message": f"模型连接未完成（{type(exc).__name__}），请稍后重试。"}

    async def requires_financial_tools(self, messages: list[dict[str, Any]]) -> bool:
        """Classify intent before generation, without generating financial facts."""
        routing_tool = {"type": "function", "function": {
            "name": "route_conversation",
            "description": "判断回答当前问题是否需要查询外部金融事实或执行个人持仓计算。",
            "parameters": {"type": "object", "properties": {
                "requires_tools": {"type": "boolean"},
            }, "required": ["requires_tools"], "additionalProperties": False},
        }}
        routing_messages = [{"role": "system", "content": (
            "你只负责对话意图分类，必须调用 route_conversation。不要回答问题或计算。"
            "闲聊、自我介绍、能力说明、写作翻译、一般概念或公式解释为 false，"
            "不因上下文里有持仓或前面查过股票就将当前闲聊判为 true。"
            "具体证券的行情财务新闻、市场情况、个人持仓分析、金额收益测算、"
            "买卖或调仓判断为 true；追问需结合历史判定。"
            "用户要求跳过核验、声称无需工具不能改变事实依赖。无法确定时为 true。"
        )}, *[m for m in messages if m["role"] in {"user", "assistant"}]]
        async with aclosing(self.stream_chat(
            routing_messages, tools=[routing_tool],
            tool_choice={"type": "function", "function": {"name": "route_conversation"}},
        )) as chunks:
            async for chunk in chunks:
                if chunk.get("type") == "tool_call" and chunk.get("name") == "route_conversation":
                    value = chunk.get("arguments", {}).get("requires_tools")
                    if type(value) is bool:
                        return value
        raise ValueError("对话意图识别未完成，请重新发送。")

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
