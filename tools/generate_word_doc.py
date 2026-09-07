"""
Generate formal engineering report Word document with embedded screenshots.
Strictly formal tone: no emojis, no colloquialisms, concise technical titles.
"""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

DOCS_DIR = Path("/Users/b./prism/docs/showcase")
OUTPUT_PATH = DOCS_DIR / "Prism_前后端版本迭代与成果展示.docx"

def set_cell_background(cell, fill_hex):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=120, bottom=120, left=160, right=160):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_cell_border(cell, **kwargs):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        if border_name in kwargs:
            b_info = kwargs[border_name]
            node = OxmlElement(f'w:{border_name}')
            for key, val in b_info.items():
                node.set(qn(f'w:{key}'), str(val))
            tcBorders.append(node)
        else:
            node = OxmlElement(f'w:{border_name}')
            node.set(qn('w:val'), 'none')
            tcBorders.append(node)
    tcPr.append(tcBorders)

def add_callout(doc, text_list, title="功能说明", fill_hex="F8FAFC", border_color="2563EB"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, fill_hex)
    set_cell_margins(cell, top=120, bottom=120, left=180, right=160)
    
    set_cell_border(cell, 
                    left={'val': 'single', 'sz': '18', 'color': border_color},
                    top={'val': 'single', 'sz': '4', 'color': 'E2E8F0'},
                    bottom={'val': 'single', 'sz': '4', 'color': 'E2E8F0'},
                    right={'val': 'single', 'sz': '4', 'color': 'E2E8F0'})
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run_title = p.add_run(f"{title}\n")
    run_title.bold = True
    run_title.font.size = Pt(10)
    run_title.font.color.rgb = RGBColor(30, 58, 138)
    
    for i, line in enumerate(text_list):
        p_line = cell.add_paragraph() if i > 0 else p
        p_line.paragraph_format.space_before = Pt(1)
        p_line.paragraph_format.space_after = Pt(2)
        p_line.paragraph_format.line_spacing = 1.2
        run = p_line.add_run(line)
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(51, 65, 85)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_image_block(doc, image_name, caption_text, width_in=6.2):
    img_path = DOCS_DIR / image_name
    if not img_path.exists():
        p_err = doc.add_paragraph(f"[图片缺失: {image_name}]")
        p_err.runs[0].font.color.rgb = RGBColor(220, 38, 38)
        return
    
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(6)
    p_img.paragraph_format.space_after = Pt(3)
    p_img.add_run().add_picture(str(img_path), width=Inches(width_in))
    
    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_before = Pt(2)
    p_cap.paragraph_format.space_after = Pt(12)
    run_cap = p_cap.add_run(f"图：{caption_text}")
    run_cap.font.size = Pt(9)
    run_cap.font.color.rgb = RGBColor(100, 116, 139)

