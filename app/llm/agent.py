"""Copilot ReAct Agent core that coordinates tools, live providers, and streaming output."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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

        persona = persona_info or {
            "name": "张先生",
            "tag": "R3 平衡型",
            "max_drawdown": 15,
            "horizon": "MEDIUM",
            "budget_cap": "30.0%",
        }

        # Build persona-conditioned system prompt
        persona_context = (
            f"\n【当前咨询用户画像】：\n"
            f"- 姓名：{persona.get('name', '投资者')}\n"
            f"- 风险等级：{persona.get('tag', 'R3 平衡型')}\n"
            f"- 最大回撤容忍度：≤{persona.get('max_drawdown', 15)}%\n"
            f"- 行业风险预算上限：{persona.get('budget_cap', '30.0%')}\n"
        )
        if portfolio_context:
            persona_context += f"- 当前已载入持仓：{json.dumps(portfolio_context, ensure_ascii=False)}\n"

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
                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": args,
                    "title": f"正在调用工具: {tool_name}",
                }

                # Execute tool
                tool_result = await self._execute_tool(
                    tool_name,
                    args,
                    persona,
                    portfolio_context,
                    data_mode=request_data_mode,
                )
                executed_tools.append({"tool": tool_name, "args": args, "result": tool_result})

                yield {
                    "type": "tool_done",
                    "tool": tool_name,
                    "result": tool_result,
                    "title": f"工具完成: {tool_name}",
                }

                # Stream out grounded final response
                grounded_response = self._synthesize_grounded_response(
                    user_message, persona, executed_tools, portfolio_context
                )
                for char_token in self._tokenize_stream(grounded_response):
                    yield {"type": "token", "delta": char_token}
                    await asyncio.sleep(0.01)

            elif chunk_type == "content":
                yield {"type": "token", "delta": chunk.get("delta", "")}

            elif chunk_type == "error":
                yield {"type": "error", "message": chunk.get("message", "生成过程中出现异常")}

        yield {"type": "done", "timestamp": datetime.now(UTC).isoformat()}

    async def parse_portfolio_from_text(self, text: str) -> dict[str, Any]:
        """Parse natural language into structured portfolio bundle."""
        text_clean = text.strip()

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
                    "sector": info["sector"],
                    "quantity": qty,
                    "cost_price": price,
                    "price": price,
                    "market_value_cny": round(qty * price, 2),
                })

        for code, info in ETF_LOOKTHROUGH_DATABASE.items():
            if code in text_clean or info["fund_name"] in text_clean or ("科创" in text_clean and code == "588000") or ("半导体" in text_clean and code == "512480") or ("300" in text_clean and code == "510300"):
                if not any(p["asset_id"] == info["fund_code"] for p in positions):
                    asset_pattern = rf"(?:{code}|{re.escape(info['fund_name'])}|科创|半导体|300)"
                    qty_match = (
                        re.search(rf"{asset_pattern}\D*?(\d+)\s*(?:万份|万元|份|股)", text_clean)
                        or re.search(rf"(\d+)\s*(?:万份|万元|份|股)\D*?{asset_pattern}", text_clean)
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

        if is_live:
            if name == "query_stock_quote":
                try:
                    data = await self.live_finance_provider.get_quote(
                        str(args.get("symbol", "300750"))
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
                        str(args.get("fund_code", "510300"))
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
            elif name == "query_wencai_semantic":
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
                    "summary": res.records[0].fields.get("summary") if res.records else "无返回结果",
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "wencai_skillhub_provider",
                        "provider_serving_mode": "DIRECT",
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

        else:  # query_wencai_semantic
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

        if stock_tool:
            stock_result = stock_tool["result"]
            if stock_result.get("status") != "SUCCESS":
                return stock_result.get("message", "行情底稿不可用，无法形成研判。")
            stock = stock_result["data"]
            lines.append(f"### 个股底稿字段：{stock['name']} ({stock['symbol']})")
            lines.append("当前返回来自 MOCK 静态底稿。以下数值仅转述工具结果，不代表实时行情、审计结论或投资建议：\n")
            lines.append(f"1. **行情字段**：价格 **¥{stock['price_cny']}**，涨跌幅 `{stock['change_pct']:+.2f}%`，市盈率 PE(TTM) **{stock['pe_ttm']} 倍**，底稿估值分位 **{stock.get('valuation_quantile_pct', '未提供')}%**。")
            lines.append(f"2. **财务字段**：ROE **{stock['roe_pct']}%**，毛利率 **{stock['gross_margin_pct']}%**，资产负债率 **{stock['debt_ratio_pct']}%**。")
            lines.append("3. **计算边界**：聊天层不计算适当性、配置比例或风险闸门；相关结论需提交结构化画像与持仓到后端确定性服务。")

        elif fund_tool:
            fund_result = fund_tool["result"]
            if fund_result.get("status") != "SUCCESS":
                return fund_result.get("message", "基金穿透底稿不可用。")
            fund = fund_result["data"]
            lines.append(f"### 基金静态底稿：{fund['fund_name']} ({fund['fund_code']})")
            lines.append("当前 MOCK 底稿列出的重仓项包括：")
            for h in fund["top_holdings"]:
                lines.append(f"- **{h['name']}** ({h['asset_id']})：权重 **{h['weight_pct']}%** · 行业：{h['sector']}")
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

        else:
            lines.append("### 请求处理边界")
            lines.append(f"已识别咨询事项「{user_message}」和画像标签 {tag}，但当前没有可引用的确定性计算结果，因此不生成行情、敞口、适当性或调仓结论。")

        controller = get_runtime_mode_controller()
        mode_label = "LIVE · 官方接口数据" if controller.mode == DataMode.LIVE else "MOCK · 基准合成数据"
        lines.append(f"\n> 数据边界：[{mode_label}] · 聊天层仅转述工具字段；金融计算由结构化确定性服务执行")
        lines.append("\n---\n*风险揭示：证券市场存在风险，投资需谨慎。本报告基于量化模型推导，不作为收益承诺。*")

        return "\n".join(lines)

    def _tokenize_stream(self, text: str, chunk_size: int = 4) -> list[str]:
        """Split text into pleasant small chunks for typewriter streaming."""
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
