import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(ROOT, 'docs', 'submission', 'figures-clean-cn');

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];
const EXECUTABLE_PATH = CHROME_CANDIDATES.find((p) => fs.existsSync(p));
if (!EXECUTABLE_PATH) {
  throw new Error('未找到 Chrome 或 Edge 浏览器可执行文件');
}

// 对应 Word A4 正文可打印宽度 146.5mm = 5.768in = 554 CSS px (96 DPI)
// deviceScaleFactor = 3 => 输出宽度 1662px (约 288 DPI)，插入 Word 时 1:1 匹配 146.5mm
// 正文字号 12pt (小四)，图中主字号 10.5pt (五号，小一号)，辅字号 9.5pt，绝不超过正文 12pt
const CANVAS_W = 554;

const CSS = `
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  width: ${CANVAS_W}px;
  background: #ffffff;
  font-family: "Microsoft YaHei", "PingFang SC", "SimHei", sans-serif;
  color: #1f2329;
  -webkit-font-smoothing: antialiased;
}
.canvas {
  width: ${CANVAS_W}px;
  padding: 12px 10px 14px 10px;
  background: #ffffff;
}

/* 通用卡片 */
.node {
  border-radius: 8px;
  padding: 8px 10px;
  text-align: center;
  border: 1.4px solid #cbd5e1;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 3px;
}
.node-title {
  font-size: 10.5pt;
  font-weight: 700;
  line-height: 1.3;
  color: #1f2329;
}
.node-sub {
  font-size: 9.2pt;
  font-weight: 400;
  line-height: 1.35;
  color: #4b5563;
}

/* 柔和语义配色（低饱和、打印清晰） */
.blue   { background: #eff6ff; border-color: #93c5fd; }
.blue .node-title { color: #1d4ed8; }

.orange { background: #fff7ed; border-color: #fdba74; }
.orange .node-title { color: #c2410c; }

.green  { background: #f0fdf4; border-color: #86efac; }
.green .node-title { color: #15803d; }

.purple { background: #faf5ff; border-color: #d8b4fe; }
.purple .node-title { color: #7e22ce; }

.amber  { background: #fffbeb; border-color: #fcd34d; }
.amber .node-title { color: #b45309; }

.red    { background: #fef2f2; border-color: #fca5a5; }
.red .node-title { color: #b91c1c; }

.slate  { background: #f8fafc; border-color: #cbd5e1; }
.slate .node-title { color: #334155; }

.dark   { background: #1e293b; border-color: #0f172a; }
.dark .node-title { color: #ffffff; }
.dark .node-sub { color: #cbd5e1; }

/* 分组框 */
.group {
  border: 1.2px dashed #cbd5e1;
  border-radius: 10px;
  padding: 9px 10px 10px 10px;
  background: #fcfcfd;
}
.group-solid {
  border: 1.3px solid #e2e8f0;
  border-radius: 10px;
  padding: 9px 10px 10px 10px;
  background: #f8fafc;
}
.group-orange {
  border: 1.3px solid #fed7aa;
  border-radius: 10px;
  padding: 9px 10px 10px 10px;
  background: #fffaf5;
}
.group-blue {
  border: 1.3px solid #bfdbfe;
  border-radius: 10px;
  padding: 9px 10px 10px 10px;
  background: #f8fbff;
}
.group-title {
  font-size: 9.8pt;
  font-weight: 700;
  color: #475569;
  margin-bottom: 7px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.group-title .badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 9pt;
  font-weight: 700;
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fdba74;
}
.group-title .badge-blue {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #93c5fd;
}

/* 布局工具 */
.row { display: flex; gap: 8px; align-items: stretch; }
.row > * { flex: 1; min-width: 0; }
.row-center { display: flex; gap: 8px; align-items: center; justify-content: center; }
.col { display: flex; flex-direction: column; gap: 6px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.grid-4 { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 7px; }

/* 向下箭头 */
.arrow-down {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2px 0;
  gap: 1px;
}
.arrow-down-label {
  font-size: 9pt;
  color: #64748b;
  line-height: 1.2;
}
.arrow-right {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto !important;
  padding: 0 1px;
}
.pill-note {
  font-size: 9pt;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 5px 9px;
  text-align: center;
  line-height: 1.35;
}
.pill-warn {
  font-size: 9pt;
  color: #9a3412;
  background: #fff7ed;
  border: 1px dashed #fdba74;
  border-radius: 6px;
  padding: 5px 9px;
  text-align: center;
  line-height: 1.35;
}

/* 横向三阶段卡片内步骤 */
.stage-row {
  display: flex;
  align-items: center;
  gap: 5px;
}
.stage-row .node { flex: 1; min-width: 0; padding: 7px 6px; }
`;

