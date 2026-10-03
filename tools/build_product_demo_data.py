"""Freeze synthetic product examples using deterministic Python calculations.

The demo never reads user data, secrets, financial Providers or model services.
Only this build step performs financial arithmetic; the browser formats a snapshot.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

import numpy as np

from app.service.research_algorithms import (
    CovarianceInput, RegimeInput, ReturnPoint,
    constant_correlation_shrinkage, regime_probabilities,
)

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app/api/static/demos/product-demo/data.js"
AS_OF = datetime(2026, 9, 30, 16, tzinfo=timezone(timedelta(hours=8)))
D = Decimal


def money(value):
    return f"{D(str(value)).quantize(D('.01'), rounding=ROUND_HALF_UP):,.2f}"


def pct(value, signed=False):
    value = D(str(value)).quantize(D('.01'), rounding=ROUND_HALF_UP)
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


def weekdays(count):
    days, current = [], AS_OF.date()
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return list(reversed(days))


def build():
    raw = [
        ("300750.SZ", "宁德时代", 1400, "280.50", "265.00", "277.10", "新能源"),
        ("600519.SH", "贵州茅台", 100, "1580.00", "1460.00", "1568.20", "消费"),
        ("601398.SH", "工商银行", 15000, "7.20", "6.40", "7.18", "金融"),
        ("510300.SH", "沪深300 ETF", 40000, "4.25", "3.98", "4.22", "宽基 ETF"),
        ("510880.SH", "红利 ETF", 50000, "3.20", "3.05", "3.21", "红利 ETF"),
    ]
    cash = D("125000")
    total = cash + sum(D(q) * D(price) for _, _, q, price, _, _, _ in raw)
    previous = cash + sum(D(q) * D(price) for _, _, q, _, _, price, _ in raw)
    holdings, allocation = [], []
    colors = ["#e86f00", "#eea666", "#7c9fa0", "#7185aa", "#b0b4be", "#d8dce3"]
    for index, (code, name, quantity, price, cost, _, sector) in enumerate(raw):
        value = D(quantity) * D(price)
        weight = value / total * 100
        gain = (D(price) / D(cost) - 1) * 100
        holdings.append(dict(code=code, name=name, quantity=f"{quantity:,}", price_cny=money(price),
            market_value_cny=money(value), weight_pct=pct(weight), return_pct=pct(gain, True),
            sector=sector, tone="up" if gain >= 0 else "down"))
        allocation.append(dict(name=name, value=float(weight), label=pct(weight), color=colors[index]))
    allocation.append(dict(name="现金", value=float(cash / total * 100), label=pct(cash / total * 100), color=colors[-1]))
    largest = max(D(q) * D(price) / total * 100 for _, _, q, price, _, _, _ in raw)
    portfolio = dict(total_cny=money(total), day_pnl_cny=money(total - previous),
        day_return_pct=pct((total / previous - 1) * 100, True), cash_cny=money(cash), cash_pct=pct(cash / total * 100),
        holding_count=str(len(raw)), largest_weight_pct=pct(largest), risk_level="C3 · 平衡型",
        risk_status="OVERBOUND" if largest > 30 else "PASS", position_limit_pct="30.00%")
    dates = weekdays(320)
    rng = np.random.default_rng(14)
    innovations = rng.normal(0.0003, np.where((np.arange(320) // 55) % 2, .017, .004))
    history = np.cumprod(1 + innovations)
    trend = [{"time": day.isoformat(), "value": round(float(history[index] / history[-1] * float(total)), 2)}
             for index, day in enumerate(dates)][-100:]
    portfolio["period"] = f"{trend[0]['time']} 至 {trend[-1]['time']}"
    instruments = {}
    for index, (key, name, code, final) in enumerate([
        ("shanghai", "上证指数", "000001.SH", 3842.19),
        ("shenzhen", "深证成指", "399001.SZ", 12887.62),
        ("csi300", "沪深300", "000300.SH", 4357.62),
        ("growth", "创业板指", "399006.SZ", 3135.28),
    ]):
        generator = np.random.default_rng(28 + index)
        returns = generator.normal(.00045, .007, 100)
        close = np.cumprod(1 + returns)
        close = close / close[-1] * final
        bars, volumes = [], []
        for i, day in enumerate(dates[-100:]):
            opening = float(close[i - 1] if i else close[i] * .995)
            closing = float(close[i])
            span = float(generator.uniform(.003, .014))
            bars.append(dict(time=day.isoformat(), open=round(opening, 2), close=round(closing, 2),
                high=round(max(opening, closing) * (1 + span), 2), low=round(min(opening, closing) * (1 - span), 2)))
            volumes.append(dict(time=day.isoformat(), value=int(generator.integers(150000000, 380000000)),
                color="#d04f46" if closing >= opening else "#23856a"))
        monthly = {}
        for bar in bars:
            month = bar["time"][:7]
            if month not in monthly:
                monthly[month] = dict(bar)
            else:
                monthly[month].update(close=bar["close"], high=max(monthly[month]["high"], bar["high"]),
                                      low=min(monthly[month]["low"], bar["low"]))
        change = (D(str(close[-1])) / D(str(close[-2])) - 1) * 100
        instruments[key] = dict(name=name, code=code, candles=bars, monthly=list(monthly.values()), volume=volumes,
            value=money(final), change_pct=pct(change, True), tone="up" if change >= 0 else "down")
        close = np.array([point["close"] for point in bars])
        instruments[key]["metrics"] = [
            dict(label="当日涨跌", value=pct((close[-1] / close[-2] - 1) * 100, True).removesuffix("%"), unit="%", note="与前一交易日收盘价相比"),
            dict(label="近 20 日涨跌", value=pct((close[-1] / close[-21] - 1) * 100, True).removesuffix("%"), unit="%", note="固定 20 个交易日窗口"),
            dict(label="年化波动率", value=pct(np.std(np.diff(np.log(close[-21:])), ddof=1) * np.sqrt(252) * 100).removesuffix("%"), unit="%", note="按近 20 日收益波动估算，不代表未来涨跌"),
            dict(label="距阶段高点回撤", value=pct((close[-1] / close.max() - 1) * 100).removesuffix("%"), unit="%", note="相对近 100 个交易日最高收盘价"),
        ]
    metrics = instruments["shanghai"]["metrics"]
    points = [ReturnPoint(time=day, value=float(value)) for day, value in zip(dates, innovations)]
    regime = regime_probabilities(RegimeInput(source="DEMO_SYNTHETIC_SEED_14", as_of=AS_OF, returns=points))
    common = rng.normal(0, .008, 100)
    covariance = constant_correlation_shrinkage(CovarianceInput(source="DEMO_SYNTHETIC_SEED_14", as_of=AS_OF,
        series={name: [ReturnPoint(time=day, value=float(value)) for day, value in zip(dates[-100:], common * beta + rng.normal(0, .006, 100))]
                for name, beta in [("样本 A", .9), ("样本 B", 1.1), ("样本 C", .6)]}))
    assert abs(sum(a["value"] for a in allocation) - 100) < 1e-8
    assert trend[-1]["value"] == float(total)
    data = dict(meta=dict(label="演示数据", as_of="2026-09-30", snapshot_id="prism-product-demo.v1",
        source="固定合成演示快照", synthetic=True, notice="页面仅用于产品演示，行情、持仓、来源及任务状态均为演示样例。",
        arithmetic="Python Decimal / NumPy / existing deterministic research algorithms", remote_calls=0),
        portfolio=portfolio, holdings=holdings, allocation=allocation, trend=trend,
        market=dict(period=portfolio["period"], coverage="6 / 6 个合成板块 · 固定观察集", quotes=[dict(id=key, **{name: item[name] for name in ["name", "code", "value", "change_pct", "tone"]}) for key, item in instruments.items()],
            instruments=instruments, metrics=metrics, sectors=[dict(name=name, return_pct=value, tone=tone, coverage="固定 6 板块观察集")
                for name, value, tone in [("新能源", "+2.18%", "up"), ("金融", "+0.84%", "up"), ("消费", "+0.62%", "up"),
                                          ("医药", "-0.31%", "down"), ("半导体", "-0.57%", "down"), ("传媒", "-1.06%", "down")]]),
        profile=dict(level="C3 · 平衡型", score="58 / 100", name="稳健研究型", experience="3 至 5 年", horizon="3 年以上", version="第 3 版",
            dimensions=[dict(label=label, value=value) for label, value in [("风险承受", 58), ("投资经验", 68), ("操作活跃", 42),
                ("研究习惯", 76), ("信息投入", 64), ("AI 信任", 56), ("个性化需求", 72), ("辅助需求", 62)]]),
        trading=dict(metrics=[dict(label=label, value=value, note=note) for label, value, note in [
            ("平均持有周期", "46 天", "固定行为样例"), ("月均交易次数", "6 次", "演示观察期"), ("计划内交易", "83.3%", "人工标记样例"), ("交易记录", "24 条", "演示记录集")]],
            records=[dict(date=d, name=n, side=s, quantity=q, price=p, pnl=result) for d, n, s, q, p, result in [
                ("2026-09-28", "沪深300 ETF", "买入", "2,000", "4.18", "—"), ("2026-09-23", "宁德时代", "卖出", "200", "278.60", "演示记录"),
                ("2026-09-18", "工商银行", "买入", "1,000", "7.12", "—"), ("2026-09-11", "红利 ETF", "买入", "3,000", "3.16", "—")]],
            style=[dict(label=l, value=v, note=n) for l, v, n in [("长期配置", 72, "持有周期较长"), ("计划执行", 83, "偏向规则驱动"), ("研究投入", 76, "定期阅读与复盘")]]),
        skills=[dict(id=key, name=name, description=description, category=category, version="1.2.0", selected=index < 6,
            status="VERIFIED", source="演示工具") for index, (key, name, description, category) in enumerate([
            ("quote", "行情查询", "读取标的行情、时点与来源。", "市场数据"), ("financial", "财务分析", "整理财报字段与公告时点。", "公司研究"),
            ("industry", "行业观察", "比较固定观察集的板块表现。", "市场数据"), ("announcement", "公告检索", "定位公告原文与版本。", "公司研究"),
            ("fund", "基金穿透", "查看基金披露的持仓与资料覆盖范围。", "组合研究"), ("risk", "组合风险", "检查持仓集中度与风险匹配情况。", "组合研究"),
            ("research", "资料研究", "查找研究资料与相关原文。", "研究资料"), ("factor", "风格分析", "观察公司规模、盈利和投资等特征的表现。", "组合研究"),
            ("citation", "引用核验", "核对分析结论是否有原文依据。", "研究资料")])],
        documents=[dict(id=key, title=title, type=kind, subject=subject, period="2026 年三季度", published_at="2026-09-30",
            source="产品演示文档", excerpt=excerpt, keywords=keywords, availability="DEMO") for key, title, kind, subject, excerpt, keywords in [
            ("doc-market", "宏观与市场观察（演示摘要）", "研究摘要", "A 股市场", "该演示片段说明市场收益与风险应结合固定观察区间，不以单日涨跌解释长期趋势。", ["市场", "宏观", "波动", "风险"]),
            ("doc-company", "新能源公司研究（演示摘要）", "公司研究", "宁德时代", "该演示片段展示如何将公司公告、财务字段和报告期关联；没有资料支持的增长预测应保留未验证状态。", ["宁德", "新能源", "公司", "财务"]),
            ("doc-portfolio", "组合集中度说明（演示资料）", "方法说明", "示例组合", "单项持仓权重超过演示参考阈值时，先展示独立风险提示，再讨论配置约束与可用资料。", ["组合", "集中度", "持仓", "配置"]),
            ("doc-method", "协方差收缩研究笔记（演示资料）", "方法说明", "组合研究", "本演示使用合成收益序列展示常相关目标收缩；它不证明真实资产的相关性或未来风险。", ["协方差", "收缩", "相关", "算法"])]],
        live=dict(version="demo.workflow.v1", steps=[dict(id=key, title=title, detail=detail, duration_ms=duration) for key, title, detail, duration in [
            ("scope", "确认研究范围", "固定样例标的、报告期及截止时点", 350), ("data", "读取演示资料", "加载本地已冻结快照，无上游调用", 650),
            ("metrics", "检查资产与风险指标", "使用预先计算的演示结果", 500), ("evidence", "关联资料片段", "保留缺少资料和待核对的事项", 450),
            ("report", "生成演示报告", "汇总预设示例，无模型服务调用", 350)]],
            result=[dict(label="研究方式", value="本地演示", note="展示预设步骤与结果"), dict(label="资料来源", value="演示样例", note="未连接实时数据服务"),
                    dict(label="未完成项", value="财务时点核验", note="保留缺口，不给出收益预测")]),
        algorithms=dict(regime=dict(status=regime["status"], reason=regime.get("reason"), method=regime["method_version"], training_samples="252",
                series=[dict(time=row["time"], value=row["low_variance"]) for row in regime.get("series", [])],
                display_series=[dict(time=row["time"], value=row["high_variance"] * 100) for row in regime.get("series", [])],
                environment=("高波动状态更可能" if regime["series"][-1]["high_variance"] >= .5 else "低波动状态更可能") if regime.get("series") else "暂无法判断波动状态",
                interpretation="概率描述演示收益序列的波动状态，不是上涨或下跌的概率，也不能用于判断当前持仓的涨跌。" if regime.get("series") else "输入收益序列尚未满足分析条件，暂不判断波动状态。",
                low_probability=pct(regime["series"][-1]["low_variance"] * 100) if regime.get("series") else "不可计算",
                high_probability=pct(regime["series"][-1]["high_variance"] * 100) if regime.get("series") else "不可计算"),
            covariance=dict(status=covariance["status"], reason=covariance.get("reason"), labels=covariance.get("assets", []), matrix=covariance.get("covariance", []),
                interpretation="结果描述三个示例资产的收益联动。它们与账户持仓不同，不能据此判断当前组合的分散效果。" if covariance["status"] == "CALCULATED" else "示例资产的数据尚未满足分析条件，暂不判断资产联动。",
                matrix_display=[[f"{value:.8f}" for value in row] for row in covariance.get("covariance", [])],
                shrinkage=f"{covariance['shrinkage']:.4f}" if covariance["status"] == "CALCULATED" and covariance.get("shrinkage") is not None else "不可计算",
                samples=str(covariance.get("sample_count", "未提供")), unit="小数收益率的平方"),
            factors=dict(status="UNAVAILABLE", missing=["历史资产名单与复权收益", "当时已公开的财报及发布时间", "分组资产的市值与收益", "同期无风险收益数据"])),
        copilot=dict(presets=[dict(id=key, query=query, title=title, text=text, claims=claims, document_ids=ids) for key, query, title, text, claims, ids in [
            ("portfolio", "我的组合有哪些需要关注的风险？", "先核对集中度，再讨论配置", "固定演示快照中，最大单项权重超过参考阈值。请先核对资金用途、风险承受能力与持仓来源。该页面展示预设研究说明，不生成真实交易建议。", ["持仓和资金来自固定演示快照。", "风险检查独立于文字解释。", "本演示不执行交易。"], ["doc-portfolio", "doc-market"]),
            ("company", "研究宁德时代的资料与风险", "从资料与公告时点开始研究", "演示资料提供行业与公司研究的呈现方式。缺少真实公告和财务输入时，保留未验证状态，不推断未来利润或价格。", ["资料为产品演示文档。", "不将预设片段标为真实财报证据。"], ["doc-company"]),
            ("market", "如何理解市场波动与回撤？", "分别查看波动与回撤的观察窗口", "波动率描述一段时间内收益的变化程度，回撤描述价格从阶段高点回落的幅度。两者应结合各自的观察期阅读，不能用于预测下一日涨跌。这里的结果来自演示日线。", ["波动率按最近20个交易日计算。", "回撤按最近100个交易日的最高收盘价计算。"], ["doc-market", "doc-method"])]]))
    return data


if __name__ == "__main__":
    snapshot = build()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("/* Synthetic product snapshot. Regenerate with python -m tools.build_product_demo_data. */\n"
        + "window.PRISM_DEMO_DATA = " + json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + ";\n", encoding="utf-8")
    print(f"Frozen synthetic snapshot: {TARGET.relative_to(ROOT)}; no remote calls")
