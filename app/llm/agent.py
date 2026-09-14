"""Copilot ReAct Agent core that coordinates tools, live providers, and streaming output."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, Field

from app.llm.client import AsyncLLMClient, LLMConfig
from app.llm.prompts import (
    COPILOT_SYSTEM_PROMPT,
    COPILOT_TOOLS,
    PORTFOLIO_PARSER_PROMPT,
)
from app.providers.live_market import (
    LiveMarketProvider,
    StaticMarketProvider,
    A_SHARE_DATABASE,
    ETF_LOOKTHROUGH_DATABASE,
)
from app.providers.fixture_wencai import FixtureWencaiProvider, FIXTURE_WENCAI_DATABASE
from app.providers.skillhub import WencaiSkillHubProvider
from app.providers.live_wencai import LiveWencaiProvider
from app.providers.fuyao import (
    CAPABILITY_FAILURE_CODES,
    FuyaoFinanceProvider,
    FuyaoProviderError,
)
from app.runtime.mode import DataMode, get_runtime_mode_controller


class CopilotMessage(BaseModel):
    role: str = Field(description="Role: user, assistant, system, or tool")
    content: str = Field(default="")
    name: str | None = None


class ChatStreamChunk(BaseModel):
    type: str = Field(description="Event type: thinking, tool_call, tool_result, token, decision, error, done")
    data: dict[str, Any] = Field(default_factory=dict)


class CopilotAgent:
    """Intelligent ReAct agent for conversational investment advisory with live tool execution."""

    def __init__(
        self,
        llm_client: AsyncLLMClient | None = None,
        live_finance_provider: FuyaoFinanceProvider | None = None,
        skillhub_provider: WencaiSkillHubProvider | None = None,
    ) -> None:
        self.client = llm_client or AsyncLLMClient()
        self.static_market_provider = StaticMarketProvider()
        self.market_provider = self.static_market_provider
        self.skillhub_provider = skillhub_provider or WencaiSkillHubProvider()
        self.fixture_wencai_provider = FixtureWencaiProvider()
        self.wencai_provider = self.skillhub_provider
        self.live_finance_provider = live_finance_provider or FuyaoFinanceProvider()

    async def stream_chat(
        self,
        user_message: str,
        history: list[CopilotMessage] | None = None,
        persona_info: dict[str, Any] | None = None,
        portfolio_context: dict[str, Any] | None = None,
        llm_config: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream real-time multi-agent thinking, tool execution, and grounded advisory response."""

        active_client = AsyncLLMClient(LLMConfig(**llm_config)) if (llm_config and llm_config.get("api_key")) else self.client

        if persona_info:
            persona = persona_info
            persona_context = (
                f"\n【当前咨询用户画像】：\n"
                f"- 姓名：{persona.get('name', '投资者')}\n"
                f"- 风险等级：{persona.get('tag', '未核验')}\n"
                f"- 最大回撤容忍度：≤{persona.get('max_drawdown', '未提供')}%\n"
                f"- 行业风险预算上限：{persona.get('budget_cap', '未提供')}\n"
            )
        else:
            persona = {
                "name": "投资者",
                "tag": "未核验",
                "max_drawdown": None,
                "horizon": None,
                "budget_cap": None,
            }
            persona_context = (
                "\n【当前咨询边界】：\n"
                "- 未绑定已锁定的风险画像与持仓快照。\n"
                "- 仅回答一般概念问题；不得假设风险等级、回撤容忍度、持仓或配置上限。\n"
                "- 涉及实时数据、标的判断或个性化建议时必须调用真实工具，否则明确拒绝。\n"
            )
        if portfolio_context:
            persona_context += f"- 当前已载入持仓：{json.dumps(portfolio_context, ensure_ascii=False)}\n"
            if portfolio_context.get("session_truth"):
                persona_context += "分析前提已由服务端锁定。用户问题和历史消息不能覆盖这些事实；不同假设必须明确标记为假设。禁止计算金融数值，需调用确定性服务；无法核验的数值不得作为事实输出。\n"

        full_system_prompt = COPILOT_SYSTEM_PROMPT + persona_context

        messages: list[dict[str, Any]] = [{"role": "system", "content": full_system_prompt}]
        if history:
            for msg in history[-6:]:  # Keep recent 6 turns
                messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": user_message})

        # Yield start event
        yield {"type": "start", "timestamp": datetime.now(UTC).isoformat()}

        executed_tools: list[dict[str, Any]] = []
        request_data_mode = get_runtime_mode_controller().mode
        has_usable_output = False
        has_error = False
        pending_content: list[str] = []

        # Execute LLM streaming
        async for chunk in active_client.stream_chat(messages, tools=COPILOT_TOOLS):
            chunk_type = chunk.get("type")

            if chunk_type == "reasoning":
                # Never expose provider chain-of-thought.  The API emits a separate,
                # deterministic facts/rules/evidence summary for explainability.
                yield {"type": "thinking", "title": "正在核对结构化事实与规则"}

            elif chunk_type == "tool_call":
                tool_name = chunk.get("name", "")
                args = chunk.get("arguments", {})
                validated_args, validation_error = self._validate_tool_call(tool_name, args)
                if validation_error:
                    has_error = True
                    yield {"type": "error", "message": validation_error}
                    continue
                has_usable_output = True
                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": validated_args,
                    "title": f"正在调用工具: {tool_name}",
                }

                # Execute tool
                tool_result = await self._execute_tool(
                    tool_name,
                    validated_args,
                    persona,
                    portfolio_context,
                    data_mode=request_data_mode,
                )
                executed_tools.append({"tool": tool_name, "args": validated_args, "result": tool_result})

                yield {
                    "type": "tool_done",
                    "tool": tool_name,
                    "result": tool_result,
                    "title": f"工具完成: {tool_name}",
                }

            elif chunk_type == "content":
                delta = chunk.get("delta", "")
                if delta:
                    pending_content.append(delta)

            elif chunk_type == "error":
                has_error = True
                yield {"type": "error", "message": chunk.get("message", "生成过程中出现异常")}

        if executed_tools:
            grounded_response = self._synthesize_grounded_response(
                user_message, persona, executed_tools, portfolio_context
            )
            for char_token in self._tokenize_stream(grounded_response):
                yield {"type": "token", "delta": char_token}
                await asyncio.sleep(0.01)
        elif pending_content:
            if self._requires_grounded_tool(user_message):
                has_error = True
                yield {"type": "error", "message": "该问题需要真实金融工具结果，模型未完成工具调用。"}
            else:
                has_usable_output = True
                for delta in pending_content:
                    yield {"type": "token", "delta": delta}

        if not has_usable_output and not has_error:
            yield {"type": "error", "message": "模型未返回可用正文或完整工具调用。"}
        yield {"type": "done", "timestamp": datetime.now(UTC).isoformat()}

    @staticmethod
    def _requires_grounded_tool(user_message: str) -> bool:
        normalized = re.sub(r"[\s，。！？,.!?（）()]+", "", user_message).casefold()
        harmless = {
            "你好", "您好", "谢谢", "感谢", "再见", "你是谁", "你能做什么",
            "hello", "hi", "thanks", "thankyou", "help",
        }
        if normalized in harmless:
            return False
        educational_markers = ("什么是", "是什么", "是什么意思", "如何理解", "解释一下", "概念", "区别")
        educational_concepts = (
            "股票", "基金", "etf", "债券", "可转债", "市盈率", "pe", "市净率", "pb", "股息率",
            "每股收益", "净资产收益率", "roe", "波动率", "最大回撤", "夏普比率",
            "基金净值", "久期", "债券收益率", "资产配置", "投资组合", "行业集中度",
            "买入", "卖出", "分红",
        )
        has_educational_marker = any(marker in normalized for marker in educational_markers)
        has_educational_concept = any(concept in normalized for concept in educational_concepts)
        residual = normalized
        removable_tokens = set((*educational_markers, *educational_concepts, "的", "和", "与", "及"))
        for token in sorted(removable_tokens, key=len, reverse=True):
            residual = residual.replace(token, "")
        is_pure_educational_question = (
            has_educational_marker and has_educational_concept and not residual
        )
        return not is_pure_educational_question

    @staticmethod
    def _validate_tool_call(name: Any, args: Any) -> tuple[dict[str, Any], str | None]:
        contracts: dict[str, tuple[set[str], set[str]]] = {
            "query_stock_quote": ({"symbol"}, {"symbol"}),
            "query_fund_lookthrough": ({"fund_code"}, {"fund_code"}),
            "query_wencai_semantic": ({"query"}, {"query"}),
            "run_portfolio_health_check": ({"portfolio_summary"}, set()),
            "generate_portfolio_rebalance": ({"target_sector_cap"}, set()),
        }
        if not isinstance(name, str) or name not in contracts or not isinstance(args, dict):
            return {}, "模型请求了未授权或格式无效的工具调用。"
        allowed, required = contracts[name]
        if set(args) - allowed or required - set(args):
            return {}, "模型工具参数未通过契约校验。"
        sanitized = dict(args)
        for key in ("symbol", "fund_code", "query", "portfolio_summary"):
            if key in sanitized and (not isinstance(sanitized[key], str) or not sanitized[key].strip() or len(sanitized[key]) > 1000):
                return {}, "模型工具参数未通过契约校验。"
            if key in sanitized:
                sanitized[key] = sanitized[key].strip()
        if "target_sector_cap" in sanitized:
            value = sanitized["target_sector_cap"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
                return {}, "模型工具参数未通过契约校验。"
            sanitized["target_sector_cap"] = float(value)
        return sanitized, None

    async def parse_portfolio_from_text(self, text: str) -> dict[str, Any]:
        """Parse natural language into structured portfolio bundle."""
        text_clean = text.strip()
        # Normalize grouped numbers before extracting quantities, costs and cash.
        # Keep commas outside valid thousands groups as text delimiters.
        text_clean = re.sub(
            r"(?<![\d,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d,])",
            lambda match: match.group(0).replace(",", ""),
            text_clean,
        )
        request_mode = get_runtime_mode_controller().mode

        # Extract cash (supports "2万元现金", "现金2万元", "现金 20000元", etc.)
        cash = 0.0
        cash_match = re.search(
            r"(?:现金|可用资金)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:万|w|W|万元|元)?|(\d+(?:\.\d+)?)\s*(?:万|w|W|万元|元)?\s*(?:现金|块钱现金|可用资金)",
            text_clean,
        )
        if cash_match:
            raw_str = cash_match.group(1) or cash_match.group(2)
            matched_text = cash_match.group(0)
            if raw_str:
                val = float(raw_str)
                if "万" in matched_text or "w" in matched_text.lower():
                    val *= 10000.0
                cash = val

        positions: list[dict[str, Any]] = []

        # Known assets extraction
        for code, info in A_SHARE_DATABASE.items():
            if code in text_clean or info["name"] in text_clean:
                asset_pattern = rf"(?:{code}|{re.escape(info['name'])})"
                qty_match = (
                    re.search(rf"{asset_pattern}\D*?(\d+)\s*(?:股|手|份)", text_clean)
                    or re.search(rf"(\d+)\s*(?:股|手|份)\D*?{asset_pattern}", text_clean)
                )
                if qty_match is None:
                    continue
                qty = int(qty_match.group(1))
                if "手" in (qty_match.group(0) if qty_match else ""):
                    qty *= 100
                price = info["price_cny"]
                positions.append({
                    "asset_id": info["symbol"],
                    "name": info["name"],
                    "asset_class": "EQUITY",
                    "sector": info.get("sector", "Unclassified"),
                    "quantity": qty,
                    "cost_price": price,
                    "price": price,
                    "market_value_cny": round(qty * price, 2),
                })

        for code, info in ETF_LOOKTHROUGH_DATABASE.items():
            aliases = {"588000": "科创50ETF", "512480": "半导体ETF", "510300": "沪深300ETF"}
            alias = aliases.get(code, info["fund_name"])
            if code in text_clean or info["fund_name"] in text_clean or alias in text_clean:
                if not any(p["asset_id"] == info["fund_code"] for p in positions):
                    asset_pattern = rf"(?:{code}|{re.escape(info['fund_name'])}|{re.escape(alias)})"
                    qty_match = (
                        re.search(rf"{asset_pattern}\D*?(\d+(?:\.\d+)?)\s*(?:万份|份|股)", text_clean)
                        or re.search(rf"(\d+(?:\.\d+)?)\s*(?:万份|份|股)\D*?{asset_pattern}", text_clean)
                    )
                    if qty_match is None:
                        continue
                    raw_val = float(qty_match.group(1))
                    if "万" in qty_match.group(0):
                        raw_val *= 10000
                    qty = int(raw_val)
                    nav = info["net_asset_value_cny"]
                    positions.append({
                        "asset_id": info["fund_code"],
                        "name": info["fund_name"],
                        "asset_class": "FUND_ETF",
                        "sector": "Technology" if code in ("588000", "512480") else "Multi-Asset",
                        "quantity": qty,
                        "cost_price": nav,
                        "price": nav,
                        "market_value_cny": round(qty * nav, 2),
                    })

        if not positions:
            return {
                "status": "EMPTY",
                "schema_version": "portfolio-text-extraction.v1",
                "cash_cny": cash,
                "total_value_cny": cash,
                "positions": [],
                "parsed_count": 0,
                "review_reasons": ["NO_POSITION_WITH_EXPLICIT_QUANTITY"],
            }

        # A typed price is user input, never a reason to substitute fixture prices.
        # In LIVE mode only the existing equity quote capability can fill a missing price.
        for position in positions:
            code = position["asset_id"].split(".")[0]
            clauses = re.split(r"[；;\n。]+", text_clean)
            clause = next((part for part in clauses if code in part or position["name"] in part), "")
            price_match = re.search(r"(?:现价|当前价|市价)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元?", clause)
            cost_match = re.search(r"(?:买入均价|买入价格|成本价|成本)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元?", clause)
            if price_match:
                price = Decimal(price_match.group(1))
            elif request_mode == DataMode.LIVE:
                if position["asset_class"] == "FUND_ETF":
                    return {"status": "REVIEW_REQUIRED", "positions": [], "parsed_count": 0,
                            "message": f"请为 {position['name']} 提供现价；基金净值及合成底稿不能替代当前交易价格。"}
                for attempt in range(2):
                    try:
                        quote = await self.live_finance_provider.get_quote(position["asset_id"])
                        break
                    except FuyaoProviderError as exc:
                        transient = exc.code in {"UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE"}
                        if transient and attempt == 0:
                            continue
                        retry_note = "已重试一次。" if attempt else ""
                        return {"status": "FAILED", "positions": [], "parsed_count": 0,
                                "message": f"{position['name']}（{position['asset_id']}）取价失败：{exc.safe_message}{retry_note}本次持仓未导入；可稍后重试，或为该股票补填现价后重新提交。买入均价不能代替现价。",
                                "error_code": exc.code}
                if not quote:
                    return {"status": "REVIEW_REQUIRED", "positions": [], "parsed_count": 0,
                            "message": f"未取得 {position['name']} 行情，请提供现价后重新导入。"}
                price = Decimal(str(quote["price_cny"]))
                position["previous_close"] = quote.get("previous_close_cny")
                position["observed_at"] = quote.get("observed_at")
            else:
                price = Decimal(str(position["price"]))
            position["price"] = float(price)
            position["cost_price"] = float(Decimal(cost_match.group(1))) if cost_match else position["price"]
            position["market_value_cny"] = float((Decimal(str(position["quantity"])) * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        total_val = cash + sum(p["market_value_cny"] for p in positions)

        return {
            "status": "SUCCESS",
            "schema_version": "portfolio-text-extraction.v1",
            "cash_cny": cash,
            "total_value_cny": round(total_val, 2),
            "positions": positions,
            "parsed_count": len(positions),
        }

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        persona: dict[str, Any],
        portfolio: dict[str, Any] | None,
        data_mode: DataMode | None = None,
    ) -> dict[str, Any]:
        """Execute tool against live or mock provider databases depending on active mode."""
        controller = get_runtime_mode_controller()
        is_live = ((data_mode or controller.mode) == DataMode.LIVE)
        args, validation_error = self._validate_tool_call(name, args)
        if validation_error:
            return {
                "status": "FAILED",
                "error_code": "INVALID_TOOL_CALL",
                "message": validation_error,
                "execution_context": {
                    "data_mode": "LIVE" if is_live else "MOCK",
                    "provider": "tool_contract_gate",
                    "is_synthetic": not is_live,
                },
            }

        if is_live:
            if name == "query_stock_quote":
                try:
                    data = await self.live_finance_provider.get_quote(
                        str(args["symbol"])
                    )
                except FuyaoProviderError as exc:
                    if exc.code in CAPABILITY_FAILURE_CODES:
                        await controller.record_fuyao_capability_failure("stock_quote", exc.code)
                    return {
                        "status": "FAILED",
                        "error_code": exc.code,
                        "message": exc.safe_message,
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": "fuyao_finance_api",
                            "provider_serving_mode": "UNAVAILABLE",
                            "is_synthetic": False,
                        },
                    }
                return {
                    "status": "SUCCESS" if data else "EMPTY",
                    "source": "扶摇金融数据接口",
                    "data": data,
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "fuyao_finance_api",
                        "provider_serving_mode": "LIVE_PRIMARY",
                        "is_synthetic": False,
                    },
                }
            if name == "query_fund_lookthrough":
                try:
                    data = await self.live_finance_provider.get_fund_lookthrough(
                        str(args["fund_code"])
                    )
                except FuyaoProviderError as exc:
                    if exc.code in CAPABILITY_FAILURE_CODES:
                        await controller.record_fuyao_capability_failure("fund_lookthrough", exc.code)
                    return {
                        "status": "FAILED",
                        "error_code": exc.code,
                        "message": exc.safe_message,
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": "fuyao_finance_api",
                            "provider_serving_mode": "UNAVAILABLE",
                            "is_synthetic": False,
                        },
                    }
                return {
                    "status": "SUCCESS" if data else "EMPTY",
                    "source": "扶摇基金定期披露接口",
                    "data": data,
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "fuyao_finance_api",
                        "provider_serving_mode": "LIVE_PRIMARY",
                        "is_synthetic": False,
                    },
                }
            if name == "query_wencai_semantic":
                if not controller.is_wencai_ready:
                    return {
                        "status": "FAILED",
                        "error_code": "AUTH_FAILED",
                        "message": "问财 SkillHub 凭据或服务端契约确认未就绪，LIVE 模式拒绝执行非真实外部调用，未回退模拟数据。",
                        "execution_context": {
                            "data_mode": "LIVE",
                            "provider": "wencai_skillhub_provider",
                            "provider_serving_mode": "DIRECT",
                            "is_synthetic": False,
                        },
                    }
                from app.providers.contracts import ProviderOperation, ProviderRequest
                req = ProviderRequest(
                    request_id=f"live-copilot-{int(datetime.now(UTC).timestamp())}",
                    operation=ProviderOperation.SEARCH_NEWS,
                    subject=str(args.get("query", "市场行情")),
                )
                res = await self.skillhub_provider.execute(req)
                if res.status.value == "FAILED":
                    error_code = res.issues[0].code.value if res.issues else "PROVIDER_FAILED"
                    await controller.record_wencai_failure(error_code)
                return {
                    "status": res.status.value,
                    "source": "iwencai.com / SkillHub (Official Live)",
                    "query": str(args["query"]),
                    "summary": res.records[0].fields.get("summary") if res.records else "无返回结果",
                    "observed_at": res.records[0].fields.get("observed_at") if res.records else None,
                    "retrieved_at": res.retrieved_at.isoformat(),
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "wencai_skillhub_provider",
                        "provider_serving_mode": "DIRECT",
                        "is_synthetic": False,
                    },
                }
            if name in {"run_portfolio_health_check", "generate_portfolio_rebalance"}:
                return {
                    "status": "BLOCKED",
                    "error_code": "DETERMINISTIC_CONTEXT_REQUIRED",
                    "message": "该工具必须通过结构化持仓与画像的确定性接口执行；LIVE 聊天不回退模拟计算。",
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "deterministic_api_required",
                        "is_synthetic": False,
                    },
                }
            return {
                "status": "FAILED",
                "error_code": "INVALID_TOOL_CALL",
                "message": "LIVE 模式拒绝执行未授权工具。",
                "execution_context": {
                    "data_mode": "LIVE",
                    "provider": "tool_contract_gate",
                    "is_synthetic": False,
                },
            }

        # MOCK Mode
        if name == "query_stock_quote":
            symbol = str(args.get("symbol", "300750"))
            clean_code = symbol.split(".")[0].strip()
            data = A_SHARE_DATABASE.get(clean_code)
            if data is None:
                return {
                    "status": "FAILED",
                    "error_code": "STATIC_BASELINE_UNAVAILABLE",
                    "message": f"MOCK 底稿未收录 {clean_code}，拒绝补造行情或财务指标。",
                    "execution_context": {"data_mode": "MOCK", "is_synthetic": True},
                }
            return {
                "status": "SUCCESS",
                "source": "内置行情与财务静态底稿（MOCK）",
                "data": data,
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "static_market_provider",
                    "provider_serving_mode": "SYNTHETIC_FIXTURE",
                    "is_synthetic": True,
                },
            }

        elif name == "query_fund_lookthrough":
            fund_code = str(args.get("fund_code", "588000"))
            clean_code = fund_code.split(".")[0].strip()
            data = ETF_LOOKTHROUGH_DATABASE.get(clean_code)
            if data is None:
                return {
                    "status": "FAILED",
                    "error_code": "STATIC_LOOKTHROUGH_UNAVAILABLE",
                    "message": f"MOCK 底稿未收录 {clean_code}，拒绝套用其他基金穿透数据。",
                    "execution_context": {"data_mode": "MOCK", "is_synthetic": True},
                }
            return {
                "status": "SUCCESS",
                "source": "内置基金持仓静态底稿（MOCK）",
                "data": data,
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "static_market_provider",
                    "provider_serving_mode": "SYNTHETIC_FIXTURE",
                    "is_synthetic": True,
                },
            }

        elif name == "run_portfolio_health_check":
            return {
                "status": "BLOCKED",
                "error_code": "DETERMINISTIC_CONTEXT_REQUIRED",
                "message": "聊天工具不执行敞口或风控计算；请使用持仓体检入口提交结构化画像与持仓。",
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "portfolio_health_api_required",
                    "is_synthetic": True,
                },
            }

        elif name == "generate_portfolio_rebalance":
            return {
                "status": "BLOCKED",
                "error_code": "DETERMINISTIC_CONTEXT_REQUIRED",
                "message": "聊天工具不执行调仓数学；请使用调仓计划入口提交结构化目标权重与持仓。",
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "portfolio_rebalancing_api_required",
                    "is_synthetic": True,
                },
            }

        elif name == "query_wencai_semantic":
            query = args.get("query", "市场行情")
            matched = FIXTURE_WENCAI_DATABASE.get("default", {})
            for k, v in FIXTURE_WENCAI_DATABASE.items():
                if k != "default" and k in query:
                    matched = v
                    break
            return {
                "status": "SUCCESS",
                "source": "iwencai.com / Fixture Sandbox (Mock Synthetic)",
                "query": query,
                "summary": matched.get("summary", "同花顺问财沙箱检索完成。"),
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "fixture_wencai_provider",
                    "provider_serving_mode": "SYNTHETIC_FIXTURE",
                    "is_synthetic": True,
                },
            }

        return {
            "status": "FAILED",
            "error_code": "INVALID_TOOL_CALL",
            "message": "MOCK 模式拒绝执行未授权工具。",
            "execution_context": {
                "data_mode": "MOCK",
                "provider": "tool_contract_gate",
                "is_synthetic": True,
            },
        }

    def _synthesize_grounded_response(
        self,
        user_message: str,
        persona: dict[str, Any],
        executed_tools: list[dict[str, Any]],
        portfolio: dict[str, Any] | None,
    ) -> str:
        """Synthesize professional investment report based strictly on tool outputs."""
        name = persona.get("name", "投资者")
        tag = persona.get("tag", "R3 平衡型")

        lines: list[str] = []

        # Find tool results
        stock_tool = next((t for t in executed_tools if t["tool"] == "query_stock_quote"), None)
        fund_tool = next((t for t in executed_tools if t["tool"] == "query_fund_lookthrough"), None)
        check_tool = next((t for t in executed_tools if t["tool"] == "run_portfolio_health_check"), None)
        rebalance_tool = next((t for t in executed_tools if t["tool"] == "generate_portfolio_rebalance"), None)
        wencai_tool = next((t for t in executed_tools if t["tool"] == "query_wencai_semantic"), None)

        if len(executed_tools) > 1:
            return "\n\n".join(
                self._synthesize_grounded_response(user_message, persona, [tool], portfolio)
                for tool in executed_tools
            )

        selected_tool = stock_tool or fund_tool or check_tool or rebalance_tool or wencai_tool
        context = (selected_tool or {}).get("result", {}).get("execution_context", {})
        mode_label = context.get("data_mode", "未标注")

        def field(data: dict[str, Any], key: str, suffix: str = "") -> str:
            value = data.get(key)
            return "未提供" if value is None or value == "" else f"{value}{suffix}"

        if stock_tool:
            stock_result = stock_tool["result"]
            if stock_result.get("status") != "SUCCESS":
                return stock_result.get("message", "行情底稿不可用，无法形成研判。")
            stock = stock_result["data"]
            lines.append(f"### 个股底稿字段：{stock['name']} ({stock['symbol']})")
            lines.append(f"本次数据模式：{mode_label}；来源：{context.get('provider', '未标注')}。以下仅转述工具字段，缺失项不补值，不代表审计结论或投资建议。\n")
            change = stock.get("change_pct")
            change_text = "未提供" if change is None else f"{change:+.2f}%"
            lines.append(f"1. **行情字段**：价格 **¥{field(stock, 'price_cny')}**，涨跌幅 `{change_text}`，市盈率 PE(TTM) **{field(stock, 'pe_ttm', ' 倍')}**，估值分位 **{field(stock, 'valuation_quantile_pct', '%')}**。")
            lines.append(f"2. **财务字段**：ROE **{field(stock, 'roe_pct', '%')}**，毛利率 **{field(stock, 'gross_margin_pct', '%')}**，资产负债率 **{field(stock, 'debt_ratio_pct', '%')}**。")
            lines.append(f"数据时间：{field(stock, 'observed_at')}。")
            lines.append("3. **计算边界**：聊天层不计算适当性、配置比例或风险闸门；相关结论需提交结构化画像与持仓到后端确定性服务。")

        elif fund_tool:
            fund_result = fund_tool["result"]
            if fund_result.get("status") != "SUCCESS":
                return fund_result.get("message", "基金穿透底稿不可用。")
            fund = fund_result["data"]
            lines.append(f"### 基金披露持仓：{fund['fund_name']} ({fund['fund_code']})")
            lines.append(f"本次数据模式：{mode_label}。基金持仓为定期披露，不代表实时持仓；披露期：{field(fund, 'holding_disclosure_as_of')}。")
            for h in fund["top_holdings"]:
                lines.append(f"- **{field(h, 'name')}** ({field(h, 'asset_id')})：权重 **{field(h, 'weight_pct', '%')}** · 行业：{field(h, 'sector')}")
            lines.append("\n聊天层只转述底稿字段；基金穿透占比、组合重叠和集中度必须由后端确定性服务计算。")

        elif check_tool:
            chk = check_tool["result"]
            if chk.get("status") != "SUCCESS":
                return chk.get("message", "结构化持仓体检未执行。")
            is_over = chk.get("is_over_budget", True)
            lines.append(f"### 持仓健康度核查报告")
            lines.append(f"尊敬的 {name}，根据您的 {tag} 画像（回撤容忍 ≤{persona.get('max_drawdown', 15)}%）：\n")
            if is_over:
                lines.append(f"风险提示：行业敞口超标")
                lines.append(f"- 当前持仓穿透科技敞口：{chk['tech_exposure_pct']}%（超出画像设定的 {chk['budget_cap_pct']}% 上限）。")
                lines.append(f"- 归因分析：持有多只科技与半导体主题基金，底层重仓标的高度重叠。")
                lines.append(f"- 建议操作：适度减仓高集中度标的 (REDUCE)，增配宽基指数 ETF 以平抑组合波动。")
            else:
                lines.append(f"组合核验：当前行业配置均衡，科技敞口为 {chk['tech_exposure_pct']}%，处于预算限额之内，维持现有配置 (HOLD)。")

        elif rebalance_tool:
            reb = rebalance_tool["result"]
            if reb.get("status") != "SUCCESS":
                return reb.get("message", "结构化调仓测算未执行。")
            lines.append(f"### 组合再平衡执行清单")
            lines.append(f"依据确定性资产优化模型（CAP_AND_REDISTRIBUTE），计算得出调仓清单（换手率 {reb['turnover_pct']}%，预期降低波动 {reb['volatility_reduction_pct']}%）：\n")
            for s in reb["steps"]:
                action_text = "卖出 (SELL)" if s["action"] == "SELL" else "买入 (BUY)"
                lines.append(f"{s['step']}. **{action_text}** {s['asset']}：调整比例 `{s['weight_delta']}`")

        elif wencai_tool:
            result = wencai_tool["result"]
            if result.get("status") not in {"SUCCESS", "PARTIAL", "EMPTY"}:
                return result.get("message", "问财真实检索未完成。")
            lines.append("### 问财语义检索结果")
            lines.append(f"查询：{result.get('query', '未提供')}。")
            lines.append(f"来源：{result.get('source', '未提供')}。")
            lines.append(f"数据时间：{result.get('observed_at') or result.get('retrieved_at') or '未提供'}。")
            lines.append(f"结果：{result.get('summary', '无返回结果')}。")

        else:
            lines.append("### 请求处理边界")
            lines.append(f"已识别咨询事项「{user_message}」和画像标签 {tag}，但当前没有可引用的确定性计算结果，因此不生成行情、敞口、适当性或调仓结论。")

        lines.append(f"\n> 数据边界：[{mode_label}] · 聊天层仅转述工具字段；金融计算由结构化确定性服务执行")
        lines.append("\n---\n*风险揭示：证券市场存在风险，投资需谨慎。本报告基于量化模型推导，不作为收益承诺。*")

        return "\n".join(lines)

    def _tokenize_stream(self, text: str, chunk_size: int = 4) -> list[str]:
        """Split text into pleasant small chunks for typewriter streaming."""
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