const SVG_DOWN = (color = '#64748b', h = 18) => `
<svg width="16" height="${h}" viewBox="0 0 16 ${h}" fill="none">
  <line x1="8" y1="0" x2="8" y2="${h - 6}" stroke="${color}" stroke-width="1.6"/>
  <path d="M3.5 ${h - 7.5} L8 ${h - 1.5} L12.5 ${h - 7.5}" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

const SVG_RIGHT = (color = '#64748b', w = 16) => `
<svg width="${w}" height="14" viewBox="0 0 ${w} 14" fill="none">
  <line x1="0" y1="7" x2="${w - 5}" y2="7" stroke="${color}" stroke-width="1.6"/>
  <path d="M${w - 7} 3 L${w - 1.5} 7 L${w - 7} 11" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

const SVG_SPLIT_2 = (color = '#64748b') => `
<svg width="100%" height="22" viewBox="0 0 520 22" preserveAspectRatio="none" fill="none" style="display:block">
  <line x1="260" y1="0" x2="260" y2="9" stroke="${color}" stroke-width="1.6"/>
  <line x1="130" y1="9" x2="390" y2="9" stroke="${color}" stroke-width="1.6"/>
  <line x1="130" y1="9" x2="130" y2="18" stroke="${color}" stroke-width="1.6"/>
  <line x1="390" y1="9" x2="390" y2="18" stroke="${color}" stroke-width="1.6"/>
  <path d="M126 15 L130 20 L134 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <path d="M386 15 L390 20 L394 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>`;

const SVG_MERGE_2 = (color = '#64748b') => `
<svg width="100%" height="22" viewBox="0 0 520 22" preserveAspectRatio="none" fill="none" style="display:block">
  <line x1="130" y1="0" x2="130" y2="10" stroke="${color}" stroke-width="1.6"/>
  <line x1="390" y1="0" x2="390" y2="10" stroke="${color}" stroke-width="1.6"/>
  <line x1="130" y1="10" x2="390" y2="10" stroke="${color}" stroke-width="1.6"/>
  <line x1="260" y1="10" x2="260" y2="19" stroke="${color}" stroke-width="1.6"/>
  <path d="M256 15.5 L260 20.5 L264 15.5" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>`;

const SVG_SPLIT_3 = (color = '#64748b') => `
<svg width="100%" height="22" viewBox="0 0 520 22" preserveAspectRatio="none" fill="none" style="display:block">
  <line x1="260" y1="0" x2="260" y2="18" stroke="${color}" stroke-width="1.6"/>
  <line x1="86" y1="9" x2="434" y2="9" stroke="${color}" stroke-width="1.6"/>
  <line x1="86" y1="9" x2="86" y2="18" stroke="${color}" stroke-width="1.6"/>
  <line x1="434" y1="9" x2="434" y2="18" stroke="${color}" stroke-width="1.6"/>
  <path d="M82 15 L86 20 L90 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <path d="M256 15 L260 20 L264 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <path d="M430 15 L434 20 L438 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>`;

const SVG_MERGE_3 = (color = '#64748b') => `
<svg width="100%" height="22" viewBox="0 0 520 22" preserveAspectRatio="none" fill="none" style="display:block">
  <line x1="86" y1="0" x2="86" y2="10" stroke="${color}" stroke-width="1.6"/>
  <line x1="260" y1="0" x2="260" y2="19" stroke="${color}" stroke-width="1.6"/>
  <line x1="434" y1="0" x2="434" y2="10" stroke="${color}" stroke-width="1.6"/>
  <line x1="86" y1="10" x2="434" y2="10" stroke="${color}" stroke-width="1.6"/>
  <path d="M256 15.5 L260 20.5 L264 15.5" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>`;