def main():
    doc = Document()
    
    # Page Margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
    
    # Normal Style
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Microsoft YaHei'
    style_normal.font.size = Pt(10.5)
    style_normal.font.color.rgb = RGBColor(30, 41, 59)
    
    # Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(8)
    p_title.paragraph_format.space_after = Pt(4)
    r_title = p_title.add_run("Prism 投顾智能体系统")
    r_title.bold = True
    r_title.font.size = Pt(20)
    r_title.font.color.rgb = RGBColor(15, 23, 42)
    
    # Subtitle
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(16)
    r_sub = p_sub.add_run("系统架构演进与功能展示报告")
    r_sub.font.size = Pt(12.5)
    r_sub.font.color.rgb = RGBColor(71, 85, 105)
    
    # Metadata summary table
    table_meta = doc.add_table(rows=2, cols=2)
    table_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r in range(2):
        for c in range(2):
            cell = table_meta.cell(r, c)
            set_cell_background(cell, "F8FAFC")
            set_cell_margins(cell, top=70, bottom=70, left=120, right=120)
            set_cell_border(cell, 
                            top={'val': 'single', 'sz': '4', 'color': 'E2E8F0'},
                            bottom={'val': 'single', 'sz': '4', 'color': 'E2E8F0'},
                            left={'val': 'single', 'sz': '4', 'color': 'E2E8F0'},
                            right={'val': 'single', 'sz': '4', 'color': 'E2E8F0'})
    
    table_meta.cell(0, 0).paragraphs[0].add_run("系统名称：Prism 证券投顾智能体系统").font.size = Pt(9.5)
    table_meta.cell(0, 1).paragraphs[0].add_run("数据底座：同花顺问财 SkillHub").font.size = Pt(9.5)
    table_meta.cell(1, 0).paragraphs[0].add_run("评测指标：事实幻觉率 0.00% | P50 延迟 4.39ms").font.size = Pt(9.5)
    table_meta.cell(1, 1).paragraphs[0].add_run("工程验证：472 项单元及集成测试全部通过").font.size = Pt(9.5)
    
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_after = Pt(12)
    
    # ==========================
    # 1. 系统架构与版本演进
    # ==========================
    h1_1 = doc.add_heading(level=1)
    h1_1.paragraph_format.space_before = Pt(12)
    h1_1.paragraph_format.space_after = Pt(6)
    r = h1_1.add_run("一、 系统架构与版本演进")
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(30, 58, 138)
    r.bold = True
    
    p = doc.add_paragraph("Prism 系统的研发经历了三个主要阶段，完成了从底层投研分析、金融工程模型到前端交互界面的分层构建：")
    p.paragraph_format.line_spacing = 1.25
    
    table_stages = doc.add_table(rows=4, cols=3)
    table_stages.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["阶段版本", "核心技术实现", "交付成果与定位"]
    widths = [Inches(1.2), Inches(3.3), Inches(2.0)]
    
    for c, text in enumerate(headers):
        cell = table_stages.cell(0, c)
        cell.width = widths[c]
        set_cell_background(cell, "1E3A8A")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p_c = cell.paragraphs[0]
        r_c = p_c.add_run(text)
        r_c.bold = True
        r_c.font.size = Pt(9.5)
        r_c.font.color.rgb = RGBColor(255, 255, 255)
    
    stages_data = [
        ("V1 阶段\n(基础投研)", "宏观、行业、标的与风险多维研究分析\n独立信源双向交叉验证\n结构化证据链追踪 (Evidence DAG)", "投研算法与证据底座\n保证决策依据的客观性与可审计性"),
        ("V2 阶段\n(模型构建)", "确定性情景压力测试模型\n换手率约束与调仓执行阶梯算法\n端到端指标回归自动化评测系统", "金融工程计算模型\n量化风险敞口，支持极端行情推演"),
        ("V3 阶段\n(交互系统)", "任务型卡片交互设计\n持仓底层穿透与重叠集中度分析\n自然语言持仓解析与三步执行指示器", "终端用户交互系统\n提供直观清晰的投资决策与执行辅助")
    ]
    
    for r_idx, (st, tech, val) in enumerate(stages_data, start=1):
        bg = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        row_cells = table_stages.rows[r_idx].cells
        for c_idx, content in enumerate([st, tech, val]):
            cell = row_cells[c_idx]
            cell.width = widths[c_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            set_cell_border(cell, 
                            top={'val': 'single', 'sz': '4', 'color': 'CBD5E1'},
                            bottom={'val': 'single', 'sz': '4', 'color': 'CBD5E1'},
                            left={'val': 'single', 'sz': '4', 'color': 'CBD5E1'},
                            right={'val': 'single', 'sz': '4', 'color': 'CBD5E1'})
            p_cell = cell.paragraphs[0]
            p_cell.paragraph_format.line_spacing = 1.15
            r_item = p_cell.add_run(content)
            r_item.font.size = Pt(9)
            if c_idx == 0:
                r_item.bold = True
                r_item.font.color.rgb = RGBColor(30, 58, 138)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(10)
    
    # ==========================
    # 2. 前端交互界面与功能实现
    # ==========================
    h1_2 = doc.add_heading(level=1)
    h1_2.paragraph_format.space_before = Pt(12)
    h1_2.paragraph_format.space_after = Pt(6)
    r = h1_2.add_run("二、 前端交互界面与功能实现")
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(30, 58, 138)
    r.bold = True
    
    # 2.1 Overview
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("2.1 投资工作台交互界面")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：面向投资者的核心操作台，采用卡片化布局，呈现资产边界与核心任务入口。",
        "技术实现：",
        "  • 投资边界展示：动态呈现账户风险等级（R3 平衡型）、总资产（50 万元）、科技板块敞口（28.0%）与风控上限（30.0%）。",
        "  • 引导式操作流：按照「边界确认 -> 穿透体检 -> 执行调仓」的三阶段时序推进。",
        "  • 任务模块划分：集成持仓健康体检、标的深度研判与智能调仓再平衡三大核心功能。"
    ], title="设计说明")
    
    add_image_block(doc, "01_v3_investor_workbench_overview.png", "投资工作台主界面布局与资产画像")
    
    # 2.2 Health Check
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("2.2 持仓穿透分析与集中度检测")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：对混合持仓进行底层穿透，检测跨基金重叠持股导致的隐性行业集中度风险。",
        "技术实现：",
        "  • 底层持仓穿透：解析持仓基金的前十大重仓股明细，加权计算实际股票暴露。",
        "  • 风险红线预警：结合用户 R3 画像设定的 30.0% 上限，对当前 28.0% 集中度提供明确警示与成因诊断。",
        "  • 依据可追溯：提供证据追溯入口，支持查验底层数据源与测算依据。"
    ], title="设计说明")
    
    add_image_block(doc, "02_v3_health_check_result.png", "持仓底层穿透与行业重叠度检测结果")
    
    # 2.3 Stock Research
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("2.3 标的基本面分析与画像匹配")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：基于结构化权威数据，提供多维财务指标与风险匹配分析，避免非受控生成。",
        "技术实现（以 300750 宁德时代为例）：",
        "  • 代码检索与联动：支持股票与 ETF 代码秒级检索，动态拉取基本面指标。",
        "  • 客观数据呈现：聚合历史估值分位、财务成长性、行业景气度及与当前持仓画像的适配性指标。",
        "  • 风险边界提示：客观标示行业波动特征与安全边际，提供辅助决策事实。"
    ], title="设计说明")
    
    add_image_block(doc, "03_v3_stock_deep_research.png", "标的基本面分析卡片（以 300750 宁德时代为例）")
    
    # 2.4 Rebalancing Stepper
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("2.4 组合再平衡与执行时序")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：将组合优化方案分解为符合交易规则的先后执行步骤，降低交易冲击与摩擦成本。",
        "技术实现：",
        "  • 换手率约束：设置死区阈值（Deadband），将换手率控制在 14.0%，避免频繁无效调仓。",
        "  • 交易执行时序：",
        "      - 第一步（卖出）：减持 001234 科技先锋混合（12.0% -> 6.0%），释放现金 30,000 元。",
        "      - 第二步（卖出）：减持 512480 半导体 ETF（10.0% -> 5.0%），释放现金 25,000 元。",
        "      - 第三步（买入）：增持 510300 沪深300 ETF（18.0% -> 29.0%），使用释放资金 55,000 元。",
        "  • 调仓效果评估：调仓后科技板块敞口降至 16.5%，符合风控安全区间。"
    ], title="设计说明")
    
    add_image_block(doc, "04_v3_rebalancing_plan_stepper.png", "再平衡方案执行时序界面（换手率 14%，先卖后买）")
    
    # 2.5 Modals
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("2.5 持仓输入与风险画像配置")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：提供非结构化持仓文本解析，并支持用户自定义关键风险承受阈值。",
        "技术实现：",
        "  • 自然语言实体解析：从非结构化文本中自动提取标的代码、名称、份额或比例信息。",
        "  • 画像参数配置：支持 R1~R5 风险偏好、最大容忍回撤及单一行业集中度限制的实时调整。"
    ], title="设计说明")
    
    add_image_block(doc, "05_v3_portfolio_input_modal.png", "自然语言持仓解析对话框", width_in=5.8)
    add_image_block(doc, "06_v3_user_profile_modal.png", "用户风险画像与约束配置对话框", width_in=5.8)
    
    # ==========================
    # 3. 金融工程模型与评测指标
    # ==========================
    h1_3 = doc.add_heading(level=1)
    h1_3.paragraph_format.space_before = Pt(12)
    h1_3.paragraph_format.space_after = Pt(6)
    r = h1_3.add_run("三、 金融工程模型与评测指标")
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(30, 58, 138)
    r.bold = True
    
    # 3.1 Explainability
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("3.1 因果归因与反事实分析")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：提供量化归因权重与假设推演，实现决策过程白盒化。",
        "技术实现：",
        "  • 权重归因计算：量化各因子对调仓决策的贡献比例——风险预算约束占 45%、用户画像约束占 35%、基本面因子占 20%。",
        "  • 反事实推演：计算若放宽集中度上限或调整风险等级时，系统再平衡策略的对应变化。"
    ], title="设计说明")
    
    add_image_block(doc, "07_v2_advanced_explainability_dag.png", "决策因果归因权重与反事实推演分析")
    
    # 3.2 Scenario Simulation
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("3.2 情景压力测试")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：通过确定性数学模型模拟系统性风险情景，评估组合抗风险韧性。",
        "技术实现：",
        "  • 压力情景测算：在「科技板块回调 15% + 市场流动性收紧」情景下，原组合预期跌幅为 -11.4%，调仓后组合预期跌幅收窄至 -6.1%。",
        "  • 指标对比：对比基准组合与优化组合的波动率、最大回撤与下行风险。"
    ], title="设计说明")
    
    add_image_block(doc, "08_v2_scenario_simulation_diff.png", "宏观压力情景下基准组合与优化组合对比模拟")
    
    # 3.3 Evaluation Dashboard
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("3.3 自动化评测指标与结果")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "功能定位：对算法输出的一致性、合规性与系统性能进行持续基准测试。",
        "评测结果：",
        "  • 事实幻觉率：0.00%，所有输出指标均严格绑定底层权威数据源。",
        "  • 响应时延：P50 延迟 4.39ms，P95 延迟 12.8ms，满足高频并发调用需求。",
        "  • 规则合规率：100.0%，投资组合约束与风控边界无一违规。"
    ], title="设计说明")
    
    add_image_block(doc, "09_v2_evaluation_dashboard_scorecard.png", "自动化评测指标与回归测试结果看板")
    
    # ==========================
    # 4. 后端接口与基础投研模块
    # ==========================
    h1_4 = doc.add_heading(level=1)
    h1_4.paragraph_format.space_before = Pt(12)
    h1_4.paragraph_format.space_after = Pt(6)
    r = h1_4.add_run("四、 后端接口与基础投研模块")
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(30, 58, 138)
    r.bold = True
    
    # 4.1 OpenAPI
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("4.1 RESTful API 接口设计")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "架构特征：基于 FastAPI 构建高内聚低耦合的微服务接口体系，提供完整的 OpenAPI 规范与数据校验。",
        "主要接口划分：",
        "  • /api/v1/health-check: 持仓底层穿透与集中度计算接口。",
        "  • /api/v1/rebalance: 考虑换手率与流动性约束的组合优化接口。",
        "  • /api/v1/scenario-simulation: 宏观与行业情景压力测试接口。",
        "  • /api/v1/explainability: 归因权重与反事实分析接口。",
        "  • /api/v1/eval: 事实一致性与评测审计接口。"
    ], title="设计说明")
    
    add_image_block(doc, "10_backend_api_architecture_swagger.png", "FastAPI OpenAPI (Swagger) 接口架构定义")
    
    # 4.2 Research Framework
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(8)
    h2.paragraph_format.space_after = Pt(3)
    r = h2.add_run("4.2 多维投研分析与证据追溯")
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(37, 99, 235)
    r.bold = True
    
    add_callout(doc, [
        "架构特征：构建覆盖宏观、行业、标的与风险的四维投研框架，所有结论建立在不可篡改的证据链条之上。",
        "技术实现：",
        "  • 证据链分层：遵循「分析结论 (Finding) -> 客观事实 (Fact) -> 数据凭证 (Evidence)」的三层追溯模型。",
        "  • 双源校验：核心财务与行情数据经由同花顺问财与研报多方校验后入库，确保数据输入可信。"
    ], title="设计说明")
    
    add_image_block(doc, "11_v1_developer_research_matrix.png", "多维投研分析与证据追溯架构")
    
    # Save document
    doc.save(str(OUTPUT_PATH))
    print(f"Successfully generated: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
