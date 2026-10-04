import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

const runtimeModules = process.env.RUNTIME_NODE_MODULES;
const skillDir = process.env.PRESENTATION_SKILL_DIR;
assert.ok(runtimeModules && skillDir, 'Runtime and presentation skill paths are required');
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(runtimeModules, '@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const { chromium } = await import(pathToFileURL(path.join(runtimeModules, 'playwright/index.mjs')).href);
const root = process.cwd();
const buildDir = path.join(root, 'output/technical-presentation');
const deliveryDir = path.join(root, 'docs/submission/technical-presentation');
const figuresDir = path.join(deliveryDir, 'figures');
await fs.mkdir(buildDir, { recursive: true });
await fs.mkdir(figuresDir, { recursive: true });

const snapshot = JSON.parse(await fs.readFile('app/api/static/pages-snapshot.json', 'utf8'));
const portfolio = JSON.parse(snapshot.routes['GET /api/v1/advisor/portfolio/report'].body);
const execution = JSON.parse(await fs.readFile('docs/submission/test-evidence/research-quality-20261003/hybrid-execution.json', 'utf8'));
const macro = execution.records.find(record => record.question_id === 'real-001');
const bank = execution.records.find(record => record.question_id === 'real-017');
assert.ok(portfolio.generated_at && macro && bank);
const dataImages = [
  {
    name: '实际数据-组合报告', title: '组合报告响应字段', source: 'pages-snapshot.json · portfolio/report',
    time: portfolio.generated_at,
    data: { generated_at: portfolio.generated_at, data_mode: portfolio.data_mode, holdings_value_cny: portfolio.holdings_value_cny, cash_cny: portfolio.cash_cny, total_value_cny: portfolio.total_value_cny, position_count: portfolio.position_count, concentration: Object.fromEntries(['status', 'top_asset_name', 'top_asset_weight_pct', 'asset_hhi', 'single_asset_limit_pct'].map(key => [key, portfolio.concentration[key]])) },
    intro: '该图选取仓库保存的正式组合报告字段，展示报告时间、金额与集中度状态。报告生成于 2026 年 9 月 15 日，证券市值与现金共同构成总资产，集中度返回 REVIEW_REQUIRED。图片展示该时点的历史报告。',
  },
  {
    name: '实际数据-宏观资料检索', title: '宏观资料检索响应字段', source: 'hybrid-execution.json · real-001',
    time: execution.generated_at,
    data: { question_id: macro.question_id, status: macro.tool_result.status, mode: macro.tool_result.mode, fulltext_backend: macro.tool_result.fulltext_backend, rrf_constant: macro.tool_result.rrf_constant, match: Object.fromEntries(['text', 'source', 'published_at', 'period', 'status'].map(key => [key, macro.tool_result.matches[0][key]])) },
    intro: '该图来自实际研究文档检索记录 real-001，展示关键词和语义向量合并后的宏观资料响应。图片保留 RRF、FTS5、原文、来源与 RETRIEVED_UNVERIFIED，配套 JSON 保存查询时间条件及来源地址。',
  },
  {
    name: '实际数据-银行财报检索', title: '银行财报检索响应字段', source: 'hybrid-execution.json · real-017',
    time: execution.generated_at,
    data: { question_id: bank.question_id, status: bank.tool_result.status, mode: bank.tool_result.mode, match: Object.fromEntries(['text', 'source', 'published_at', 'period', 'status'].map(key => [key, bank.tool_result.matches[0][key]])) },
    intro: '该图来自实际研究文档检索记录 real-017，展示工商银行 2024 年报中的净利息收入与营业收入片段。金额单位沿用原文的 RMB millions，图片保留发布时间、期间和检索状态，配套 JSON 保存来源地址。',
  },
];
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1500, height: 1300 }, deviceScaleFactor: 2 });
  for (const asset of dataImages) {
    await page.setContent('<html lang="zh-CN"><style>body{margin:0;background:#f7f9fc;color:#19314d;font-family:Microsoft YaHei}main{width:1400px;padding:40px;box-sizing:border-box}h1{font-size:30px;margin:0 0 14px}p{font-size:21px;color:#546b84;margin:0 0 22px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;border-left:5px solid #326dc4;padding:28px;font:23px/1.45 Consolas,Microsoft YaHei;margin:0}</style><main><h1></h1><p></p><pre></pre></main></html>');
    await page.evaluate(({ title, source, time, data }) => {
      document.querySelector('h1').textContent = title;
      document.querySelector('p').textContent = `${source} · 记录时间 ${time}`;
      document.querySelector('pre').textContent = JSON.stringify(data, null, 2);
    }, asset);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('main').screenshot({ path: path.join(figuresDir, `${asset.name}.png`) });
    const record = asset.name.includes('宏观') ? macro : asset.name.includes('银行') ? bank : null;
    await fs.writeFile(path.join(figuresDir, `${asset.name}.json`), JSON.stringify({ source: asset.source, time: asset.time, request: record?.request, source_url: record?.tool_result.matches[0].source_url, selected_response_fields: asset.data }, null, 2));
  }
} finally {
  await browser.close();
}