const SVG_SPLIT_4 = (color = '#64748b') => `
<svg width="100%" height="22" viewBox="0 0 520 22" preserveAspectRatio="none" fill="none" style="display:block">
  <line x1="260" y1="0" x2="260" y2="9" stroke="${color}" stroke-width="1.6"/>
  <line x1="65" y1="9" x2="455" y2="9" stroke="${color}" stroke-width="1.6"/>
  <line x1="65" y1="9" x2="65" y2="18" stroke="${color}" stroke-width="1.6"/>
  <line x1="195" y1="9" x2="195" y2="18" stroke="${color}" stroke-width="1.6"/>
  <line x1="325" y1="9" x2="325" y2="18" stroke="${color}" stroke-width="1.6"/>
  <line x1="455" y1="9" x2="455" y2="18" stroke="${color}" stroke-width="1.6"/>
  <path d="M61 15 L65 20 L69 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <path d="M191 15 L195 20 L199 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <path d="M321 15 L325 20 L329 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <path d="M451 15 L455 20 L459 15" stroke="${color}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>`;

const arrowDown = (label = '', color = '#64748b') => `
<div class="arrow-down">
  ${label ? `<div class="arrow-down-label">${label}</div>` : ''}
  ${SVG_DOWN(color)}
</div>`;

const node = (title, sub = '', cls = 'slate') => `
<div class="node ${cls}">
  <div class="node-title">${title}</div>
  ${sub ? `<div class="node-sub">${sub}</div>` : ''}
</div>`;

