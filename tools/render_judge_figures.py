from pathlib import Path
from io import StringIO
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/submission/figures"
QA = ROOT / "output/report-review"
FONT = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
BOLD = FontProperties(fname="C:/Windows/Fonts/msyhbd.ttc")
INK = "#202124"
MUTED = "#717780"
ORANGE = "#e86f00"
matplotlib.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})

# 每个分区表示同一处理阶段，跨分区箭头表示阶段之间的信息传递。
FIGURES = [
    ("judge-01-processing-flow", "3-1", "从投资问题到分析结果", "个人条件、研究依据与金融计算共同参与分析", [
        ("确认输入", "明确本次分析采用的个人条件", [
            ("投资问题", "自然语言表达\n识别分析目的", False),
            ("投资者画像", "问卷评分与提案确认\n保存有效画像版本", True),
            ("持仓资料", "导入并核对资产\n确认组合快照", False)]),
        ("并行分析", "研究与计算提供不同类型的依据", [
            ("专业研究", "市场、行业与证券\n查询所需资料", False),
            ("证据校验", "来源、期间与质量\n形成研究发现", True),
            ("组合计算", "暴露与风险预算\n输出组合报告", True)]),
        ("审查与输出", "完整建议需要通过风险与合规审查", [
            ("独立双闸门", "风险条件与引用披露\n分别检查", True),
            ("建议资格", "通过 / 复核 / 阻断\n保留具体原因", False),
            ("用户结果", "报告、建议与回执\n工作台展示与回看", False)])]),
    ("judge-02-architecture", "5-1", "系统总体架构", "模型理解、金融计算与建议审查具有明确职责", [
        ("交互与任务", "以确认后的用户上下文组织分析", [
            ("工作台", "对话、问卷、持仓\n用户确认输入", False),
            ("任务协调", "意图识别与研究计划\n按依赖调度任务", True),
            ("用户上下文", "画像与持仓版本\n用户归属检查", False)]),
        ("研究与计算", "数据服务支撑两类专业处理", [
            ("数据服务", "问财 SkillHub 等来源\n时间、单位与状态", False),
            ("专业研究", "市场、行业与证券\n研究发现与证据引用", True),
            ("金融程序", "Decimal 确定性计算\n暴露、配置与调整", True)]),
        ("验证与交付", "结果展示与历史记录共同保留分析依据", [
            ("证据验证", "来源独立性与冲突\n检查引用关系", False),
            ("风险与合规", "独立规则审查\n判定建议资格", True),
            ("报告与记录", "组合报告、建议回执\n证据版本与决策事件", False)])]),
    ("judge-03-profile-calculation", "5-2", "画像进入风险计算", "算法一 · 投资者画像驱动的风险约束映射", [
        ("形成画像", "正式评分与用户确认共同确定有效输入", [
            ("正式问卷", "五维加权评分\n风险等级映射", False),
            ("自然语言提案", "保留原文依据\n确认字段差异", False),
            ("已确认画像", "风险等级与版本\n作为计算条件", True)]),
        ("比较风险", "个人阈值与当前组合采用统一口径", [
            ("风险预算", "按风险等级选择\n资产与行业上限", True),
            ("组合暴露", "确认持仓与成分\n计算占比和集中度", False),
            ("逐项比较", "观察值与适用阈值\n计算超限幅度", True)]),
        ("应用结果", "个性化条件能够改变风险判断", [
            ("超限定位", "具体资产或行业\n观察值、上限与差额", False),
            ("配置与复核", "形成配置范围\n进入方案及审查", True),
            ("版本追踪", "关联画像与组合\n支持历史复核", False)])]),
    ("judge-04-evidence-validation", "5-3", "证据支持研究结论", "算法二 · 来源关联约束的证据交叉验证", [
        ("统一口径", "只有可比较的观测进入来源分组", [
            ("Evidence", "来源记录与质量状态\n保留原始依据", False),
            ("声明匹配", "主体、指标、单位\n期间与质量检查", True),
            ("来源分组", "依据 lineage_id\n同源记录仅计一次", True)]),
        ("独立验证", "根据独立支持、反对与歧义判定状态", [
            ("来源检查", "同组数值冲突复核\n缺少关联不计独立支持", False),
            ("状态判定", "支持 / 反对\n冲突 / 数量不足", True),
            ("Fact", "满足验证条件的事实\n保留证据引用", False)]),
        ("进入建议", "已验证事实通过引用关系支持建议", [
            ("Finding", "形成研究发现\n引用已验证事实", False),
            ("双重审查", "风险与合规检查\n完整建议生成条件", True),
            ("Recommendation", "建议与决策回执\n逐层追踪分析依据", False)])]),
    ("judge-05-rebalancing", "5-4", "目标权重转化为交易数量", "算法三 · 交易单位与现金约束下的再平衡计算", [
        ("确定目标", "持仓、画像与报价共同定义计算输入", [
            ("确认组合", "持仓与有效报价\n现金及资产总值", False),
            ("风险约束", "暴露、集中度与预算\n形成配置范围", True),
            ("目标金额", "目标权重与当前权重\n计算金额变化", False)]),
        ("计算数量", "每项行动同时考虑交易单位与资金条件", [
            ("数量取整", "按报价与交易单位\n卖出受持仓数量限制", False),
            ("卖出测算", "计算数量和费用\n更新可用现金", True),
            ("买入测算", "预留现金并计入费用\n二分查找可负担数量", True)]),
        ("检查结果", "按实际测算数量复核调整后的组合", [
            ("资金汇总", "金额、费用与现金\n计算实际换手率", False),
            ("交易后复核", "现金、风险与画像条件\n保留超限和缺项", True),
            ("方案输出", "先卖出后买入步骤\n数量及复核说明", False)])]),
    ("judge-06-decision-gates", "5-5", "专业协作与双重审查", "研究执行状态与独立规则共同决定建议资格", [
        ("研究执行", "依赖条件决定节点何时执行", [
            ("研究计划", "依赖关系与必需字段\n节点及整体时间预算", False),
            ("专业节点", "符合条件的任务并行\n返回结果及引用", True),
            ("结果汇集", "保存超时、取消与缺项\n验证研究证据", False)]),
        ("独立检查", "研究发现与组合计算结果进入两个闸门", [
            ("风险闸门", "画像、组合、预算\n证据与配置一致性", True),
            ("合规闸门", "引用、披露与归属\n禁止表述检查", True),
            ("资格聚合", "汇集两个审查结果\n建议组合器再次校验", False)]),
        ("决策结果", "每种状态均保留决策事件", [
            ("PASS", "双重通过\n生成建议与回执", True),
            ("REVIEW_REQUIRED", "暂缓建议组合\n返回缺项与复核原因", False),
            ("BLOCKED", "终止建议组合\n保留阻断原因", False)])]),
]