const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const font = 'Microsoft YaHei';
const colors = { ink: '#20344F', blue: '#2867BF', muted: '#566C83', line: '#BBCBDE', mint: '#E4F4ED', pale: '#E7EFFF', violet: '#EEE9F9', orange: '#FFF0DF' };
const slideMetadata = [];
function text(slide, content, left, top, width, height, size = 25, color = colors.ink, bold = false, alignment = 'left', name = 'text') {
  const shape = slide.shapes.add({ geometry: 'textbox', name, position: { left, top, width, height }, fill: 'none', line: { fill: 'none', width: 0 } });
  shape.text = content;
  shape.text.style = { typeface: font, fontSize: size, color, bold, alignment, verticalAlignment: 'middle', autoFit: 'none', insets: { left: 0, right: 0, top: 0, bottom: 0 } };
  return shape;
}
function box(slide, content, left, top, width, height, fill = colors.pale, size = 25) {
  const shape = slide.shapes.add({ geometry: 'roundRect', name: 'diagram-node', position: { left, top, width, height }, fill, line: { fill: colors.line, width: 1.2 }, borderRadius: 10 });
  shape.text = content;
  shape.text.style = { typeface: font, fontSize: size, color: colors.ink, alignment: 'center', verticalAlignment: 'middle', autoFit: 'none', insets: { left: 10, right: 10, top: 8, bottom: 8 } };
  return shape;
}
function connect(slide, from, to, down = false) {
  return slide.shapes.connect(from, to, { kind: 'straight', fromSide: down ? 'bottom' : 'right', toSide: down ? 'top' : 'left', line: { fill: '#6C829D', width: 2 }, head: { type: 'triangle', width: 'sm', length: 'sm' } });
}
function note(slide, intro, references, heading) {
  slide.speakerNotes.textFrame.setText(`${intro}\n\n实现依据：${references.join('；')}。\n对应技术文档：${heading}。`);
}
function makeSlide(title, section, intro, references = [], heading = '') {
  const slide = presentation.slides.add();
  slide.background.fill = '#FFFFFF';
  const index = slideMetadata.length + 1;
  text(slide, title, 64, 44, 1152, 64, 40, colors.ink, true, 'left', 'slide-title');
  if (heading) text(slide, heading, 64, 114, 1152, 34, 21, colors.muted, false, 'left', 'document-heading');
  text(slide, intro, 64, 580, 1152, 88, 23, colors.muted, false, 'left', 'figure-introduction');
  text(slide, `Prism · ${section}`, 64, 680, 960, 25, 17, colors.muted, false, 'left', 'footer');
  text(slide, `${index}`, 1160, 680, 55, 25, 17, colors.muted, false, 'right', 'page-number');
  note(slide, intro, references, heading);
  slideMetadata.push({ index, title, section, intro, references, heading, slide });
  return slide;
}
function chain(slide, labels, top = 245, fill = colors.pale) {
  const gap = 27;
  const width = (1152 - gap * (labels.length - 1)) / labels.length;
  const shapes = labels.map((label, i) => box(slide, label, 64 + i * (width + gap), top, width, 110, fill, labels.length > 4 ? 23 : 26));
  for (let i = 1; i < shapes.length; i++) connect(slide, shapes[i - 1], shapes[i]);
  return shapes;
}
function divider(number, title, english, section, intro) {
  const slide = presentation.slides.add();
  slide.background.fill = '#F5F7FA';
  text(slide, number, 200, 242, 225, 150, 126, '#25282C', true);
  text(slide, english, 465, 223, 700, 50, 30, '#333840');
  text(slide, title, 465, 290, 745, 92, 60, colors.blue, true);
  text(slide, intro, 470, 409, 660, 80, 23, colors.muted);
  const index = slideMetadata.length + 1;
  note(slide, intro, [], `分类 ${number}`);
  slideMetadata.push({ index, title, section, intro, references: [], heading: `分类 ${number}`, slide, divider: true });
}
function table(slide, values, widths, top = 182, height = 335, size = 23) {
  const result = slide.tables.add({ rows: values.length, columns: values[0].length, left: 64, top, width: 1152, height, columnWidths: widths, values });
  for (let row = 0; row < values.length; row++) for (let column = 0; column < values[0].length; column++) {
    const cell = result.getCell(row, column);
    cell.fill = row === 0 ? colors.pale : row % 2 ? '#FFFFFF' : '#F6F8FB';
    cell.text.style = { typeface: font, fontSize: size, color: colors.ink, bold: row === 0, autoFit: 'none' };
  }
  return result;
}