const FIGURES = [
  // 图 3-1 系统技术架构
  {
    file: '图3-01-系统技术架构.png',
    html: `
      <div class="node blue">
        <div class="node-title">网页工作台（用户入口）</div>
        <div class="node-sub">智能对话 · 风险测评 · 持仓体检 · 行情观察 · 专业研究</div>
      </div>
      ${arrowDown('提交问题与已确认资料')}
      <div class="group-blue">
        <div class="group-title"><span class="badge badge-blue">服务协调层</span> 统一校验与任务调度</div>
        <div class="grid-2">
          ${node('身份与前提校验', '核对账户、画像与持仓版本', 'slate')}
          ${node('主协调调度器', '拆解任务、按依赖并行执行', 'blue')}
        </div>
      </div>
      ${SVG_SPLIT_3()}
      <div class="grid-3">
        ${node('大语言模型', '听懂意图、选工具<br/>通俗解释结果', 'purple')}
        ${node('专业研究与数据', '行情、财报、基金<br/>保留来源与时间', 'green')}
        ${node('确定性金融计算', '市值、穿透、集中度<br/>再平衡数量测算', 'orange')}
      </div>
      ${SVG_MERGE_3()}
      <div class="group-orange">
        <div class="group-title"><span class="badge">双重审查闸门</span> 双方通过才输出建议</div>
        <div class="grid-2">
          ${node('风险审查', '核对画像上限、持仓与证据', 'orange')}
          ${node('合规审查', '核对事实引用与风险提示', 'orange')}
        </div>
      </div>
      ${SVG_SPLIT_2()}
      <div class="grid-2">
        ${node('可追溯结果与回执', '仅作研究参考，不直接下单', 'green')}
        ${node('本地与云端存储', '保存账户、画像、事实与回执', 'slate')}
      </div>
    `,
  },

  // 图 3-2 提示词组织与工具处理
  {
    file: '图3-02-提示词组织与工具处理.png',
    html: `
      <div class="grid-2">
        ${node('系统规则与当前问题', '明确职责边界与风险提示要求', 'blue')}
        ${node('已确认个人上下文', '画像、持仓与近六轮对话记录', 'blue')}
      </div>
      ${SVG_MERGE_2()}
      ${node('组装对话提示词与工具清单', '声明可调用工具的名称与参数规范', 'slate')}
      ${arrowDown()}
      <div class="row" style="align-items:center">
        <div style="flex:1.55">
          ${node('大模型理解意图并选择工具', '决定直接解释还是调用金融工具', 'purple')}
        </div>
        <div class="arrow-right">${SVG_RIGHT('#c2410c', 16)}</div>
        <div style="flex:1">
          <div class="pill-warn"><b>版本实时核对</b><br/>画像或持仓变动则中止并重确认</div>
        </div>
      </div>
      ${arrowDown('声明工具调用参数')}
      ${node('服务端校验参数与访问权限', '确认字段完整且仅查本人资料', 'orange')}
      ${arrowDown()}
      ${node('执行金融查询或程序计算', '获取实时数据、检索原文或算金额比例', 'green')}
      ${arrowDown('结果与数据来源回填对话')}
      ${node('大模型基于真实结果生成回答', '数据缺失时如实说明，绝不编造数值', 'blue')}
    `,
  },

  // 图 3-3 前端交互与状态框架
  {
    file: '图3-03-前端交互与状态框架.png',
    html: `
      ${node('浏览器工作台入口', '原生网页结构与页面路由切换', 'dark')}
      ${arrowDown()}
      <div class="group-blue">
        <div class="group-title"><span class="badge badge-blue">一、用户操作</span> 按任务分流入口</div>
        <div class="grid-3">
          ${node('智能对话', '提问与查看进度', 'blue')}
          ${node('画像与持仓', '问卷与资料确认', 'blue')}
          ${node('分析与行情', '查看风险与走势', 'blue')}
        </div>
      </div>
      ${arrowDown()}
      <div class="group-orange">
        <div class="group-title"><span class="badge">二、状态与通信</span> 账户隔离与流式交互</div>
        <div class="grid-2">
          ${node('前端状态协调', '管理当前账户、画像与持仓', 'orange')}
          ${node('请求与流式接收', '提交请求并实时显示工具进度', 'orange')}
        </div>
      </div>
      ${arrowDown('发送请求 / 接收结构化结果')}
      <div class="grid-2">
        ${node('后端服务接口', '返回数值、状态与数据来源', 'slate')}
        ${node('结果与图表呈现', '文字说明、行情图与流程图', 'green')}
      </div>
    `,
  },

  // 图 3-4 后端分层服务框架
  {
    file: '图3-04-后端分层服务框架.png',
    html: `
      ${node('接口入口层', '接收网页请求 · 校验身份归属与参数格式', 'dark')}
      ${arrowDown()}
      <div class="group-blue">
        <div class="group-title"><span class="badge badge-blue">一、应用服务层</span> 协调业务流程</div>
        <div class="grid-3">
          ${node('对话协调', '意图路由与工具调度', 'blue')}
          ${node('上下文管理', '画像、持仓与前提', 'blue')}
          ${node('研究调度', '按节点依赖执行', 'blue')}
        </div>
      </div>
      ${arrowDown()}
      <div class="group-orange">
        <div class="group-title"><span class="badge">二、核心计算与审查层</span> 纯程序计算、可独立验证</div>
        <div class="grid-3">
          ${node('金融计算', '暴露、预算、再平衡', 'orange')}
          ${node('证据核对', '来源分组与交叉验证', 'orange')}
          ${node('双闸门审查', '风险审查与合规审查', 'orange')}
        </div>
      </div>
      ${arrowDown()}
      <div class="group-solid">
        <div class="group-title">三、外部接入与数据存储层</div>
        <div class="grid-3">
          ${node('外部接口适配', '大模型与金融数据源', 'purple')}
          ${node('业务数据库', '保存画像、快照与回执', 'green')}
          ${node('资料解析工具', '表格读取与截图识别', 'slate')}
        </div>
      </div>
    `,
  },

  // 图 3-5 工作台页面入口与反馈
  {
    file: '图3-05-工作台页面入口与反馈.png',
    html: `
      ${node('顶部导航栏与任务入口', '按用户想做的事分类，默认只看核心结论', 'dark')}
      ${SVG_SPLIT_2()}
      <div class="grid-2">
        <div class="group-orange">
          <div class="group-title"><span class="badge">个人投资分析</span></div>
          <div class="col">
            ${node('对话工作台', '提问、看工具进度、查历史', 'orange')}
            ${node('持仓分析', '导入持仓、看盈亏与集中度', 'orange')}
            ${node('个人中心', '风险测评、八维画像与设置', 'orange')}
          </div>
        </div>
        <div class="group-blue">
          <div class="group-title"><span class="badge badge-blue">市场与专业研究</span></div>
          <div class="col">
            ${node('市场观察', '切指数、看走势与技术指标', 'blue')}
            ${node('研究工作台', '查数据、搜研报、跑算法', 'blue')}
            ${node('技能商店', '查看并启用各项研究能力', 'blue')}
          </div>
        </div>
      </div>
      ${SVG_MERGE_2()}
      ${node('统一状态与来源反馈', '明确标出“通过 / 超限 / 已算好”，并展示数据时间与缺项', 'green')}
    `,
  },

  // 图 3-6 账户、对话和研究数据的数据库外键
  {
    file: '图3-06-数据库外键关系.png',
    html: `
      <div class="group-blue" style="margin-bottom:10px">
        <div class="group-title"><span class="badge badge-blue">账户与对话数据</span> 数据库级联删除</div>
        <div class="grid-2">
          <div class="col">
            ${node('本地账户表', '保存账号与密码哈希', 'blue')}
            ${arrowDown('按用户名关联')}
            ${node('登录会话表', '校验有效期与账户状态', 'slate')}
          </div>
          <div class="col">
            ${node('对话会话表', '保存对话标题与更新时间', 'blue')}
            ${arrowDown('按会话编号关联')}
            ${node('对话消息表', '按顺序保存问答记录', 'slate')}
          </div>
        </div>
      </div>
      <div class="group-orange">
        <div class="group-title"><span class="badge">研究数据</span> 按账户与快照编号联合关联</div>
        ${node('研究快照表', '记录单次研究任务与输入版本', 'orange')}
        ${SVG_SPLIT_2('#c2410c')}
        <div class="grid-2">
          ${node('结构化事实表', '保存可核验的金融观测值', 'slate')}
          ${node('原始报文记录表', '留存原始请求与响应备查', 'slate')}
        </div>
      </div>
    `,
  },

  // 图 3-7 资料版本与会话前提的应用层关联
  {
    file: '图3-07-资料版本与应用层关联.png',
    html: `
      <div class="group-blue" style="margin-bottom:10px">
        <div class="group-title"><span class="badge badge-blue">知识资料</span> 按文档编号与版本号关联</div>
        ${node('知识资料主表', '记录资料权限与当前最新版本号', 'blue')}
        ${SVG_SPLIT_2('#1d4ed8')}
        <div class="grid-2">
          ${node('历史版本表', '保留各版本全文与内容摘要', 'slate')}
          ${node('检索片段表', '按当前版本核对原文与页码', 'slate')}
        </div>
      </div>
      <div class="group-orange">
        <div class="group-title"><span class="badge">个人前提与决策</span> 服务层校验版本与指纹</div>
        <div class="grid-2">
          ${node('已确认问卷表', '保存有效画像版本', 'orange')}
          ${node('当前持仓表', '保存当前持仓快照', 'orange')}
        </div>
        ${SVG_MERGE_2('#c2410c')}
        ${node('会话前提表', '绑定账户、版本与内容指纹', 'amber')}
        ${arrowDown('引用版本核验', '#c2410c')}
        ${node('决策审查记录表', '留存审查状态与可追溯回执', 'green')}
      </div>
    `,
  },

  // 图 3-8 金融提供方结果状态与后续处理
  {
    file: '图3-08-金融数据状态与处理.png',
    html: `
      ${node('发起统一金融数据查询', '明确查询操作、标的代码与必需字段', 'blue')}
      ${arrowDown()}
      ${node('外部数据源执行并返回质量状态', '同步记录数据出处、时间、单位与缺项', 'orange')}
      ${SVG_SPLIT_4()}
      <div class="grid-4">
        <div class="col">
          ${node('成功', '字段完整有效', 'green')}
          ${arrowDown('', '#15803d')}
          ${node('正常使用', '展示来源<br/>与数据时间', 'slate')}
        </div>
        <div class="col">
          ${node('部分可用', '仅含部分字段', 'amber')}
          ${arrowDown('', '#b45309')}
          ${node('谨慎采用', '只用有效项<br/>并标明缺口', 'slate')}
        </div>
        <div class="col">
          ${node('空结果', '未查到记录', 'slate')}
          ${arrowDown()}
          ${node('如实提示', '保留条件<br/>说明无数据', 'slate')}
        </div>
        <div class="col">
          ${node('失败', '接口异常超时', 'red')}
          ${arrowDown('', '#b91c1c')}
          ${node('显式报错', '展示原因<br/>与重试提示', 'slate')}
        </div>
      </div>
    `,
  },

  // 图 3-9 画像与预算参与组合计算
  {
    file: '图3-09-画像与预算映射流程.png',
    html: `
      <div class="group-solid">
        <div class="group-title">一、问卷测评与确定性评分</div>
        <div class="stage-row">
          ${node('十九题问卷', '采集风险与经验', 'blue')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('完整性检查', '核对必填与冲突', 'slate')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('确定性评分', '算出八维分与等级', 'orange')}
        </div>
      </div>
      ${SVG_SPLIT_2('#c2410c')}
      <div class="grid-2">
        ${node('八维投资者画像', '直观展示风险、经验、偏好等维度', 'green')}
        ${node('风险等级与仓位预算', '映射单一资产、行业与未分类上限', 'orange')}
      </div>
      ${arrowDown('预算作为硬约束进入后续组合计算', '#c2410c')}
      ${node('持仓风险比对与超限提示', '逐项对照上限，标出超限标的与超出百分点', 'amber')}
    `,
  },

  // 图 3-10 持仓穿透、金额守恒与集中度计算
  {
    file: '图3-10-持仓穿透与集中度计算.png',
    html: `
      ${node('输入持仓数量、报价与资产标识', '校验非负金额、币种与数据时间', 'blue')}
      ${arrowDown()}
      ${node('高精度计算各标的市值', '市值 = 持仓数量 × 最新价格（避免浮点误差）', 'orange')}
      ${SVG_SPLIT_3()}
      <div class="grid-3">
        ${node('直接持仓', '按个股与所属<br/>行业直接计入', 'slate')}
        ${node('基金穿透部分', '按披露成分比例<br/>拆分到底层资产', 'orange')}
        ${node('未穿透金额', '无成分披露部分<br/>单列为未分类', 'amber')}
      </div>
      ${SVG_MERGE_3()}
      ${node('金额守恒核验', '拆分后各部分合计 = 原始组合总市值', 'green')}
      ${arrowDown()}
      ${node('计算资产占比与集中度指标', '分别按纯证券持仓、含现金总资产两种口径计算', 'blue')}
      ${arrowDown()}
      ${node('对照个人画像预算上限', '标出超限资产或行业，以及具体超限幅度', 'orange')}
    `,
  },

  // 图 3-11 再平衡数量与现金计算
  {
    file: '图3-11-再平衡数量与现金计算.png',
    html: `
      <div class="group-blue">
        <div class="group-title"><span class="badge badge-blue">一、明确调整目标</span></div>
        <div class="stage-row">
          ${node('确认现有组合', '持仓、报价与现金', 'slate')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('套用风险约束', '画像预算与集中度', 'orange')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('算出金额差额', '目标与当前权重差', 'slate')}
        </div>
      </div>
      ${arrowDown('', '#c2410c')}
      <div class="group-orange">
        <div class="group-title"><span class="badge">二、按交易规则算数量</span> 先卖后买、严守现金底线</div>
        <div class="stage-row">
          ${node('按手数取整', '符合最小交易单位', 'slate')}
          <div class="arrow-right">${SVG_RIGHT('#c2410c')}</div>
          ${node('先算卖出', '扣费用、更新现金', 'orange')}
          <div class="arrow-right">${SVG_RIGHT('#c2410c')}</div>
          ${node('再算买入', '预留现金、求最大可买', 'orange')}
        </div>
      </div>
      ${arrowDown('', '#15803d')}
      <div class="group-solid">
        <div class="group-title">三、交易后复核与输出</div>
        <div class="stage-row">
          ${node('资金与费用汇总', '核算费用与换手率', 'slate')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('复核风控达标', '未达标则如实标出', 'amber')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('输出参考方案', '先卖后买清单与说明', 'green')}
        </div>
      </div>
    `,
  },

  // 图 3-12 研究依赖执行、排队容量与时间预算
  {
    file: '图3-12-研究调度与时间预算.png',
    html: `
      ${node('生成研究执行计划', '检查节点依赖顺序，排除循环依赖', 'blue')}
      ${arrowDown()}
      <div class="grid-2">
        ${node('排队容量限制', '总排队上限 400，单人上限 200', 'amber')}
        ${node('总体时间预算', '单次研究最长 60 秒，超时即止', 'amber')}
      </div>
      ${SVG_MERGE_2()}
      ${node('研究调度引擎', '同时活跃任务上限 100 · 前置完成后自动触发下游', 'orange')}
      ${SVG_SPLIT_2()}
      <div class="grid-2">
        ${node('金融数据并发名额', '默认上限 100，防接口拥堵', 'slate')}
        ${node('大模型并发名额', '默认上限 8，防资源耗尽', 'purple')}
      </div>
      ${SVG_MERGE_2()}
      ${node('汇总各节点状态与结果', '已完成节点结果保留；超时或失败仅取消下游并记明原因', 'green')}
    `,
  },

  // 图 3-13 来源分组与证据验证
  {
    file: '图3-13-来源分组与证据验证.png',
    html: `
      <div class="group-blue">
        <div class="group-title"><span class="badge badge-blue">一、统一口径与去重</span> 防止同一来源被重复计数</div>
        <div class="stage-row">
          ${node('收集原始证据', '保留出处与质量状态', 'slate')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('核对口径一致', '标的、指标、单位、期间', 'blue')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('按来源分组', '同源多次引用只算一次', 'orange')}
        </div>
      </div>
      ${arrowDown('', '#c2410c')}
      <div class="group-orange">
        <div class="group-title"><span class="badge">二、独立交叉验证</span> 至少两家独立来源支持才成立</div>
        <div class="stage-row">
          ${node('组内冲突检查', '同源数值矛盾转复核', 'slate')}
          <div class="arrow-right">${SVG_RIGHT('#c2410c')}</div>
          ${node('判定验证状态', '支持 / 反对 / 冲突 / 不足', 'orange')}
          <div class="arrow-right">${SVG_RIGHT('#c2410c')}</div>
          ${node('沉淀可信事实', '保留全部原始证据引用', 'green')}
        </div>
      </div>
      ${arrowDown('', '#15803d')}
      <div class="group-solid">
        <div class="group-title">三、支撑研究结论与建议</div>
        <div class="stage-row">
          ${node('形成研究发现', '逐条引用已验证事实', 'slate')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('风险与合规审查', '独立校验建议资格', 'orange')}
          <div class="arrow-right">${SVG_RIGHT()}</div>
          ${node('建议与决策回执', '结论可逐层回溯依据', 'green')}
        </div>
      </div>
    `,
  },

  // 图 3-14 风险与合规审查
  {
    file: '图3-14-风险与合规审查.png',
    html: `
      ${node('汇集研究发现与组合计算结果', '附带完整证据引用、画像版本与组合指标', 'blue')}
      ${SVG_SPLIT_2('#c2410c')}
      <div class="group-orange">
        <div class="group-title"><span class="badge">独立双闸门并行审查</span> 互相隔离、各自一票否决</div>
        <div class="grid-2">
          ${node('风险审查闸门', '核对画像、持仓上限<br/>与证据完整性', 'orange')}
          ${node('合规审查闸门', '核对事实引用、风险揭示<br/>与禁止性表述', 'orange')}
        </div>
      </div>
      ${arrowDown('按严格优先级汇总裁决建议资格', '#c2410c')}
      <div class="grid-3">
        ${node('通过', '双方合格<br/>生成建议与回执', 'green')}
        ${node('需人工复核', '暂缓生成建议<br/>列明缺项原因', 'amber')}
        ${node('拦截终止', '禁止输出建议<br/>留存拦截记录', 'red')}
      </div>
    `,
  },

  // 图 3-15 研究资料提取、候选范围检查与引用返回
  {
    file: '图3-15-研究资料提取与检索.png',
    html: `
      ${node('上传私有研究资料', '支持纯文本与可提取文字的电子文档（限 8 兆、千页内）', 'blue')}
      ${arrowDown()}
      ${node('提取正文并切分为短片段', '保留标题、页码与发布时间，长段按字数上限切分', 'slate')}
      ${arrowDown()}
      ${node('过滤可见范围与最新版本', '仅检索本人可见、发布时间合规且属当前版本的片段', 'orange')}
      ${SVG_SPLIT_2()}
      <div class="grid-2">
        ${node('关键词精准检索', '默认开启，按字词相关性排序', 'blue')}
        ${node('语义向量检索', '按需开启，捕捉相近含义表达', 'purple')}
      </div>
      ${SVG_MERGE_2()}
      ${node('融合排序并返回原文引用', '附带原文、页码与版本号；文中金融数据仍须独立核验', 'green')}
    `,
  },

  // 图 3-16 会话上下文与工具处理
  {
    file: '图3-16-会话上下文与工具处理.png',
    html: `
      <div class="grid-3">
        ${node('当前问题', '新提问或追问', 'blue')}
        ${node('历史记录', '显式保存与恢复', 'slate')}
        ${node('画像与持仓', '当前已确认版本', 'orange')}
      </div>
      ${SVG_MERGE_3()}
      ${node('请求入口 · 前提核验', '已绑定前提则校验版本与指纹；未通过则提示重新确认', 'dark')}
      ${arrowDown('校验通过，附带近六轮对话分流处理')}
      <div class="grid-3">
        ${node('一般概念问答', '金融知识解释<br/>无需个人前提', 'slate')}
        ${node('金融数据查询', '行情、财报与资讯<br/>返回来源与时间', 'blue')}
        ${node('个人组合分析', '持仓体检或调仓<br/>必须由程序测算', 'orange')}
      </div>
      ${SVG_MERGE_3()}
      ${node('依据工具结果组织最终回答', '数值由程序产生，调仓前须用户确认约束条件', 'green')}
    `,
  },

  // 图 3-17 会话前提确认、持续检查与资料变化处理
  {
    file: '图3-17-会话前提状态流转.png',
    html: `
      <div class="stage-row" style="align-items:stretch">
        ${node('未锁定状态', '用户尚未确认问卷与持仓', 'slate')}
        <div class="arrow-right">${SVG_RIGHT('#15803d', 20)}</div>
        ${node('已锁定状态', '保存画像、持仓版本与内容指纹', 'green')}
      </div>
      ${arrowDown('发起对话与流式输出期间', '#1d4ed8')}
      ${node('持续核对归属、版本与指纹', '每次提问与输出前均复核是否与锁定版本一致', 'blue')}
      ${SVG_SPLIT_2()}
      <div class="grid-2">
        ${node('核对一致 · 正常执行', '调用工具并流式输出回答<br/>全程对应同一份输入', 'green')}
        ${node('检测到资料变动', '画像、持仓或模式已改<br/>中止生成并提示重新确认', 'red')}
      </div>
      <div style="margin-top:8px">
        <div class="pill-warn">用户重新确认最新资料后，重新进入<b>「已锁定」</b>状态；历史记忆须手动恢复并确认才参与计算</div>
      </div>
    `,
  },

  // 图 3-18 确定性研究算法的输入、计算与结果条件
  {
    file: '图3-18-确定性研究算法流程.png',
    html: `
      ${node('提交真实历史数据与截止日期', '严格校验数值类型、样本量、时间顺序与有效性', 'blue')}
      ${SVG_SPLIT_3()}
      <div class="grid-3">
        ${node('市场状态识别', '有序日收益序列<br/>至少 252 条样本<br/>输出状态概率', 'orange')}
        ${node('协方差矩阵收缩', '多资产收益序列<br/>降低样本估计误差<br/>输出稳定协方差', 'orange')}
        ${node('五因子收益构造', '按公告时点筛选<br/>分组算因子收益<br/>杜绝未来数据', 'orange')}
      </div>
      ${SVG_MERGE_3()}
      ${node('关联方法版本、数据来源与输入快照', '离线可复现，独立于大模型运行', 'slate')}
      ${SVG_SPLIT_2()}
      <div class="grid-2">
        ${node('已算好', '满足条件，输出完整指标与依据', 'green')}
        ${node('暂不可用', '样本不足或未收敛，明确说明原因', 'amber')}
      </div>
    `,
  },
];

