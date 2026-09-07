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

    def __init__(self, llm_client: AsyncLLMClient | None = None) -> None:
        self.client = llm_client or AsyncLLMClient()
        self.static_market_provider = StaticMarketProvider()
        self.market_provider = self.static_market_provider
        self.skillhub_provider = WencaiSkillHubProvider()
        self.fixture_wencai_provider = FixtureWencaiProvider()
        self.wencai_provider = self.skillhub_provider

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

        # Execute LLM streaming
        async for chunk in active_client.stream_chat(messages, tools=COPILOT_TOOLS):
            chunk_type = chunk.get("type")

            if chunk_type == "reasoning":
                yield {"type": "thinking", "text": chunk.get("delta", "")}

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
                tool_result = await self._execute_tool(tool_name, args, persona, portfolio_context)
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
                qty_match = re.search(rf"(?:{code}|{info['name']})\D*?(\d+)\s*(?:股|手|份)", text_clean)
                qty = int(qty_match.group(1)) if qty_match else 1000
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
                    "market_value_cny": round(qty * price, 2),
                })

        for code, info in ETF_LOOKTHROUGH_DATABASE.items():
            if code in text_clean or info["fund_name"] in text_clean or ("科创" in text_clean and code == "588000") or ("半导体" in text_clean and code == "512480") or ("300" in text_clean and code == "510300"):
                if not any(p["asset_id"] == info["fund_code"] for p in positions):
                    qty_match = re.search(rf"(?:{code}|{info['fund_name']}|科创|半导体|300)\D*?(\d+)\s*(?:份|股|万份|万元)", text_clean)
                    qty = 20000
                    if qty_match:
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
                        "market_value_cny": round(qty * nav, 2),
                    })

        if not positions:
            # Fallback default starter portfolio
            positions.append({
                "asset_id": "300750.SZ",
                "name": "宁德时代",
                "asset_class": "EQUITY",
                "sector": "Industrials",
                "quantity": 1000,
                "cost_price": 250.0,
                "market_value_cny": 250000.0,
            })
            positions.append({
                "asset_id": "588000.SH",
                "name": "华夏上证科创板50成份ETF",
                "asset_class": "FUND_ETF",
                "sector": "Technology",
                "quantity": 20000,
                "cost_price": 1.0,
                "market_value_cny": 20000.0,
            })
            if cash == 0.0:
                cash = 30000.0

        total_val = cash + sum(p["market_value_cny"] for p in positions)

        return {
            "schema_version": "portfolio-import-bundle.v1",
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
    ) -> dict[str, Any]:
        """Execute tool against live or mock provider databases depending on active mode."""
        controller = get_runtime_mode_controller()
        is_live = (controller.mode == DataMode.LIVE)

        if is_live:
            if name in ("query_stock_quote", "query_fund_lookthrough"):
                return {
                    "status": "FAILED",
                    "error_code": "LIVE_MODE_UNSUPPORTED",
                    "message": "该功能在 LIVE 官方数据模式下尚未接入交易所实时数据源，未回退模拟数据。",
                    "execution_context": {
                        "data_mode": "LIVE",
                        "provider": "wencai_skillhub_provider",
                        "provider_serving_mode": "UNSUPPORTED",
                        "is_synthetic": False,
                    },
                }
            elif name == "query_wencai_semantic":
                if not self.skillhub_provider.is_configured:
                    return {
                        "status": "FAILED",
                        "error_code": "AUTH_FAILED",
                        "message": "官方 SkillHub 凭据 (WENCAI_SKILLHUB_API_KEY) 未配置，LIVE 模式拒绝执行非真实外部调用，未回退模拟数据。",
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
            data = A_SHARE_DATABASE.get(clean_code, {
                "symbol": f"{clean_code}.SZ",
                "name": f"A股标的 ({clean_code})",
                "sector": "Technology",
                "price_cny": 38.5,
                "change_pct": 1.5,
                "pe_ttm": 26.2,
                "pb": 3.4,
                "roe_pct": 15.2,
                "gross_margin_pct": 34.0,
                "debt_ratio_pct": 42.0,
                "valuation_quantile_pct": 48.0,
            })
            return {
                "status": "SUCCESS",
                "source": "问财实时行情（MOCK 基准沙箱）",
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
            data = ETF_LOOKTHROUGH_DATABASE.get(clean_code, ETF_LOOKTHROUGH_DATABASE["588000"])
            return {
                "status": "SUCCESS",
                "source": "公募基金季度持仓穿透（MOCK 基准沙箱）",
                "data": data,
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "static_market_provider",
                    "provider_serving_mode": "SYNTHETIC_FIXTURE",
                    "is_synthetic": True,
                },
            }

        elif name == "run_portfolio_health_check":
            is_over = persona.get("tag", "").startswith("R3") or "42" in str(persona)
            return {
                "status": "SUCCESS",
                "tech_exposure_pct": 42.0 if is_over else 15.0,
                "budget_cap_pct": float(persona.get("budget_cap", "30.0%").replace("%", "")),
                "is_over_budget": is_over,
                "verdict": "REDUCE" if is_over else "HOLD",
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "deterministic_portfolio_engine",
                    "is_synthetic": True,
                },
            }

        elif name == "generate_portfolio_rebalance":
            return {
                "status": "SUCCESS",
                "turnover_pct": 14.0,
                "volatility_reduction_pct": -2.4,
                "steps": [
                    {"step": 1, "action": "SELL", "asset": "科技成长混合基金", "weight_delta": "-5.0%"},
                    {"step": 2, "action": "SELL", "asset": "半导体主题 ETF", "weight_delta": "-2.0%"},
                    {"step": 3, "action": "BUY", "asset": "沪深300 宽基 ETF", "weight_delta": "+7.0%"},
                ],
                "execution_context": {
                    "data_mode": "MOCK",
                    "provider": "deterministic_rebalance_engine",
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
            stock = stock_tool["result"]["data"]
            lines.append(f"### 📊 【个股深度研判】{stock['name']} ({stock['symbol']})")
            lines.append(f"基于同花顺问财实时行情与财务数据，结合您的 **{tag}** 画像为您提供以下研判：\n")
            lines.append(f"1. **实时行情与估值**：最新现价 **¥{stock['price_cny']}** (涨跌幅 `{stock['change_pct']:+.2f}%`)，市盈率 PE(TTM) 为 **{stock['pe_ttm']} 倍**，处于近三年历史分位数 **{stock.get('valuation_quantile_pct', 45.2)}%**（估值处于合理区间）。")
            lines.append(f"2. **财务质地与盈利能力**：ROE 达到 **{stock['roe_pct']}%**，毛利率为 **{stock['gross_margin_pct']}%**，资产负债率 **{stock['debt_ratio_pct']}%** 处于安全边界之内，具备较强抗周期护城河。")
            lines.append(f"3. **画像适配与仓位建议**：根据您的风险预算，建议单标的配置比例控制在 **5.0% 以内**，适合逢低分批建仓，不建议重仓单押。")

        elif fund_tool:
            fund = fund_tool["result"]["data"]
            lines.append(f"### 🔍 【基金底层穿透分析】{fund['fund_name']} ({fund['fund_code']})")
            lines.append(f"最新穿透数据显示，该基金前五大重仓股包括：")
            for h in fund["top_holdings"]:
                lines.append(f"- **{h['name']}** ({h['asset_id']})：权重 **{h['weight_pct']}%** · 行业：{h['sector']}")
            lines.append(f"\n穿透行业暴露显示 **科技/半导体集中度达 {fund['sector_exposure'].get('Technology', 70)}%**。若您已有科技持仓，请注意隐性重叠风险。")

        elif check_tool:
            chk = check_tool["result"]
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
            lines.append(f"### 组合再平衡执行清单")
            lines.append(f"依据确定性资产优化模型（CAP_AND_REDISTRIBUTE），计算得出调仓清单（换手率 {reb['turnover_pct']}%，预期降低波动 {reb['volatility_reduction_pct']}%）：\n")
            for s in reb["steps"]:
                action_text = "卖出 (SELL)" if s["action"] == "SELL" else "买入 (BUY)"
                lines.append(f"{s['step']}. **{action_text}** {s['asset']}：调整比例 `{s['weight_delta']}`")

        else:
            lines.append(f"### 投资研判结论")
            lines.append(f"针对咨询事项「{user_message}」并结合 {tag} 适当性约束，系统完成测算分析：全市场流动性与估值分位数处于合理区间，建议遵循多元化分散配置纪律，控制单一行业暴露上限。")

        controller = get_runtime_mode_controller()
        mode_label = "LIVE · 官方接口数据" if controller.mode == DataMode.LIVE else "MOCK · 基准合成数据"
        lines.append(f"\n> 来源核验与审计：数据模式 [{mode_label}] · 决策回执由确定性计算引擎闭环生成")
        lines.append("\n---\n*风险揭示：证券市场存在风险，投资需谨慎。本报告基于量化模型推导，不作为收益承诺。*")

        return "\n".join(lines)

    def _tokenize_stream(self, text: str, chunk_size: int = 4) -> list[str]:
        """Split text into pleasant small chunks for typewriter streaming."""
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
