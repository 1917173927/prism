import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile, FileBlob } from "@oai/artifact-tool";

const workspaceDir = "E:\\prism";
const SKILL_DIR = "C:\\Users\\pc\\.codex\\plugins\\cache\\openai-primary-runtime\\presentations\\26.909.12148\\skills\\presentations";
const TMP_DIR = path.join(workspaceDir, ".codex-temp", "prism-technical-deck");
const outputDir = path.join(workspaceDir, "docs", "submission");
const previewDir = path.join(outputDir, "PRISM-技术模块-预览");
const FINAL_PPTX = path.join(outputDir, "PRISM-技术模块-10页答辩版.pptx");
const RUNTIME_PYTHON = "C:\\Users\\pc\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe";

const { finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools", "artifact_tool_utils.mjs")).href,
);

await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const W = 1280;
const H = 720;
const FONT = "Microsoft YaHei";
const C = {
  bg: "#FCFBF7",
  white: "#FFFFFF",
  ink: "#172D3D",
  muted: "#667783",
  faint: "#D8E0E3",
  navy: "#183B56",
  blue: "#2F6684",
  paleBlue: "#EDF4F7",
  orange: "#E47A4A",
  paleOrange: "#FFF0E8",
  teal: "#167C80",
  paleTeal: "#EAF7F6",
  green: "#3D7A57",
  paleGreen: "#EEF6F0",
  brown: "#9A6A22",
  paleBrown: "#FBF4E7",
  red: "#B4493D",
  paleRed: "#FCEDEA",
  gray: "#F2F3F0",
  darkGray: "#4F575B",
};

const asset = (...parts) => path.join(workspaceDir, ...parts);
const imageFiles = {
  swagger: asset("docs", "showcase", "backend_api_full_architecture.png"),
  workbench: asset("docs", "showcase", "01_v3_investor_workbench_overview.png"),
  currentWorkbench: asset("docs", "showcase", "current-pages-snapshot-workbench-20260917.png"),
  rebalance: asset("docs", "showcase", "04_v3_rebalancing_plan_stepper.png"),
  profile: asset("docs", "showcase", "06_v3_user_profile_modal.png"),
};
const imageBytes = Object.fromEntries(
  await Promise.all(Object.entries(imageFiles).map(async ([key, file]) => [key, await fs.readFile(file)])),
);

function addShape(slide, x, y, w, h, fill = C.white, line = C.faint, radius = 18, name = undefined) {
  return slide.shapes.add({
    geometry: "roundRect",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: 1 },
    borderRadius: radius,
  });
}