def render(spec):
    name, number, title, subtitle, stages = spec
    fig, ax = plt.subplots(figsize=(8.2, 8.5))
    fig.subplots_adjust(0, 0, 1, 1)
    ax.set(xlim=(0, 100), ylim=(0, 104))
    ax.axis("off")
    texts = []

    def text(x, y, value, size=9, color=INK, bold=False, ha="left", va="center"):
        item = ax.text(x, y, value, fontsize=size, color=color, ha=ha, va=va,
                       fontproperties=BOLD if bold else FONT, linespacing=1.7)
        texts.append(item)
        return item

    text(6, 99, "PRISM", 10, ORANGE, True)
    text(94, 99, f"技术文档 / 图 {number}", 8, MUTED, ha="right")
    text(6, 92.5, title, 20, bold=True)
    text(6, 87, subtitle, 9, MUTED)
    ax.plot([6, 94], [82, 82], color="#dedfe2", lw=0.8)
    ax.plot([6, 18], [82, 82], color=ORANGE, lw=2)
    boxes = []
    card_texts = []
    for row, (label, description, nodes) in enumerate(stages):
        top = 77 - row * 25
        text(6, top, f"0{row + 1}", 12, ORANGE, True)
        text(12, top, label, 12, bold=True)
        text(94, top, description, 7.6, MUTED, ha="right")
        y = top - 19
        for col, (heading, detail, accent) in enumerate(nodes):
            x, w, h = 6 + col * 31, 26, 14.5
            patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.6",
                                  facecolor="#fff4e8" if accent else "#fafafa",
                                  edgecolor="#f1c89e" if accent else "#dedfe2", linewidth=0.8)
            ax.add_patch(patch)
            ax.plot([x + 0.8, x + 0.8], [y + 2, y + h - 2], color=ORANGE if accent else "#717780", lw=2)
            heading_item = text(x + w / 2, y + 10.5, heading, 9.3 if len(heading) < 15 else 8, bold=True, ha="center")
            detail_item = text(x + w / 2, y + 5, detail, 8, "#4f5660", ha="center")
            card_texts.append((patch, heading_item, detail_item))
            boxes.append((x, y, w, h))
        if row < 2:
            # 连线仅表示阶段衔接，同一行的模块可以具有并列关系。
            arrow = FancyArrowPatch((50, y - 0.4), (50, y - 4.2), arrowstyle="-|>",
                                    mutation_scale=10, color=ORANGE, linewidth=1.1)
            ax.add_patch(arrow)
    ax.plot([6, 94], [4.5, 4.5], color="#dedfe2", lw=0.6)
    text(6, 2, "灰色：输入与结果    橙色：核心处理", 7, MUTED)
    text(94, 2, "箭头表示阶段衔接，同行模块按说明协作", 7, MUTED, ha="right")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for item in texts:
        bounds = item.get_window_extent(renderer)
        assert fig.bbox.contains(bounds.x0, bounds.y0) and fig.bbox.contains(bounds.x1, bounds.y1), item.get_text()
    for patch, heading_item, detail_item in card_texts:
        card_bounds = patch.get_window_extent(renderer)
        for item in (heading_item, detail_item):
            bounds = item.get_window_extent(renderer)
            assert card_bounds.contains(bounds.x0, bounds.y0) and card_bounds.contains(bounds.x1, bounds.y1), item.get_text()
        assert not heading_item.get_window_extent(renderer).overlaps(detail_item.get_window_extent(renderer)), heading_item.get_text()
    for suffix in ("png", "svg", "pdf"):
        target = OUTPUT / f"{name}.{suffix}"
        if suffix == "svg":
            with StringIO() as buffer:
                fig.savefig(buffer, format="svg", facecolor="white")
                target.write_text("\n".join(line.rstrip() for line in buffer.getvalue().splitlines()) + "\n", encoding="utf-8")
        else:
            fig.savefig(target, dpi=300, facecolor="white")
    plt.close(fig)
    return {"figure": name, "nodes": len(boxes), "text_bounds": "PASS", "card_bounds": "PASS", "size_inches": [8.2, 8.5]}


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    results = [render(spec) for spec in FIGURES]
    (QA / "python-figure-validation.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