function wrapHtml(bodyHtml) {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>${CSS}</style>
</head>
<body>
<div class="canvas" id="canvas">${bodyHtml}</div>
</body>
</html>`;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: EXECUTABLE_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none'],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: CANVAS_W, height: 1200, deviceScaleFactor: 3 });

    const manifest = [];
    for (const fig of FIGURES) {
      await page.setContent(wrapHtml(fig.html), { waitUntil: 'load' });
      const rect = await page.evaluate(() => {
        const el = document.getElementById('canvas');
        const r = el.getBoundingClientRect();
        return { width: Math.ceil(r.width), height: Math.ceil(r.height) };
      });
      await page.setViewport({ width: CANVAS_W, height: rect.height, deviceScaleFactor: 3 });
      const outPath = path.join(OUT_DIR, fig.file);
      await page.screenshot({
        path: outPath,
        clip: { x: 0, y: 0, width: CANVAS_W, height: rect.height },
      });
      manifest.push({
        file: fig.file,
        css_px: [CANVAS_W, rect.height],
        png_px: [CANVAS_W * 3, rect.height * 3],
        word_mm_at_288dpi: [
          Number(((CANVAS_W * 3) / 288 * 25.4).toFixed(1)),
          Number(((rect.height * 3) / 288 * 25.4).toFixed(1)),
        ],
      });
      console.log(`Rendered ${fig.file} (${CANVAS_W * 3}x${rect.height * 3})`);
    }
    fs.writeFileSync(
      path.join(OUT_DIR, 'manifest.json'),
      JSON.stringify(manifest, null, 2),
      'utf-8'
    );
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