{
  const slide = presentation.slides.add();
  slide.background.fill = '#F7F9FC';
  text(slide, 'Prism', 86, 180, 1120, 85, 70, colors.blue, true);
  text(slide, '个性化证券投顾智能体系统', 86, 293, 1120, 85, 53, colors.ink, true);
  text(slide, '核心技术 · 创新机制 · 实际数据', 90, 412, 1080, 48, 31, colors.muted);
  const intro = '演示文稿依据《技术文档－创新详解版》组织系统技术、四项创新机制和实际数据记录。图形说明模块职责、算法输入输出以及来源和版本关系，具体实现位置列入各页备注与技术对应表。';
  note(slide, intro, ['docs/submission/Prism-技术文档-创新详解版.docx'], '第五至第七章');
  slideMetadata.push({ index: 1, title: 'Prism 技术与创新', section: '系统与核心技术', intro, references: [], heading: '第五至第七章', slide });
}
divider('01', '系统与核心技术', 'System and Core Technologies', '系统与核心技术', '开发环境与系统职责 → 六项核心技术');
{
  const intro = '架构图展示同源工作台、FastAPI 应用及专业研究、证据验证、确定性计算和双闸门之间的关系。画像和持仓提供用户约束，金融 Provider 提供记录与质量状态，建议结果关联可验证回执及历史记录。';
  const slide = makeSlide('系统技术架构', '系统与核心技术', intro, ['app/api/main.py', 'app/service/', 'docs/submission/Prism系统技术架构.svg'], '5.2 前后端 AI 系统');
  slide.images.add({ blob: new Uint8Array(await fs.readFile('docs/submission/Prism系统技术架构.png')), contentType: 'image/png', alt: intro, fit: 'contain', position: { left: 202, top: 155, width: 875, height: 412 } });
}
{
  const slide = makeSlide('开发环境与前后端职责', '系统与核心技术', '浏览器组织输入与展示；FastAPI 校验并调用应用服务；领域模块完成研究、计算与审查。具体依赖按项目配置安装，HTTP 和 SSE 传递请求及运行事件。', ['pyproject.toml', 'package.json', 'app/api/main.py', 'app/api/static/app.js'], '5.1 开发环境 / 5.2 前后端 AI 系统');
  chain(slide, ['HTML · CSS · JavaScript\nAntV X6 · Markdown', 'Python 3.11–3.12\nFastAPI · Pydantic 2', 'Decimal · 领域规则\nSQLite / PostgreSQL'], 213);
  text(slide, 'HTTP / SSE', 220, 354, 230, 40, 25, colors.blue);
  text(slide, '用户归属 / 版本', 620, 354, 260, 40, 25, colors.blue);
  text(slide, 'Pillow · RapidOCR · OpenPyXL · python-multipart · Uvicorn', 64, 432, 1152, 52, 28);
}
{
  const slide = makeSlide('数据接入与确认输入', '系统与核心技术', '外部查询由 Provider 统一字段和来源状态；图片与表格经识别或导入形成待确认资料。语言模型产生意图与字段候选，用户确认后才形成计算上下文。', ['app/providers/skillhub.py', 'app/providers/contracts.py', 'app/llm/ocr_portfolio_parser.py', 'app/trading_history/importer.py', 'app/service/natural_profile.py'], '5.2.1 前端系统 / 5.2.3 AI 服务开发系统');
  chain(slide, ['问财 SkillHub\n金融 Provider', '来源 · 单位 · 时间\n四类结果状态', 'Evidence\n研究任务输入'], 190, colors.mint);
  chain(slide, ['截图 / Excel / 文本\nOCR 与文件解析', '证券 · 数量 · 现金\n待确认字段', '用户确认\n画像与持仓快照'], 390);
}
{
  const slide = makeSlide('画像与风险约束映射', '系统与核心技术', '正式问卷经确定性规则形成分数与风险等级，预算绑定用户和画像版本。持仓观察值按同一分母与预算比较，超限记录保留观察值、上限和幅度。', ['app/profile/scoring.py', 'app/profile/questionnaire.py', 'app/risk/budget.py'], '5.3.1 投资者画像与风险约束映射');
  chain(slide, ['已确认问卷\n五项评分字段', 'Decimal 归一化\n加权分数', '等级映射\n33 / 66 分界', '版本化风险预算\n四类比例上限'], 218);
  text(slide, '正式问卷 19 题 → 展示维度与计算字段分别管理', 64, 393, 1152, 42, 27);
  text(slide, 'observed_weight_pct − limit_weight_pct = excess_weight_pct', 64, 470, 1152, 44, 26, colors.blue);
}
{
  const slide = makeSlide('来源关联约束的证据验证', '系统与核心技术', '验证按主体、指标、单位、期间与质量筛选记录，随后按 lineage_id 分组。有效独立来源参与支持与反对计数，冲突和依据不足保留为明确状态，引用继续传入研究结果。', ['app/research/cross_validation.py', 'app/research/contracts.py', 'app/contracts/evidence.py'], '5.3.2 来源关联约束的证据验证');
  chain(slide, ['主体 / 指标\n单位 / 期间', 'VERIFIED\n质量筛选', 'lineage_id\n来源分组', '支持 / 反对\n冲突 / 不足'], 218, colors.violet);
  chain(slide, ['Evidence', 'Fact', 'Finding', 'Recommendation'], 407);
}
{
  const slide = makeSlide('持仓暴露与集中度计算', '系统与核心技术', '持仓市值与成分比例产生资产及行业暴露。基金未覆盖成分继续保留，报告注明分母、分组及精度。证券 HHI 与含现金行业 HHI 使用各自的计算口径。', ['app/portfolio/exposure.py', 'app/portfolio/report.py', 'app/risk/concentration.py'], '5.3.3 持仓暴露与集中度计算');
  chain(slide, ['数量 × 报价\n持仓市值', '直接证券 / 基金成分\n暴露贡献', '资产 / 行业分组\n未覆盖成分', '权重与 HHI\n风险预算检查'], 222, colors.mint);
  text(slide, 'E(g) = Σ V(i) × a(i,g)       p(g) = E(g) / V × 100%', 64, 405, 1152, 50, 30, colors.blue);
  text(slide, 'HHI = Σ p(g)²       p(g) 使用百分比数值', 64, 477, 1152, 45, 29);
}
{
  const slide = makeSlide('交易单位与现金约束的再平衡', '系统与核心技术', '目标权重转换为金额与数量，卖出受持仓约束并扣除费用，买入受现金预留和交易单位约束。程序更新现金后重新计算换手率、组合暴露与风险，输出实际测算数量。', ['app/service/portfolio_rebalancing.py', 'app/rebalancing/contracts.py'], '5.3.4 交易单位与现金约束下的再平衡');
  chain(slide, ['目标权重\n金额变化', '卖出数量\n持仓与交易单位', '扣除费用\n更新可用现金', '买入二分查找\n最大可负担手数'], 215, colors.orange);
  chain(slide, ['shares · 成交金额', 'total_fees_cny', 'cash_after_cny', '交易后体检'], 407, colors.mint);
}
{
  const slide = makeSlide('专业研究依赖执行', '系统与核心技术', '研究计划声明依赖、必需字段和时间预算。满足依赖的节点并行运行，结果保留状态与引用；未完成条件影响整体结果和下游建议资格。专业处理入口覆盖市场、行业、证券、基金及可转债。', ['app/orchestration/contracts.py', 'app/orchestration/executor.py', 'app/service/specialist_matrix.py'], '5.3.5 专业研究协作');
  const plan = box(slide, '研究计划\n依赖与时间预算', 64, 262, 240, 115);
  const macro = box(slide, '宏观研究\nProvider 请求', 382, 180, 250, 95);
  const industry = box(slide, '行业研究\nProvider 请求', 382, 385, 250, 95);
  const stock = box(slide, '个股 / 基金研究\n结构化结果', 728, 262, 270, 115);
  const result = box(slide, '结果汇集\n状态与引用', 1054, 262, 170, 115, colors.mint, 24);
  connect(slide, plan, macro); connect(slide, plan, industry); connect(slide, macro, stock); connect(slide, industry, stock); connect(slide, stock, result);
  text(slide, '依赖示意；具体连接由当前 WorkflowDefinition 决定 · asyncio.gather', 64, 506, 1152, 39, 25, colors.blue);
}
{
  const slide = makeSlide('风险与合规双重审查', '系统与核心技术', '风险与合规分别检查其职责内的输入。整体状态按 BLOCKED、REVIEW_REQUIRED、PASS 的顺序聚合，只有双方 PASS 才取得建议资格；建议组合器继续核对输入绑定和引用。', ['app/gates/pipeline.py', 'app/gates/risk.py', 'app/gates/compliance.py', 'app/recommendation/composer.py'], '5.3.6 风险与合规双重审查');
  const input = box(slide, '画像 · 研究证据\n预算 · 配置 · 候选文本', 64, 264, 295, 120);
  const risk = box(slide, '风险闸门\n版本 · 预算 · 证据', 440, 184, 300, 100, colors.orange);
  const compliance = box(slide, '合规闸门\n引用 · 披露 · 禁止表述', 440, 389, 300, 100, colors.orange);
  const result = box(slide, '双方 PASS\nRecommendation\nDecisionReceipt', 847, 255, 355, 140, colors.mint);
  connect(slide, input, risk); connect(slide, input, compliance); connect(slide, risk, result); connect(slide, compliance, result);
  text(slide, 'BLOCKED > REVIEW_REQUIRED > PASS', 64, 520, 1152, 38, 28, colors.blue);
}
divider('02', '算法与创新机制', 'Algorithms and Innovation', '算法与创新机制', '按技术文档 6.1—6.5 说明机制、算法与评价条件');
{
  const slide = makeSlide('画像驱动的风险约束映射算法', '算法与创新机制', '创新机制把问卷字段、确定性分数、预算选择和持仓超限连接起来。维度变化影响分数，风险等级跨越分界时改变预算；上限比较、用户归属和画像版本参与同一次评估。', ['app/profile/scoring.py', 'app/risk/budget.py', 'app/risk/contracts.py'], '6.1 画像驱动的风险约束映射算法');
  table(slide, [['评分字段', '权重', '处理方式', '参与计算'], ['损失承受', '30%', '(s−1)/4', 'Decimal'], ['投资期限', '25%', '1 / 3 / 5 分', '归一化'], ['流动性需求', '20%', '5 / 3 / 1 分', '归一化'], ['投资经验', '10%', '1 / 3 / 5 分', '归一化'], ['收益预期', '15%', '1 / 3 / 5 分', '归一化']], [345, 190, 335, 282], 178, 342, 24);
  text(slide, 'score = 100 × Σ weight × (s−1)/4', 64, 535, 1152, 33, 27, colors.blue);
}
{
  const slide = makeSlide('来源关联约束的证据交叉验证算法', '算法与创新机制', '来源分组控制独立支持数量，同组重复记录只增加引用记录。组内冲突、口径差异或未验证输入要求复核；两个独立来源支持且无反对和待处理问题时才返回 SUPPORTED。', ['app/research/cross_validation.py'], '6.2 来源关联约束的证据交叉验证算法');
  chain(slide, ['相同口径的观测\nVERIFIED', '来源组 A\n同源记录去重', '来源组 B\n独立来源计数', '确定性判定\n状态与引用清单'], 209, colors.violet);
  table(slide, [['结果', '独立支持', '独立反对', '输入条件'], ['SUPPORTED', '至少 2', '0', '无待处理问题'], ['CONTRADICTED', '0', '至少 2', '无待处理问题'], ['UNRESOLVED', '存在冲突', '存在冲突', '口径或质量问题'], ['INSUFFICIENT', '独立依据不足', '独立依据不足', '不足以判定']], [320, 240, 240, 352], 354, 203, 21);
}
{
  const slide = makeSlide('交易单位与现金约束的再平衡算法', '算法与创新机制', '二分查找在候选交易手数范围内寻找能够覆盖成交金额和费用、同时保留最低现金的最大整数手数。每项交易更新现金，最后使用实际数量复核风险；这一计算保证单项可负担数量，整体配置仍受后续检查约束。', ['app/service/portfolio_rebalancing.py'], '6.3 交易单位与现金约束的再平衡算法');
  chain(slide, ['候选手数范围\nlow = 0, high = N', 'middle\n向上取中点', '成交金额 + 费用\n≤ 可支出现金', '更新边界\n得到最大可行手数'], 213, colors.orange);
  text(slide, '可支出现金 = 当前现金 − 初始总资产 × 最低现金比例', 64, 403, 1152, 46, 29, colors.blue);
  text(slide, '交易单位 · 持仓上限 · 佣金 · 印花税 · 过户费 · 交易后体检', 64, 481, 1152, 50, 27);
}
{
  const slide = makeSlide('依赖执行与独立双闸门的专业协作机制', '算法与创新机制', '任务依赖与研究状态约束后续证据使用，用户归属和输入版本约束审查对象。两个独立判定共同决定建议资格，回执保存输入、证据、规则版本与裁决关系，便于历史复核。', ['app/orchestration/executor.py', 'app/gates/pipeline.py', 'app/recommendation/contracts.py', 'app/recommendation/composer.py'], '6.4 依赖执行与独立双闸门的专业协作机制');
  chain(slide, ['DAG 依赖\n状态传播', '画像与持仓版本\n研究证据结果', '独立双闸门\n资格聚合', '建议组合器\n再次校验'], 218);
  chain(slide, ['输入版本', '规则版本', '证据引用', '闸门结果', 'DecisionReceipt'], 411, colors.mint);
}
{
  const slide = makeSlide('创新评价对象与使用条件', '算法与创新机制', '评价分别检查个人条件参与计算、证据满足规则、金额及比例可复算，以及建议资格符合审查结果。正式报告能够证明对应输入下的计算与状态；外部金融研究基准及完整咨询性能需要对应评价记录。', ['docs/submission/Prism-技术文档-创新详解版.docx', 'docs/submission/test-evidence/'], '6.5 创新评价与后续研究');
  table(slide, [['评价对象', '检查输入', '可核对结果', '评价条件'], ['画像约束', '问卷与画像版本', '分数、预算、超限', '已确认输入'], ['证据验证', '口径与 lineage', '支持、冲突与引用', '结构化观测'], ['金融计算', '数量、价格及规则', '金额、权重与现金', '同一分母与精度'], ['建议资格', '研究及双闸门结果', '资格、问题和回执', '输入版本一致']], [270, 282, 315, 285], 197, 340, 24);
}
divider('03', '实际数据与验证', 'Actual Data and Verification', '实际数据与验证', '历史正式报告 · 实际文档检索 · 技术与工程证据');
for (const [index, asset] of dataImages.entries()) {
  const title = ['实际组合报告字段', '实际宏观资料检索字段', '实际银行财报检索字段'][index];
  const slide = makeSlide(title, '实际数据与验证', asset.intro, [asset.source], index === 0 ? '7.1 正式组合报告案例' : '5.3.5 专业研究协作 / 当前文档检索实现');
  slide.images.add({ blob: new Uint8Array(await fs.readFile(path.join(figuresDir, `${asset.name}.png`))), contentType: 'image/png', alt: asset.intro, fit: 'contain', position: { left: 64, top: 172, width: 778, height: 386 } });
  const labels = index === 0 ? ['报告状态', 'REVIEW_REQUIRED', '总资产口径', '1,445,545.00 元'] : ['检索模式', 'HYBRID_RRF', '片段状态', 'RETRIEVED_UNVERIFIED'];
  labels.forEach((label, i) => text(slide, label, 885, 206 + i * 74, 326, 62, i % 2 ? 24 : 29, i % 2 ? colors.blue : colors.ink, i % 2 === 0));
}
{
  const slide = makeSlide('正式报告的金额与风险复算', '实际数据与验证', '金额与风险来自同一份历史正式报告。证券市值加现金等于总资产；最大资产按含现金总资产口径占 52.83%，超过成长型 50% 上限，现金占 1.94%，报告整体要求复核。', ['app/api/static/pages-snapshot.json', 'app/portfolio/report.py'], '7.1 正式组合报告案例');
  table(slide, [['项目', '金额或观察值', '比较条件', '报告结果'], ['证券市值', portfolio.holdings_value_cny + ' 元', '五个证券持仓', 'CALCULATED'], ['现金', portfolio.cash_cny + ' 元', '占总资产 1.94%', 'OVERBOUND'], ['总资产', portfolio.total_value_cny + ' 元', '证券 + 现金', 'CALCULATED'], ['最大资产比例', '52.83%', '成长型上限 50%', 'OVERBOUND'], ['证券资产 HHI', portfolio.concentration.asset_hhi, '证券市值分母', 'CALCULATED']], [300, 320, 290, 242], 183, 360, 23);
}
{
  const slide = makeSlide('专业研究的检索与计算支持', '实际数据与验证', '当前专业研究还使用 PDF 提取、关键词检索、语义向量和 RRF，以及时间序列计算模块。向量模型与 HMM 属于可选能力，运行依赖本地模型或相应库、输入质量和数据时间条件。', ['app/service/knowledge.py', 'app/service/knowledge_embedding.py', 'app/service/research_algorithms.py', 'pyproject.toml'], '5.3.5 关联支持技术 / 当前实现补充');
  chain(slide, ['PDF / 研究资料\npypdf', 'FTS5 · BM25\n中文相邻字符索引', 'e5-small · cosine\n语义向量', 'RRF 常数 60\n来源与片段'], 198, colors.violet);
  text(slide, 'NumPy · GaussianHMM · 协方差 · 因子计算', 64, 395, 1152, 48, 31);
  text(slide, 'Sentence Transformers · PyTorch · Transformers · 固定模型 revision', 64, 468, 1152, 55, 26, colors.blue);
}
{
  const slide = makeSlide('存储、安全与历史解释', '实际数据与验证', '上下文、研究记录与回执按用户归属保存。内容指纹和版本关系支持历史复核，Windows DPAPI 保护本地凭据，Markdown 经 DOMPurify 处理后展示，前端证据视图保留引用方向。', ['app/store/sqlite.py', 'app/store/postgres.py', 'app/security/store.py', 'app/api/static/markdown.src.js', 'app/service/advanced_explainability.py'], '5.2 前后端 AI 系统 / 7.4 用户信息与部署');
  chain(slide, ['用户归属\nowner_id', 'SQLite / PostgreSQL\n上下文与事件', 'SHA-256 · 版本\n引用与回执', '历史解释\n证据审计'], 207);
  text(slide, 'DPAPI / ctypes → 服务端凭据保护', 64, 395, 1152, 45, 30, colors.blue);
  text(slide, 'marked → DOMPurify → DOM 片段 → 研究结果展示', 64, 475, 1152, 45, 29);
}
{
  const slide = makeSlide('实现技术与文档对应索引', '实际数据与验证', '核心技术与创新机制使用同一套已核对的代码位置。完整对应表继续列出直接依赖、标准库、金融 Provider、前端工具和可选研究能力，具体条件与实际证据分别记录。', ['docs/submission/technical-presentation/技术与文档对应表.md'], '5.3 核心技术 / 第六章 创新亮点');
  table(slide, [['核心技术', '创新条目', '关键模块', '主要输出'], ['画像与预算', '6.1', 'profile / risk', '风险约束与超限'], ['来源与证据', '6.2', 'research / contracts', '验证状态与引用'], ['暴露与集中度', '支撑 6.1、6.3', 'portfolio / risk', '暴露、权重与 HHI'], ['再平衡', '6.3', 'service / rebalancing', '数量、费用与现金'], ['专业协作与双闸门', '6.4', 'orchestration / gates', '建议资格与回执']], [345, 190, 325, 292], 183, 357, 23);
}
assert.equal(slideMetadata.length, 25);
await (await PresentationFile.exportPptx(presentation)).save(path.join(buildDir, 'candidate.pptx'));
await fs.writeFile(path.join(buildDir, 'slide-manifest.json'), JSON.stringify(slideMetadata.map(({ slide, ...entry }) => entry), null, 2));
let introductions = '# Prism 配图介绍\n\n';
for (const asset of dataImages) introductions += `## ${asset.title}\n\n![${asset.title}](figures/${asset.name}.png)\n\n${asset.intro}\n\n来源：${asset.source}；记录时间：${asset.time}。\n\n`;
for (const entry of slideMetadata) introductions += `## 第 ${entry.index} 页 ${entry.title}\n\n${entry.intro}\n\n对应：${entry.heading}。\n\n`;
await fs.writeFile(path.join(deliveryDir, '配图介绍.md'), introductions);
console.log(JSON.stringify({ candidate: path.join(buildDir, 'candidate.pptx'), slides: slideMetadata.length, dataImages: dataImages.length }));
