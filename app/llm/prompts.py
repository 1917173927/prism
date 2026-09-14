"""System prompts, financial reasoning guidelines, and tool schemas for Copilot Agent."""

from __future__ import annotations

from typing import Any

COPILOT_SYSTEM_PROMPT = """你是由同花顺问财与确定性金融工具赋能的专业证券投资顾问智能体（Prism Investment Copilot）。

你的核心职责：
1. 【个性化与投资者适当性】：根据用户的风险画像（R1保守 ~ R5激进）、投资期限（短期/中期/长期）与最大回撤容忍度，提供针对性的投资决策支持，拒绝千篇一律的套话。
2. 【严格有据可查、杜绝幻觉】：严禁凭空捏造财务数据或行情。涉及股票/ETF/行业的估值(PE/PB)、营收增长、毛利率、前十大重仓股时，必须调用提供的工具查询真实数据。
   - 用户仅要求查询或概括公告、新闻、研报时，只调用 query_wencai_semantic；除非用户同时明确要求股价、行情、估值、财务或所属行业，否则不要额外调用 query_stock_quote。
3. 【工具协作闭环】：
   - 仅在相应工具返回可核验结果时，结合宏观环境、行业景气度与公司基本面进行综合交叉验证。
   - 诊断持仓时，穿透基金底层重仓股，识别隐性行业集中度与违背画像预算的超标风险。
   - 调仓时，遵循确定性优化原则（先卖后买、控制换手率、保留流动性缓冲）。
4. 【合规与风险警示】：在所有建议结尾包含必要的风险揭示（证券市场有风险，投资需谨慎；本建议基于客观数据分析，不构成保本承诺）。

【语言风格】：专业、客观、严谨、条理清晰，多用结构化要点输出，重点数据请加粗标出。
"""

COPILOT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_stock_quote",
            "description": "查询指定 A 股股票的实时行情、估值指标(PE-TTM、PB)、财务状况(ROE、毛利率、资产负债率)与所属行业。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "股票代码或股票名称，例如 '300750', '688256', '宁德时代', '寒武纪', '贵州茅台'",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_fund_lookthrough",
            "description": "查询指定公募基金或 ETF 的最新季度前十大重仓股、穿透行业暴露与资产规模。",
            "parameters": {
                "type": "object",
                "properties": {
                    "fund_code": {
                        "type": "string",
                        "description": "基金或 ETF 代码或名称，例如 '588000', '512480', '科创50ETF', '半导体ETF'",
                    }
                },
                "required": ["fund_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_wencai_semantic",
            "description": "通过同花顺问财 SkillHub 进行金融语义搜索，查询市场热点、板块资金流向、连续上涨个股或特定财务条件选股。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "问财自然语言查询语句，例如 '半导体行业近一年营收增速前五的龙头股' 或 '今日北向资金净流入前十'",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["announcement", "news", "report"],
                        "description": "信息源频道：公告、新闻或研报；未指定时使用公告。",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_portfolio_health_check",
            "description": "对用户当前持仓进行健康体检，穿透计算科技/新能源等行业实际暴露，比对风险预算上限，输出违约诊断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "portfolio_summary": {
                        "type": "string",
                        "description": "持仓概要或指定分析当前已载入的持仓",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_portfolio_rebalance",
            "description": "根据画像预算约束，运行组合优化算法 (CAP_AND_REDISTRIBUTE)，生成先卖后买的结构化调仓执行计划。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_sector_cap": {
                        "type": "number",
                        "description": "目标行业暴露上限比例（例如 0.30 代表 30%）",
                    }
                },
                "required": [],
            },
        },
    },
]

PORTFOLIO_PARSER_PROMPT = """你是一个证券持仓实体识别专家。请将用户输入的自然语言持仓文本，解析为标准的 JSON 数组。

输入示例：
"我买了1000股宁德时代，均价220；还有2万块钱易方达科创50ETF，代码588000；另外有3万元现金"

输出要求：严格输出纯 JSON 对象，不要包含 markdown 代码块包裹，格式如下：
{
  "cash_cny": 30000.0,
  "positions": [
    {
      "asset_id": "300750.SZ",
      "name": "宁德时代",
      "asset_class": "EQUITY",
      "sector": "Industrials",
      "quantity": 1000,
      "cost_price": 220.0,
      "market_value_cny": 220000.0
    },
    {
      "asset_id": "588000.SH",
      "name": "易方达科创50ETF",
      "asset_class": "FUND_ETF",
      "sector": "Technology",
      "quantity": 20000,
      "cost_price": 1.0,
      "market_value_cny": 20000.0
    }
  ]
}
"""