function addText(slide, text, x, y, w, h, opts = {}) {
  const shape = slide.shapes.add({
    geometry: opts.geometry ?? "textbox",
    name: opts.name,
    position: { left: x, top: y, width: w, height: h },
    fill: opts.fill ?? "none",
    line: opts.line ? { style: opts.lineStyle ?? "solid", fill: opts.line, width: opts.lineWidth ?? 1 } : { style: "solid", fill: "none", width: 0 },
    borderRadius: opts.radius ?? 0,
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: opts.size ?? 22,
    bold: opts.bold ?? false,
    italic: opts.italic ?? false,
    color: opts.color ?? C.ink,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "middle",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: "square",
    insets: opts.insets ?? { top: 6, right: 8, bottom: 6, left: 8 },
  };
  return shape;
}

function addPill(slide, text, x, y, w, fill, color, line = fill, size = 18) {
  return addText(slide, text, x, y, w, 32, {
    fill, line, radius: 16, size, color, bold: true, align: "center", valign: "middle",
    insets: { top: 2, right: 6, bottom: 2, left: 6 },
  });
}

function connect(slide, from, to, opts = {}) {
  return slide.shapes.connect(from, to, {
    kind: opts.kind ?? "straight",
    fromSide: opts.fromSide ?? "right",
    toSide: opts.toSide ?? "left",
    line: { style: opts.style ?? "solid", fill: opts.color ?? C.blue, width: opts.width ?? 2 },
    tail: { type: opts.head ?? "triangle", width: "sm", length: "sm" },
  });
}

function addHeader(slide, page, section, title, subtitle, status = "当前实现") {
  slide.background.fill = C.bg;
  addText(slide, `${String(page).padStart(2, "0")}  ${section}`, 58, 24, 310, 28, { size: 17, bold: true, color: C.orange, insets: { top: 0, right: 0, bottom: 0, left: 0 } });
  addText(slide, title, 58, 54, 900, 52, { size: 40, bold: true, color: C.ink, insets: { top: 0, right: 0, bottom: 0, left: 0 } });
  addText(slide, subtitle, 60, 108, 1040, 34, { size: 20, color: C.muted, insets: { top: 0, right: 0, bottom: 0, left: 0 } });
  addPill(slide, status, 1080, 48, 140, status === "当前实现" ? C.paleGreen : C.paleBrown, status === "当前实现" ? C.green : C.brown, status === "当前实现" ? "#BCD8C5" : "#E5CE9E", 17);
  slide.shapes.add({ geometry: "line", position: { left: 58, top: 145, width: 1164, height: 0 }, fill: "none", line: { style: "solid", fill: C.faint, width: 1 } });
}

function addFooter(slide, page) {
  addText(slide, "PRISM 技术模块", 58, 680, 220, 22, { size: 14, color: C.muted, insets: { top: 0, right: 0, bottom: 0, left: 0 } });
  addText(slide, "ADVISORY_ONLY", 940, 680, 200, 22, { size: 14, bold: true, color: C.brown, align: "right", insets: { top: 0, right: 0, bottom: 0, left: 0 } });
  addText(slide, String(page).padStart(2, "0"), 1160, 680, 60, 22, { size: 14, bold: true, color: C.navy, align: "right", insets: { top: 0, right: 0, bottom: 0, left: 0 } });
}

function addImage(slide, bytes, x, y, w, h, crop = undefined, alt = "PRISM product screenshot") {
  const frame = addShape(slide, x - 4, y - 4, w + 8, h + 8, C.white, "#CED9DE", 18);
  frame.shadow = "shadow-sm";
  const image = slide.images.add({
    blob: bytes,
    contentType: "image/png",
    alt,
    fit: "cover",
    position: { left: x, top: y, width: w, height: h },
    geometry: "roundRect",
    borderRadius: 14,
    ...(crop ? { crop } : {}),
  });
  return image;
}

function setNotes(slide, text, sources) {
  slide.speakerNotes.textFrame.setText(`${text}\n\n资料依据：\n${sources.map((s) => `- ${s}`).join("\n")}`);
  slide.speakerNotes.setVisible(true);
}

function moduleBox(slide, text, x, y, w, h, palette = "blue", opts = {}) {
  const palettes = {
    blue: [C.paleBlue, C.blue, "#C8DCE5"],
    orange: [C.paleOrange, C.orange, "#F1C5B1"],
    green: [C.paleGreen, C.green, "#C8DDCD"],
    teal: [C.paleTeal, C.teal, "#B7DCDA"],
    gray: [C.gray, C.darkGray, "#D6D9D8"],
    brown: [C.paleBrown, C.brown, "#E3CFA3"],
    red: [C.paleRed, C.red, "#EBC4BD"],
  };
  const [fill, color, line] = palettes[palette];
  const box = addShape(slide, x, y, w, h, fill, line, opts.radius ?? 16);
  addText(slide, text, x + 4, y + 3, w - 8, h - 6, { size: opts.size ?? 21, bold: opts.bold ?? true, color, align: opts.align ?? "center", valign: "middle", insets: { top: 4, right: 8, bottom: 4, left: 8 } });
  return box;
}

const presentation = Presentation.create({ slideSize: { width: W, height: H } });

// Slide 1
{
  const s = presentation.slides.add();
  addHeader(s, 1, "整体架构", "系统总体分层架构", "语言模型负责理解与表达，金融数值和建议资格由确定性模块裁决");

  const lane1 = addShape(s, 58, 168, 1164, 120, C.paleBlue, "#C7DAE3", 20);
  const lane2 = addShape(s, 58, 304, 1164, 156, C.paleOrange, "#EFC7B6", 20);
  const lane3 = addShape(s, 58, 476, 1164, 146, C.paleGreen, "#C6DDCC", 20);
  addPill(s, "交互与任务层", 76, 180, 168, C.navy, C.white, C.navy, 18);
  addPill(s, "研究与计算层", 76, 316, 168, C.orange, C.white, C.orange, 18);
  addPill(s, "验证与交付层", 76, 488, 168, C.green, C.white, C.green, 18);

  const a1 = moduleBox(s, "用户输入", 278, 204, 132, 58, "blue");
  const a2 = moduleBox(s, "静态工作台", 438, 204, 152, 58, "blue");
  const a3 = moduleBox(s, "FastAPI\nHTTP / SSE", 620, 196, 158, 74, "gray", { size: 19 });
  const a4 = moduleBox(s, "LLM\n意图 / 槽位 / 解释", 810, 190, 188, 86, "orange", { size: 19 });
  const a5 = moduleBox(s, "结构化输入", 1042, 204, 142, 58, "blue");
  [ [a1,a2], [a2,a3], [a3,a4], [a4,a5] ].forEach(([a,b]) => connect(s,a,b));
  addPill(s, "不可直接生成金融事实", 802, 164, 204, C.paleRed, C.red, "#E9C0B8", 16);

  const b1 = moduleBox(s, "SkillHub 与\n数据 Provider", 278, 350, 166, 70, "blue", { size: 19 });
  const b2 = moduleBox(s, "有界 DAG\n研究矩阵", 476, 350, 156, 70, "gray", { size: 19 });
  const b3 = moduleBox(s, "证据与来源\n一致性校验", 664, 350, 178, 70, "green", { size: 19 });
  const b4 = moduleBox(s, "确定性金融计算", 882, 350, 210, 70, "orange");
  [ [b1,b2], [b2,b3], [b3,b4] ].forEach(([a,b]) => connect(s,a,b,{color:C.orange}));
  addText(s, "金额　权重　穿透暴露　HHI　风险预算　整手数量　费用　现金约束", 286, 426, 806, 26, { size: 17, bold: true, color: C.orange, align: "center", insets: { top: 0, right: 0, bottom: 0, left: 0 } });
  connect(s, a5, b2, { fromSide: "bottom", toSide: "top", kind: "elbow", color: C.blue });

  const c1 = moduleBox(s, "风险闸门", 300, 526, 166, 60, "orange");
  const c2 = moduleBox(s, "合规闸门", 516, 526, 166, 60, "green");
  const c3 = moduleBox(s, "DecisionReceipt", 746, 526, 198, 60, "blue", { size: 19 });
  const c4 = moduleBox(s, "DecisionEvent\n审计回放", 990, 516, 176, 80, "gray", { size: 19 });
  connect(s, b4, c1, { fromSide: "bottom", toSide: "top", kind: "elbow", color: C.orange });
  connect(s, b3, c2, { fromSide: "bottom", toSide: "top", kind: "elbow", color: C.green });
  connect(s, c1, c3, { color: C.orange });
  connect(s, c2, c3, { color: C.green });
  connect(s, c3, c4, { color: C.blue });
  addPill(s, "双 PASS 才生成正式建议", 508, 598, 272, C.white, C.green, "#AFCFBA", 17);
  addFooter(s, 1);
  setNotes(s,
    "这一页先讲清系统的责任边界。用户通过工作台或对话入口提出问题，LLM只负责识别意图、提取槽位和生成解释。只有经过确认的结构化输入，才能进入研究与计算层。金融数据由Provider取得，研究任务由有界DAG调度，金额、权重、暴露、HHI和调仓数量全部由确定性模块计算。最后风险闸门和合规闸门独立审查，只有双重通过才形成DecisionReceipt，并保存DecisionEvent用于复核。",
    ["docs/submission/technical-report.md 第3章", "README.md 处理链路与职责边界", "app/service/advisor_query.py", "app/gates/ 与 app/recommendation/"]
  );
}

// Slide 2
{
  const s = presentation.slides.add();
  addHeader(s, 2, "整体架构", "前后端技术栈与环境", "模块化单体降低竞赛部署成本，清晰接口为后续拆分保留边界");
  const stations = [
    ["浏览器工作台", "原生 HTML / CSS / JS\nHash 路由", "blue"],
    ["交互与可视化", "SSE 流式输出\nAntV X6 / Charts", "teal"],
    ["服务端接口", "FastAPI / Pydantic\nUvicorn", "orange"],
    ["确定性领域", "Python Decimal\n规则与状态机", "green"],
    ["数据与存储", "SQLite / PostgreSQL\nSkillHub / Fuyao", "gray"],
  ];
  const boxes = [];
  stations.forEach((st, i) => {
    const x = 58 + i * 232;
    const box = addShape(s, x, 184, 204, 126, i === 2 ? C.paleOrange : i === 3 ? C.paleGreen : i === 1 ? C.paleTeal : i === 4 ? C.gray : C.paleBlue, i === 2 ? "#EEC5B4" : "#CDD9DD", 18);
    addText(s, st[0], x + 12, 195, 180, 34, { size: 21, bold: true, color: i === 2 ? C.orange : i === 3 ? C.green : i === 1 ? C.teal : C.navy, align: "center" });
    addText(s, st[1], x + 14, 232, 176, 62, { size: 18, color: C.ink, align: "center" });
    boxes.push(box);
    if (i > 0) connect(s, boxes[i - 1], box, { color: i === 2 ? C.orange : C.blue });
  });
  addPill(s, "Python 3.11 / 3.12", 58, 326, 190, C.white, C.navy, "#CCD9DF", 16);
  addPill(s, "RapidOCR", 262, 326, 122, C.white, C.navy, "#CCD9DF", 16);
  addPill(s, "9 项问财 Skill", 398, 326, 160, C.white, C.orange, "#EBC1AF", 16);
  addPill(s, "iFinD 兼容注入", 572, 326, 174, C.white, C.brown, "#DFC99E", 16);
  addPill(s, "同源部署", 760, 326, 128, C.white, C.teal, "#B9DAD8", 16);

  addShape(s, 58, 384, 420, 234, C.navy, C.navy, 20);
  addText(s, "模块化单体", 82, 402, 250, 40, { size: 28, bold: true, color: C.white });
  addText(s, "接口层、应用服务、研究证据、确定性计算和存储位于同一进程，但通过领域契约隔离。", 82, 452, 362, 78, { size: 21, color: "#EAF2F5", valign: "top" });
  addPill(s, "低部署复杂度", 82, 548, 160, "#294F68", C.white, "#53758B", 16);
  addPill(s, "可测试边界", 258, 548, 144, "#294F68", C.white, "#53758B", 16);
  addImage(s, imageBytes.swagger, 514, 386, 708, 232, { left: 0.02, top: 0.0, right: 0.02, bottom: 0.68 }, "Prism FastAPI OpenAPI routes");
  addPill(s, "真实 API 路由证据", 968, 570, 224, C.paleGreen, C.green, "#BDD7C4", 16);
  addFooter(s, 2);
  setNotes(s,
    "前端没有引入庞大的SPA框架，而是使用原生HTML、CSS和JavaScript，通过Hash路由组织页面，SSE提供流式对话，AntV X6承载工作流画布，Lightweight Charts负责行情图。后端使用FastAPI、Pydantic和Uvicorn，金融计算统一使用Decimal。默认存储是SQLite，也提供PostgreSQL适配。右侧是真实OpenAPI路由截图，证明系统不是概念架构，而是具备完整接口边界的可运行模块化单体。",
    ["pyproject.toml", "package.json", "app/api/main.py", "docs/showcase/backend_api_full_architecture.png"]
  );
}

// Slide 3
{
  const s = presentation.slides.add();
  addHeader(s, 3, "嵌入集成", "与同花顺 SkillHub 平台集成方案", "复用底层金融数据与模型能力，在上层补齐个性化决策闭环");
  addText(s, "目标交付入口", 64, 170, 170, 32, { size: 20, bold: true, color: C.brown });
  const app1 = moduleBox(s, "问财 APP", 270, 164, 210, 62, "brown");
  const app2 = moduleBox(s, "iFinD 机构工作台", 546, 164, 244, 62, "brown");
  const app3 = moduleBox(s, "外部 API 调用方", 856, 164, 244, 62, "brown");
  addPill(s, "虚线表示目标嵌入", 1030, 126, 190, C.paleBrown, C.brown, "#E1CCA0", 15);

  const prism = addShape(s, 150, 278, 980, 172, C.navy, C.navy, 24);
  addText(s, "PRISM 智能体应用层", 178, 290, 320, 38, { size: 28, bold: true, color: C.white });
  const features = ["画像编译", "证据校验", "穿透与 HHI", "序贯再平衡", "双闸门与回执"];
  features.forEach((f, i) => addPill(s, f, 176 + i * 184, 352, 164, i === 4 ? "#345B46" : "#294F68", C.white, i === 4 ? "#6E9A7D" : "#53758B", 16));
  addText(s, "不改造 SkillHub 底层，通过 API 与模块化适配器接入", 178, 402, 770, 28, { size: 18, color: "#DCE8ED" });

  addText(s, "平台与数据底座", 64, 500, 170, 32, { size: 20, bold: true, color: C.blue });
  const base1 = moduleBox(s, "问财 SkillHub\n九项官方 Skill", 246, 480, 224, 92, "blue", { size: 19 });
  const base2 = moduleBox(s, "HithinkGPT /\n兼容 OpenAI 模型", 518, 480, 244, 92, "orange", { size: 19 });
  const base3 = moduleBox(s, "iFinD 兼容适配器\n显式注入", 810, 480, 224, 92, "gray", { size: 19 });
  addPill(s, "公告　新闻　研报　行情　财务　行业　宏观　基金　转债", 246, 590, 788, C.white, C.blue, "#C9DAE2", 16);
  [app1, app2, app3].forEach((app, i) => connect(s, prism, app, { fromSide: "top", toSide: "bottom", kind: "elbow", color: C.brown, style: "dashed" }));
  [base1, base2, base3].forEach((base) => connect(s, base, prism, { fromSide: "top", toSide: "bottom", kind: "elbow", color: C.blue }));
  addPill(s, "Bearer 鉴权", 1050, 492, 150, C.paleBlue, C.blue, "#C6DAE3", 15);
  addPill(s, "四态结果", 1050, 532, 150, C.paleGreen, C.green, "#C4DCCB", 15);
  addFooter(s, 3);
  setNotes(s,
    "这一页区分当前实现和目标嵌入。底层的问财SkillHub已经通过项目内九项版本化Skill清单接入，公告、新闻和研报走综合搜索接口，结构化金融查询走query2data。PRISM不改造平台底层，而是在上层增加画像编译、证据校验、组合计算、再平衡和双闸门。上方问财APP、iFinD机构工作台和外部API属于交付入口，因此使用虚线表示目标嵌入，不把尚未完成的平台内上线表述为现状。",
    ["docs/iwencai-live-provider.md", "app/providers/skillhub.py", "app/providers/iwencai_skills.json", "docs/submission/technical-report.md 第3.4节"]
  );
}

// Slide 4
{
  const s = presentation.slides.add();
  addHeader(s, 4, "嵌入集成", "部署与交付形态", "同一套业务规则支持单机演示与生产化存储配置", "部署方案");
  addPill(s, "演示环境", 78, 170, 160, C.navy, C.white, C.navy, 19);
  addPill(s, "生产落地目标", 684, 170, 190, C.brown, C.white, C.brown, 19);
  addPill(s, "当前可运行", 268, 170, 138, C.paleGreen, C.green, "#BBD6C3", 15);
  addPill(s, "需部署方补充基础设施", 892, 170, 250, C.paleBrown, C.brown, "#DFC99D", 15);

  const lx = 78, rx = 684;
  const l1 = moduleBox(s, "浏览器工作台", lx, 224, 214, 58, "blue");
  const l2 = moduleBox(s, "FastAPI 单进程", lx, 314, 214, 58, "orange");
  const l3 = moduleBox(s, "SQLite + WAL", lx, 404, 214, 58, "green");
  const l4 = moduleBox(s, "DPAPI 保护凭据", lx, 494, 214, 58, "gray");
  [ [l1,l2], [l2,l3], [l3,l4] ].forEach(([a,b]) => connect(s,a,b,{fromSide:"bottom",toSide:"top",kind:"straight"}));
  addText(s, "一键启动　离线回放　owner 隔离", 320, 330, 276, 84, { size: 22, bold: true, color: C.navy, fill: C.white, line: "#CBD9DF", radius: 16, align: "center" });

  const r1 = moduleBox(s, "反向代理 / 身份服务", rx, 224, 240, 58, "brown");
  const r2 = moduleBox(s, "FastAPI 实例", rx, 314, 240, 58, "orange");
  const r3 = moduleBox(s, "PostgreSQL", rx, 404, 240, 58, "green");
  const r4 = moduleBox(s, "监控 / 限流 / 审计", rx, 494, 240, 58, "gray");
  [ [r1,r2], [r2,r3], [r3,r4] ].forEach(([a,b]) => connect(s,a,b,{fromSide:"bottom",toSide:"top",kind:"straight",color:C.brown}));
  addText(s, "Provider 配额、权限、长期 SLA\n按实际部署单独验收", 958, 330, 256, 84, { size: 20, bold: true, color: C.brown, fill: C.white, line: "#E0C99A", radius: 16, align: "center" });

  addShape(s, 58, 586, 1164, 62, C.paleRed, "#E9C1BA", 18);
  addText(s, "统一运行边界", 78, 598, 160, 36, { size: 20, bold: true, color: C.red });
  addText(s, "仅输出分析建议与测算　不连接券商账户　不生成订单　不执行交易", 250, 598, 790, 36, { size: 21, bold: true, color: C.red, align: "center" });
  addPill(s, "ADVISORY_ONLY", 1052, 600, 152, C.red, C.white, C.red, 16);
  addFooter(s, 4);
  setNotes(s,
    "项目提供两类部署形态。演示环境是当前可运行的单机模式，浏览器与FastAPI同源部署，SQLite使用WAL，凭据在Windows下通过DPAPI保护，并按owner隔离数据。生产落地可以替换为PostgreSQL，并在前方接入身份服务、反向代理、限流和监控。后者是部署目标，不把公网身份、长期监控或99.9%可用性描述为已完成。无论采用哪种部署，系统都保持Advisory Only，不接管账户和交易。",
    ["docs/local-deployment.md", "docs/adr/0001-modular-monolith.md", "app/store/sqlite.py", "app/store/postgres.py", "README.md 当前边界"]
  );
}

// Slide 5
{
  const s = presentation.slides.add();
  addHeader(s, 5, "工作链路", "完整业务工作总链路", "画像、持仓、证据、闸门和回执使用同一用户归属与版本关系");
  const steps = [
    ["01", "注册与归属"], ["02", "19 题问卷"], ["03", "八维画像\nC1-C5"], ["04", "持仓导入\nOCR / 文本"],
    ["05", "意图与计划"], ["06", "DAG 研究"], ["07", "证据校验"], ["08", "双闸门"], ["09", "报告与回执"],
  ];
  const nodes = [];
  steps.forEach((st, i) => {
    const x = 62 + i * 128;
    const circle = s.shapes.add({ geometry: "ellipse", position: { left: x, top: 204, width: 52, height: 52 }, fill: i < 4 ? C.navy : i < 7 ? C.orange : C.green, line: { style: "solid", fill: C.white, width: 2 } });
    addText(s, st[0], x, 204, 52, 52, { size: 17, bold: true, color: C.white, align: "center", insets: { top: 0, right: 0, bottom: 0, left: 0 } });
    addText(s, st[1], x - 24, 264, 100, 58, { size: 17, bold: true, color: i < 4 ? C.navy : i < 7 ? C.orange : C.green, align: "center", valign: "top" });
    nodes.push(circle);
    if (i > 0) connect(s, nodes[i - 1], circle, { color: i < 4 ? C.blue : i < 7 ? C.orange : C.green });
  });
  addPill(s, "VERSIONED PROFILE", 76, 346, 222, C.paleBlue, C.navy, "#C8D9E1", 17);
  addPill(s, "VERIFIED EVIDENCE", 322, 346, 226, C.paleGreen, C.green, "#C1DAC7", 17);
  addPill(s, "DECISION RECEIPT", 572, 346, 224, C.paleOrange, C.orange, "#EBC3B1", 17);

  addShape(s, 58, 402, 560, 226, C.white, "#CCD9DE", 20);
  addText(s, "一次问题的闭环", 82, 420, 230, 34, { size: 24, bold: true, color: C.navy });
  addText(s, "“我想控制回撤，这套持仓需要怎么调整？”", 82, 466, 492, 42, { size: 24, bold: true, color: C.ink, fill: C.paleBlue, line: "#CADCE4", radius: 14, align: "center" });
  addText(s, "每条建议绑定画像版本、持仓快照、研究结果、证据引用、闸门状态和失效条件。", 82, 526, 492, 66, { size: 20, color: C.muted, valign: "top" });
  addImage(s, imageBytes.workbench, 648, 402, 574, 226, { left: 0.10, top: 0.05, right: 0.02, bottom: 0.52 }, "PRISM investor workbench showing profile and risk boundary");
  addPill(s, "真实工作台", 1042, 586, 152, C.paleGreen, C.green, "#BBD6C3", 15);
  addFooter(s, 5);
  setNotes(s,
    "用一个具体问题贯穿这条链路。用户先完成注册和归属确认，再通过19题问卷生成八维画像与C1到C5适当性等级。持仓可以通过文本或截图OCR导入，低置信内容必须确认。系统把问题转为研究计划，由DAG执行专业节点，再把Provider结果转成Evidence、Fact和Finding。风险与合规双闸门通过后，才输出带来源和失效条件的报告与回执。右下角是真实工作台，画像边界和持仓状态在同一页面呈现。",
    ["docs/submission/competition-technical-solution.md 第3章与第5章", "app/profile/questionnaire.py", "app/portfolio/", "app/research/", "docs/showcase/01_v3_investor_workbench_overview.png"]
  );
}

// Slide 6
{
  const s = presentation.slides.add();
  addHeader(s, 6, "工作链路", "AI 对话多轮交互链路", "先锁定分析前提，再允许模型调用金融工具");
  addText(s, "分层记忆", 64, 174, 160, 28, { size: 20, bold: true, color: C.navy });
  const m1 = moduleBox(s, "短期\n消息窗口", 68, 214, 158, 72, "blue", { size: 19 });
  const m2 = moduleBox(s, "中期\n会话事实 + revision", 68, 310, 158, 84, "teal", { size: 18 });
  const m3 = moduleBox(s, "长期\n显式结构化记忆", 68, 418, 158, 84, "gray", { size: 18 });
  addPill(s, "HISTORICAL_ONLY", 68, 522, 158, C.paleBrown, C.brown, "#DFC99F", 14);

  const lock = s.shapes.add({ geometry: "ellipse", position: { left: 332, top: 274, width: 230, height: 230 }, fill: C.navy, line: { style: "solid", fill: "#7FA0B3", width: 3 } });
  addText(s, "会话前提锁", 356, 306, 182, 44, { size: 27, bold: true, color: C.white, align: "center" });
  addText(s, "画像版本\n持仓版本\n数据模式\nSHA-256 fingerprint", 364, 356, 166, 104, { size: 18, color: "#E7F0F4", align: "center" });
  [m1,m2,m3].forEach((m) => connect(s, m, lock, { color: C.blue }));
  addPill(s, "expected_revision", 350, 520, 196, C.paleBlue, C.navy, "#C6D9E2", 15);
  addPill(s, "DRIFT_DETECTED", 350, 560, 196, C.paleRed, C.red, "#E8C1BA", 15);

  addText(s, "工具路由", 626, 174, 150, 28, { size: 20, bold: true, color: C.orange });
  const r1 = moduleBox(s, "普通交流\n语言模型回答", 624, 214, 190, 72, "gray", { size: 19 });
  const r2 = moduleBox(s, "金融查询\nProvider + 证据", 624, 322, 190, 72, "green", { size: 19 });
  const r3 = moduleBox(s, "持仓测算\n确定性工具", 624, 430, 190, 72, "orange", { size: 19 });
  [r1,r2,r3].forEach((r) => connect(s, lock, r, { color: r === r3 ? C.orange : C.blue }));
  const out = moduleBox(s, "SSE 流式回复\n来源与状态同时输出", 624, 548, 190, 72, "blue", { size: 18 });
  [r1,r2,r3].forEach((r) => connect(s, r, out, { fromSide: "bottom", toSide: "top", kind: "elbow", color: r === r3 ? C.orange : C.blue }));
  addImage(s, imageBytes.currentWorkbench, 860, 188, 362, 432, { left: 0.14, top: 0.03, right: 0.01, bottom: 0.03 }, "Current PRISM AI conversation workbench");
  addPill(s, "对话入口共享同一画像与持仓", 894, 576, 294, C.paleGreen, C.green, "#BED8C5", 14);
  addFooter(s, 6);
  setNotes(s,
    "多轮对话最重要的不是记得更多，而是避免旧状态污染新计算。系统把短期消息窗口、中期会话事实和长期显式记忆分开。进行金融分析前，服务端锁定画像版本、持仓版本和数据模式，并计算SHA-256指纹。请求必须携带预期修订号，发现漂移后停止沿用旧结论。普通交流可以直接由模型回答，金融查询必须进入Provider和证据链，持仓测算必须进入确定性工具。最终通过SSE流式返回内容、来源与状态。",
    ["app/service/session_truth.py", "app/service/semantic_memory.py", "docs/archive/context-memory.md", "app/api/main.py /api/v1/copilot/chat", "docs/showcase/current-pages-snapshot-workbench-20260917.png"]
  );
}

// Slide 7
{
  const s = presentation.slides.add();
  addHeader(s, 7, "工作链路", "持仓分析与再平衡工作链路", "目标权重必须转换为可交易股数，并通过交易后完整复核");
  addText(s, "诊断漏斗", 66, 172, 160, 30, { size: 21, bold: true, color: C.navy });
  const f1 = moduleBox(s, "持仓导入与确认", 68, 214, 330, 54, "blue");
  const f2 = moduleBox(s, "基金 / ETF 穿透暴露", 98, 282, 300, 54, "teal");
  const f3 = moduleBox(s, "HHI 与画像风险预算", 128, 350, 270, 54, "green");
  const f4 = moduleBox(s, "识别超限项与目标权重", 158, 418, 240, 54, "orange", { size: 19 });
  [ [f1,f2], [f2,f3], [f3,f4] ].forEach(([a,b]) => connect(s,a,b,{fromSide:"bottom",toSide:"top",kind:"straight",color:C.orange}));

  addText(s, "执行阶梯", 454, 172, 160, 30, { size: 21, bold: true, color: C.orange });
  const x0 = 454, y0 = 230;
  const exec = [
    ["0.50% 死区", "gray"], ["先卖后买", "orange"], ["100 股整手", "blue"], ["费用与现金", "teal"], ["交易后体检", "green"],
  ];
  let prev = null;
  exec.forEach((item, i) => {
    const box = moduleBox(s, item[0], x0 + i * 58, y0 + i * 70, 150, 50, item[1], { size: 18 });
    if (prev) connect(s, prev, box, { fromSide: "bottom", toSide: "left", kind: "elbow", color: C.orange });
    prev = box;
  });
  addPill(s, "Decimal 算术", 80, 512, 154, C.white, C.navy, "#CCD9DF", 15);
  addPill(s, "二分求可承受买入手数", 248, 512, 246, C.white, C.orange, "#E8C2B0", 15);
  addPill(s, "印花税 / 过户费 / 佣金", 80, 554, 234, C.white, C.teal, "#B9DAD8", 15);
  addPill(s, "换手上限 / 现金下限", 330, 554, 210, C.white, C.green, "#BFD8C5", 15);
  addImage(s, imageBytes.rebalance, 870, 246, 352, 264, { left: 0.08, top: 0.10, right: 0.02, bottom: 0.44 }, "PRISM rebalancing execution stepper");
  addPill(s, "真实执行步骤：SELL、SELL、BUY", 900, 530, 292, C.paleGreen, C.green, "#BDD7C4", 14);
  addPill(s, "序贯确定性求解", 938, 574, 218, C.paleOrange, C.orange, "#EBC2B0", 15);
  addFooter(s, 7);
  setNotes(s,
    "持仓分析先做数据确认，再把基金和ETF穿透到底层资产和行业，计算HHI，并与当前画像的风险预算比较。识别超限项后，系统生成目标权重，但不会停留在金额层。它先过滤0.50%的小偏差，严格先卖后买，再按100股整手、有效报价、印花税、过户费、佣金和现金下限计算可执行数量。买入手数使用二分法寻找可承受最大值。最后重新构造交易后组合并执行完整体检。这个算法是序贯确定性求解，不宣称全局最优。",
    ["app/service/portfolio_rebalancing.py", "app/rebalancing/contracts.py", "docs/portfolio-analysis-agent.md", "docs/showcase/04_v3_rebalancing_plan_stepper.png"]
  );
}

// Slide 8
{
  const s = presentation.slides.add();
  addHeader(s, 8, "自研算法", "自研算法① 画像、风险与证据验证", "画像转换为约束，事实升级依赖独立来源");
  addPill(s, "01 画像条件化风险预算映射", 64, 170, 334, C.navy, C.white, C.navy, 17);
  addPill(s, "02 来源等价类证据验证", 676, 170, 310, C.green, C.white, C.green, 17);

  const q = moduleBox(s, "19 题问卷", 72, 230, 142, 54, "blue");
  const dims = ["风险承受", "投资经验", "操作活跃", "研究习惯", "信息投入", "AI 信任", "个性需求", "辅助需求"];
  dims.forEach((d, i) => addPill(s, d, 224 + (i % 2) * 124, 216 + Math.floor(i / 2) * 48, 112, C.white, i < 2 ? C.navy : C.teal, i < 2 ? "#C9D9E1" : "#BBD9D7", 13));
  const c15 = moduleBox(s, "C1-C5\n适当性展示", 488, 230, 126, 70, "orange", { size: 17 });
  const tiers = moduleBox(s, "内部规则层\nCONSERVATIVE\nBALANCED\nGROWTH", 460, 330, 154, 118, "gray", { size: 13 });
  const budget = moduleBox(s, "风险预算\n资产 / 行业 / 科技\n未分类上限", 476, 478, 138, 104, "green", { size: 16 });
  connect(s, q, c15, { color: C.orange });
  connect(s, c15, tiers, { fromSide: "bottom", toSide: "top", kind: "straight", color: C.orange });
  connect(s, tiers, budget, { fromSide: "bottom", toSide: "top", kind: "straight", color: C.green });
  addImage(s, imageBytes.profile, 72, 444, 314, 140, { left: 0.20, top: 0.12, right: 0.20, bottom: 0.08 }, "PRISM profile and risk-control constraints modal");

  const e1 = moduleBox(s, "记录 A1\nlineage-A", 686, 230, 150, 60, "blue", { size: 17 });
  const e2 = moduleBox(s, "记录 A2\nlineage-A", 686, 316, 150, 60, "blue", { size: 17 });
  const e3 = moduleBox(s, "记录 B1\nlineage-B", 686, 402, 150, 60, "teal", { size: 17 });
  const dedupe = moduleBox(s, "按 lineage\n去重", 884, 286, 132, 72, "gray", { size: 18 });
  const validate = moduleBox(s, "独立来源\n一致性验证", 884, 404, 132, 72, "green", { size: 18 });
  [e1,e2].forEach((e) => connect(s,e,dedupe,{color:C.blue}));
  connect(s, e3, validate, { color: C.teal });
  connect(s, dedupe, validate, { fromSide: "bottom", toSide: "top", kind: "straight", color: C.green });
  const states = [
    ["SUPPORTED", C.paleGreen, C.green], ["CONTRADICTED", C.paleRed, C.red],
    ["UNRESOLVED", C.paleBrown, C.brown], ["INSUFFICIENT", C.gray, C.darkGray],
  ];
  states.forEach((st, i) => addPill(s, st[0], 1050, 226 + i * 68, 170, st[1], st[2], st[2], 14));
  addText(s, "同一来源重复记录只计一次\n至少两个独立 lineage 才能形成支持", 684, 510, 536, 70, { size: 20, bold: true, color: C.green, fill: C.white, line: "#BDD7C4", radius: 16, align: "center" });
  addFooter(s, 8);
  setNotes(s,
    "第一组算法把19题问卷转为八个0到100分维度，并形成C1到C5适当性展示。为了兼容当前确定性闸门，系统再把有效画像编译为保守、平衡和成长三档内部规则，并生成单一资产、行业、科技行业和未分类暴露上限。第二组算法解决多智能体重复同一信息的问题。验证器只认可显式lineage，同一来源的多条记录先去重，至少两个独立来源一致，事实才进入SUPPORTED。来源冲突或数据不足会保留为复核状态，不用多数票掩盖分歧。",
    ["app/profile/questionnaire.py", "app/profile/behavior.py", "app/profile/presentation.py", "app/risk/budget.py", "app/research/cross_validation.py", "docs/showcase/current-pages-snapshot-profile-20260917.png"]
  );
}

// Slide 9
{
  const s = presentation.slides.add();
  addHeader(s, 9, "自研算法", "自研算法② 组合计算与任务调度", "穿透计算保持守恒，研究调度具有节点预算与总预算");
  addPill(s, "03 穿透暴露矩阵与 HHI", 64, 170, 286, C.orange, C.white, C.orange, 17);
  addPill(s, "04 时间预算约束 DAG", 684, 170, 272, C.navy, C.white, C.navy, 17);

  const h1 = moduleBox(s, "股票持仓\n100% 归属", 70, 236, 154, 72, "blue", { size: 18 });
  const h2 = moduleBox(s, "基金 / ETF\n按披露比例拆分", 70, 336, 154, 80, "teal", { size: 17 });
  const h3 = moduleBox(s, "未披露残值\n保留为未分类", 70, 446, 154, 80, "gray", { size: 17 });
  const sectors = [
    moduleBox(s, "新能源", 330, 226, 150, 52, "orange"),
    moduleBox(s, "半导体", 390, 310, 150, 52, "orange"),
    moduleBox(s, "其他行业", 330, 394, 150, 52, "green"),
    moduleBox(s, "UNCLASSIFIED", 390, 478, 170, 52, "gray", { size: 16 }),
  ];
  connect(s,h1,sectors[0],{color:C.orange});
  connect(s,h1,sectors[2],{color:C.green});
  connect(s,h2,sectors[0],{color:C.orange});
  connect(s,h2,sectors[1],{color:C.orange});
  connect(s,h2,sectors[2],{color:C.green});
  connect(s,h3,sectors[3],{color:C.darkGray});
  addText(s, "E_g = Σ v_i w_i,g", 82, 560, 220, 36, { size: 23, bold: true, color: C.orange, fill: C.white, line: "#E9C2B0", radius: 14, align: "center" });
  addText(s, "HHI = 10000 Σ(E_g/V)²", 320, 560, 290, 36, { size: 23, bold: true, color: C.orange, fill: C.white, line: "#E9C2B0", radius: 14, align: "center" });
  addPill(s, "直接 + 穿透 + 未分类 = 组合总值", 160, 612, 380, C.paleGreen, C.green, "#BDD8C5", 15);

  const plan = moduleBox(s, "研究计划\n固定拓扑与总预算", 702, 230, 190, 70, "blue", { size: 18 });
  const macro = moduleBox(s, "宏观节点\nREADY", 670, 344, 144, 62, "teal", { size: 17 });
  const industry = moduleBox(s, "行业节点\nREADY", 834, 344, 144, 62, "teal", { size: 17 });
  const stock = moduleBox(s, "个股节点\nWAIT", 998, 344, 144, 62, "gray", { size: 17 });
  const fund = moduleBox(s, "基金节点\nOPTIONAL", 834, 446, 144, 62, "brown", { size: 16 });
  const val = moduleBox(s, "证据校验\nCOMPLETE / PARTIAL", 1010, 446, 176, 70, "green", { size: 16 });
  connect(s, plan, macro, { fromSide: "bottom", toSide: "top", kind: "elbow" });
  connect(s, plan, industry, { fromSide: "bottom", toSide: "top", kind: "elbow" });
  connect(s, plan, stock, { fromSide: "bottom", toSide: "top", kind: "elbow" });
  connect(s, industry, fund, { fromSide: "bottom", toSide: "top", kind: "elbow", color: C.brown });
  connect(s, macro, val, { fromSide: "bottom", toSide: "left", kind: "elbow", color: C.green });
  connect(s, industry, val, { fromSide: "bottom", toSide: "left", kind: "elbow", color: C.green });
  connect(s, stock, val, { fromSide: "bottom", toSide: "top", kind: "elbow", color: C.green });
  connect(s, fund, val, { color: C.green });
  addPill(s, "节点 timeout", 690, 548, 146, C.paleBrown, C.brown, "#DFC99E", 15);
  addPill(s, "总 deadline", 850, 548, 146, C.paleRed, C.red, "#E9C0B8", 15);
  addPill(s, "取消向下传播", 1010, 548, 176, C.gray, C.darkGray, "#D1D5D4", 15);
  addText(s, "失败不会被静默改写为成功", 744, 604, 390, 34, { size: 20, bold: true, color: C.red, align: "center" });
  addFooter(s, 9);
  setNotes(s,
    "左侧算法解决基金表面分散、底层集中看不见的问题。股票直接按100%归属，基金和ETF按披露成分拆分，没有披露的残值必须保留为未分类，直接暴露、穿透暴露和未分类暴露严格闭合组合总值。HHI在权重取整前计算。右侧是有界DAG。研究计划提前固定拓扑、节点超时和总截止时间，依赖就绪的节点并行运行。必需节点失败会使运行失败，可选节点不完整只能降级为部分结果，取消和超时都显式传播。",
    ["app/portfolio/exposure.py", "app/risk/concentration.py", "app/orchestration/contracts.py", "app/orchestration/executor.py", "docs/archive/bounded-orchestration.md"]
  );
}

// Slide 10
{
  const s = presentation.slides.add();
  addHeader(s, 10, "自研算法", "自研算法③ 决策控制与会话记忆", "四项控制共同决定建议是否具备输出资格");
  const q1 = addShape(s, 70, 184, 470, 190, C.paleOrange, "#EDC4B2", 22);
  addPill(s, "05 离散交易约束再平衡", 88, 200, 286, C.orange, C.white, C.orange, 16);
  addText(s, "目标金额", 94, 252, 110, 42, { size: 18, bold: true, color: C.orange, fill: C.white, line: "#EBC2B0", radius: 12, align: "center" });
  addText(s, "整手股数", 246, 252, 110, 42, { size: 18, bold: true, color: C.orange, fill: C.white, line: "#EBC2B0", radius: 12, align: "center" });
  addText(s, "费用与现金", 398, 252, 122, 42, { size: 18, bold: true, color: C.orange, fill: C.white, line: "#EBC2B0", radius: 12, align: "center" });
  addText(s, "先卖后买，交易后重新计算风险", 94, 316, 420, 34, { size: 19, bold: true, color: C.orange, align: "center" });

  const q2 = addShape(s, 740, 184, 470, 190, C.paleGreen, "#C3DCC9", 22);
  addPill(s, "06 双闸门状态聚合", 758, 200, 244, C.green, C.white, C.green, 16);
  const g1 = moduleBox(s, "风险闸门", 774, 248, 122, 44, "orange", { size: 17 });
  const g2 = moduleBox(s, "合规闸门", 774, 310, 122, 44, "green", { size: 17 });
  const go = moduleBox(s, "双 PASS", 1040, 278, 130, 50, "blue", { size: 18 });
  connect(s,g1,go,{kind:"straight",color:C.orange}); connect(s,g2,go,{kind:"straight",color:C.green});
  addText(s, "优先级：BLOCKED > REVIEW_REQUIRED > PASS", 766, 336, 418, 24, { size: 14, bold: true, color: C.green, align: "center" });

  const q3 = addShape(s, 70, 408, 470, 190, C.paleBlue, "#C5D9E2", 22);
  addPill(s, "07 分层记忆与版本状态", 88, 424, 270, C.navy, C.white, C.navy, 16);
  addText(s, "短期消息", 94, 478, 118, 42, { size: 17, bold: true, color: C.navy, fill: C.white, line: "#C7D9E1", radius: 12, align: "center" });
  addText(s, "会话事实", 246, 478, 118, 42, { size: 17, bold: true, color: C.teal, fill: C.white, line: "#B9D9D7", radius: 12, align: "center" });
  addText(s, "显式记忆", 398, 478, 118, 42, { size: 17, bold: true, color: C.darkGray, fill: C.white, line: "#D0D5D4", radius: 12, align: "center" });
  addText(s, "revision + fingerprint 阻止旧状态进入新计算", 94, 542, 420, 34, { size: 18, bold: true, color: C.navy, align: "center" });

  const q4 = addShape(s, 740, 408, 470, 190, C.paleBrown, "#DFC99D", 22);
  addPill(s, "08 历史检索与受控恢复", 758, 424, 278, C.brown, C.white, C.brown, 16);
  const hs = moduleBox(s, "检索最近\n100 条显式保存", 766, 478, 154, 68, "gray", { size: 16 });
  const hc = moduleBox(s, "用户确认", 946, 486, 120, 52, "brown", { size: 17 });
  const hr = moduleBox(s, "恢复后\n清空旧派生结果", 1090, 478, 100, 68, "green", { size: 15 });
  connect(s,hs,hc,{color:C.brown}); connect(s,hc,hr,{color:C.green});
  addPill(s, "HISTORICAL_ONLY", 892, 554, 180, C.white, C.brown, "#D9C18E", 14);

  const center = s.shapes.add({ geometry: "ellipse", position: { left: 560, top: 316, width: 160, height: 160 }, fill: C.navy, line: { style: "solid", fill: C.white, width: 3 } });
  addText(s, "建议资格", 582, 348, 116, 42, { size: 25, bold: true, color: C.white, align: "center" });
  addText(s, "PASS 才输出", 582, 398, 116, 30, { size: 17, color: "#E4EDF1", align: "center" });
  [q1,q2,q3,q4].forEach((q, i) => connect(s, q, center, { fromSide: i < 2 ? "bottom" : "top", toSide: i % 2 === 0 ? "left" : "right", kind: "elbow", color: i === 0 ? C.orange : i === 1 ? C.green : i === 2 ? C.blue : C.brown }));
  [
    ["可复算", 210, C.orange], ["可追踪", 450, C.blue], ["可阻断", 690, C.red], ["可恢复", 930, C.green],
  ].forEach(([t,x,color]) => addPill(s, t, x, 624, 140, C.white, color, color, 17));
  addFooter(s, 10);
  setNotes(s,
    "最后一页把四项控制放在同一张图里。离散再平衡把目标金额转换为受整手、费用和现金约束的数量。双闸门独立审查风险与合规，状态聚合遵循阻断优先、复核其次、通过最后，只有双PASS才能输出正式建议。分层记忆用revision和指纹阻止旧状态进入新计算。历史记录检索始终标记为Historical Only，必须由用户确认恢复，恢复后还要清空旧的研究、优化和建议结果。四项机制共同保证结果可复算、过程可追踪、输出可阻断、历史可受控恢复。",
    ["app/service/portfolio_rebalancing.py", "app/gates/pipeline.py", "app/service/session_truth.py", "app/service/semantic_memory.py", "docs/archive/risk-compliance-gates.md", "docs/archive/context-memory.md"]
  );
}

const stagingDir = path.join(workspaceDir, ".codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const candidatePath = path.join(stagingDir, "prism-technical-candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);

const requirements = {
  explicitTotalSlideCount: 10,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  materializeLiteralChartWorkbooks: false,
};
const fontPolicy = {
  basis: "design",
  families: [FONT],
  scriptFonts: { ea: FONT },
};
const result = await finalizePresentation({
  ...requirements,
  workspaceDir,
  candidatePath,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  requiredNativeTableOwnerSlides: [],
  fontPolicy,
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "PRISM-技术模块-10页答辩版.validation.json"),
});

const finalDeck = await PresentationFile.importPptx(await FileBlob.load(FINAL_PPTX));
for (let i = 0; i < finalDeck.slides.items.length; i += 1) {
  const blob = await finalDeck.export({ slide: finalDeck.slides.items[i], format: "png", scale: 1.5 });
  await fs.writeFile(path.join(previewDir, `slide-${String(i + 1).padStart(2, "0")}.png`), new Uint8Array(await blob.arrayBuffer()));
}
const montage = await finalDeck.export({ format: "png", montage: true, scale: 0.55 });
await fs.writeFile(path.join(previewDir, "montage.png"), new Uint8Array(await montage.arrayBuffer()));

console.log(JSON.stringify({ final: FINAL_PPTX, previews: previewDir, validation: result }, null, 2));
