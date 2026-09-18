# Prism

> 同一市场，不同约束；每项分析都能追溯到计算与证据。

Prism 是面向同花顺 A18 赛题的个性化证券投顾智能体系统。系统将已确认的投资者画像、持仓资料、金融数据和研究任务组织为可复核的分析过程，由确定性程序完成金额、比例、风险与再平衡计算，并在建议输出前执行独立风险与合规审查。

[技术文档](docs/submission/competition-technical-solution.md) · [技术文档 PDF](docs/submission/Prism-技术文档-图形优化版.pdf) · [技术设计文档](docs/submission/technical-report.md) · [本地部署说明](docs/local-deployment.md)

![Prism 整体处理流程](docs/submission/figures/judge-01-processing-flow.png)

## 项目介绍

证券投资分析需要同时处理个人风险条件、账户持仓、市场资料和交易约束。Prism 通过统一工作台连接画像建立、证券研究、持仓分析、方案测算和结果复核，使开发者与使用者能够检查每项结果采用的输入、规则、来源和状态。

| 目标 | 输入 | 系统处理 | 输出 |
| --- | --- | --- | --- |
| 建立个人风险条件 | 正式问卷、用户确认信息 | 确定性评分、字段确认、版本保存 | 风险等级、预算上限、配置参考 |
| 识别组合风险 | 持仓、现金、报价、行业与基金成分 | 暴露聚合、穿透计算、集中度与预算比较 | 风险位置、观察值、适用阈值 |
| 核验证券研究依据 | 证券、主题、时间范围 | 专业任务调度、来源归类、口径校验 | 证据、事实、研究发现及问题记录 |
| 测算组合调整方案 | 当前组合、目标权重、报价 | 交易单位、费用、现金与调整后风险计算 | 数量、费用、现金变化及复核结果 |
| 判定建议资格 | 画像、研究、计算结果与披露 | 风险审查、合规审查、状态聚合 | `PASS`、`REVIEW_REQUIRED` 或 `BLOCKED` |

Prism 遵守以下工程原则：

- 金融事实保留来源、观察时间、单位、期间和质量状态；
- 金融金额、比例、数量与风险指标由 Python 领域模块计算；
- LLM 负责意图识别、字段提取、工具选择和自然语言说明；
- 缺失数据、空结果、查询失败和来源冲突分别记录；
- 画像版本与持仓版本共同构成个性化计算前提；
- 建议需要完整引用关系，并通过风险与合规审查；
- 系统提供研究与决策支持，不连接证券交易接口。

## 系统方案

### 系统职责

| 组成部分 | 输入 | 处理职责 | 输出 |
| --- | --- | --- | --- |
| 用户工作台 | 对话、问卷、持仓、文件与图片 | 输入确认、过程展示、结果回看 | 版本化用户上下文 |
| 任务协调 | 用户问题、可用能力与时间预算 | 研究计划、依赖校验、任务状态管理 | 专业任务及执行记录 |
| 专业研究 | 数据主题、查询范围与来源 | 查询、归一化、交叉验证 | 研究证据与发现 |
| 金融程序 | 画像、持仓、报价与目标 | 暴露、预算、配置、情景与再平衡计算 | 结构化计算报告 |
| 独立审查 | 研究、计算与候选建议 | 风险、归属、引用与披露检查 | 建议资格及决策回执 |
| 数据管理 | 用户资料、运行记录与版本 | 用户归属、持久化、恢复与审计 | SQLite 或 PostgreSQL 记录 |

### 总体架构

![Prism 系统总体架构](docs/submission/figures/judge-02-architecture.png)

后端采用模块化单体结构。接口层负责 HTTP、SSE、认证与字段校验；应用服务层协调画像、组合、研究和会话流程；领域模块执行确定性计算；数据提供方模块管理金融服务调用及状态；存储模块保存当前资料、历史记录和决策事件。

一次完整分析按照以下关系传递信息：

1. 读取当前账户已确认的画像、持仓和数据模式；
2. 识别分析目的并生成研究计划或工具请求；
3. 专业研究任务按照依赖关系执行，结果进入证据校验；
4. 金融程序计算暴露、集中度、风险预算、配置边界和调整结果；
5. 风险与合规模块分别检查建议条件；
6. 具备资格的结果生成 `Recommendation`、`DecisionReceipt` 和 `DecisionEvent`；
7. 工作台展示结果、数据状态、引用关系和需要复核的原因。

### 证据与决策关系

| 对象 | 主要内容 | 生成条件 | 后续用途 |
| --- | --- | --- | --- |
| `Evidence` | 来源、主体、指标、单位、期间、观察值与质量状态 | 数据提供方结果经过字段与状态校验 | 支持或反对结构化声明 |
| `Fact` | 已验证的结构化事实 | 口径一致，独立来源数量及冲突条件满足规则 | 形成研究发现 |
| `Finding` | 对事实的研究判断 | 引用有效事实并保留严重程度与适用条件 | 支持建议候选 |
| `Recommendation` | 适用于当前画像与组合的建议 | 引用闭合，风险与合规审查满足资格条件 | 生成决策回执 |
| `DecisionReceipt` | 输入版本、规则版本、依据与内容哈希 | 建议组合完成确定性复核 | 保存、回看和审计 |

## 产品功能

### 投资任务工作台

![投资任务工作台](docs/showcase/current-pages-snapshot-workbench-20260917.png)

工作台提供自然语言入口，并关联当前已确认画像与持仓。对话接口通过 SSE 返回分析上下文、工具执行进度和回答内容；涉及金融事实或个人组合计算的问题需要调用结构化工具。组合体检、标的研究、方案测算和历史记录均可进入相应页面继续处理。

### 投资者画像

![投资者画像](docs/showcase/current-pages-snapshot-profile-20260917.png)

正式风险问卷包含 19 个问题。服务端按照固定权重计算风险分数，将结果映射为保守型、均衡型或成长型画像，并生成单一资产、行业、科技行业及未分类暴露的预算上限。自然语言产生的画像字段需要经过用户确认，画像修订号参与后续计算。

### 持仓分析与组合报告

![持仓分析与组合报告](docs/showcase/current-pages-snapshot-portfolio-20260917.png)

持仓可以通过表单、文本或图片识别形成草稿，用户确认后保存为当前组合。报告计算证券市值、现金、总资产、直接及穿透暴露、集中度、画像预算差额和数据质量，并为每项检查同时展示观察值、适用阈值与判定状态。

### 研究、市场与持续复核

| 功能 | 处理内容 | 主要结果 | 使用条件 |
| --- | --- | --- | --- |
| 市场观察 | 指数行情、技术指标与数据时间 | 行情列表、K 线和分析状态 | 对应数据能力可用 |
| 个股研究 | 财务、估值、行业及来源验证 | Evidence Card、事实和风险发现 | 字段、期间与来源满足规则 |
| 基金研究 | 基金指标、持仓披露和穿透资料 | 集中度、费用、波动及跟踪信息 | 报告期与字段明确 |
| 可转债研究 | 正股、转股价、债底、收益和流动性 | 转股价值、溢价率及风险发现 | 报价和基础字段齐备 |
| 行为分析 | 历史交易记录与问卷画像比较 | 行为维度、资料覆盖和复核提示 | 用户导入并确认历史记录 |
| 历史记忆 | 显式保存的画像、组合和研究意图 | 相关记录、匹配字段与恢复入口 | 当前账户范围内检索 |

## 核心技术

### 画像条件化风险预算

五项底层评分字段分别表示损失承受、投资期限、流动性需求、投资经验和收益预期。系统使用固定权重 `0.30 / 0.25 / 0.20 / 0.10 / 0.15` 计算百分制风险分数，再依据分数区间选择风险等级及预算向量。

| 风险等级 | 单一资产上限 | 已识别行业上限 | 科技行业合计上限 | 未分类合计上限 |
| --- | --- | --- | --- | --- |
| 保守型 | 20% | 30% | 25% | 10% |
| 均衡型 | 35% | 45% | 40% | 20% |
| 成长型 | 50% | 60% | 60% | 35% |

![画像参与风险计算](docs/submission/figures/judge-03-profile-calculation.png)

### 来源独立性与证据验证

系统按照主体、指标、单位和期间确定比较口径，并使用 `lineage_id` 识别同源记录。相同来源的重复记录只计为一项独立支持；组内冲突、口径差异、缺少来源关联和部分数据均进入问题记录。声明需要至少两个独立来源支持、没有独立反对并且没有待处理问题，才能形成已验证事实。

![证据验证与建议依据](docs/submission/figures/judge-04-evidence-validation.png)

### 穿透暴露与集中度

直接证券依据分类关系进入资产与行业暴露，基金和 ETF 依据可用成分信息形成穿透贡献。未分类部分保持独立质量状态。系统使用同一组已计算比例形成最大类别占比和 HHI，并在报告中记录分组方式、分母及舍入规则。

### 离散交易约束下的再平衡

再平衡服务将目标权重转换为交易数量，依次处理交易单位、持仓上限、报价、费用、最低现金比例和卖出优先顺序。每项行动完成后更新现金，最终依据测算数量重新计算组合暴露与画像条件。

![目标权重与交易数量计算](docs/submission/figures/judge-05-rebalancing.png)

### 有限研究任务与双重审查

专业研究采用有向无环图表达依赖关系。系统在执行前检查未知依赖和有向环，对可同时运行的独立节点执行并发调度，并以请求预算、节点预算和整体剩余时间共同限制单次调用。前置节点出现部分数据、空结果、失败或取消时，依赖节点保存对应原因。

建议生成前分别执行风险审查与合规审查。整体状态按照 `PASS < REVIEW_REQUIRED < BLOCKED` 的优先级聚合，任一审查提升等级时，最终结果保留该等级及关联问题。

![专业研究协作与双重审查](docs/submission/figures/judge-06-decision-gates.png)

### 版本化会话与历史记忆

| 上下文层次 | 保存内容 | 保存位置与范围 | 使用方式 |
| --- | --- | --- | --- |
| 近期消息 | 用户与助手的近期文本 | 前端按账户组织 | 理解连续追问和省略表达 |
| 当前会话前提 | 数据模式、画像、持仓、修订号与内容指纹 | 服务端 `session_truth` 记录 | 请求开始及输出期间检查版本 |
| 长期显式记录 | 用户确认保存的问卷、画像、组合及关联标识 | SQLite 或 PostgreSQL | 检索、恢复、重新确认与重新计算 |

内容指纹采用规范化 JSON 与 SHA-256 计算。用户在回答期间修改画像、持仓或数据模式时，后续输出会在再次检查中终止，并要求重新确认当前资料。历史记录的相关性排序只决定展示顺序；恢复后仍需经过当前资料确认。

## 工程实现

### 技术组件

| 范围 | 组件 | 职责 | 主要入口 |
| --- | --- | --- | --- |
| 前端 | HTML、CSS、原生 JavaScript、Hash 路由 | 页面结构、交互状态、HTTP 与 SSE 通信 | `app/api/static/index.html`、`app.js` |
| 可视化 | Lightweight Charts、AntV X6 工作流编辑器 | 行情图表、研究流程与任务关系展示 | `app/api/static/lightweight-charts.js`、`workflow-editor.js` |
| 接口服务 | FastAPI、Uvicorn、Pydantic | HTTP、SSE、字段校验和错误映射 | `app/api/main.py`、`app/api/contracts.py` |
| 金融计算 | Python、Decimal、领域模块 | 金额、比例、暴露、预算、配置与再平衡 | `app/portfolio/`、`app/risk/`、`app/allocation/` |
| 资料处理 | OpenPyXL、Pillow、RapidOCR | 表格、图片与文字识别 | `app/llm/ocr_portfolio_parser.py` |
| 数据存储 | SQLite、可选 PostgreSQL | 账户资料、上下文、历史记录和决策事件 | `app/store/` |
| 外部能力 | 问财、扶摇、Yahoo Finance、港股资讯网、兼容 OpenAI API 的模型 | 金融查询、行情与语言服务 | `app/providers/`、`app/llm/` |

### 数据状态

数据内容状态与送达方式分别记录。缓存、备用来源和直接查询均需要保留实际内容状态。

| 状态 | 含义 | 后续处理 |
| --- | --- | --- |
| `SUCCESS` | 记录存在且必需字段完整 | 可以进入归一化与证据校验 |
| `PARTIAL` | 记录存在，部分字段缺少或结构存在问题 | 可以展示，保留缺项并进入复核 |
| `EMPTY` | 查询范围明确且没有记录 | 保留空结果，不补写推测数值 |
| `FAILED` | 请求、授权、额度、网络或解析失败 | 返回结构化问题，进入备用来源、缓存、复核或阻断流程 |

送达方式包括 `DIRECT`、`CACHE_FRESH`、`FALLBACK_PROVIDER` 和 `CACHE_STALE_FALLBACK`。过期缓存归一化为 `STALE`，不能形成 `VERIFIED` 事实。

### 代码目录

| 路径 | 职责 | 代表内容 |
| --- | --- | --- |
| `app/api/` | 接口与静态工作台 | 应用工厂、路由、请求响应模型和前端资源 |
| `app/profile/` | 投资者画像 | 问卷、评分、画像确认与展示规则 |
| `app/portfolio/`、`app/risk/`、`app/allocation/` | 组合与风险计算 | 暴露、集中度、风险预算和配置边界 |
| `app/orchestration/`、`app/research/` | 专业研究 | 计划、依赖执行、交叉验证和证据构建 |
| `app/gates/`、`app/recommendation/` | 建议审查 | 风险、合规、建议组合和决策回执 |
| `app/providers/` | 外部数据能力 | 问财、扶摇、行情、行业、海外数据和缓存策略 |
| `app/service/` | 应用服务 | 对话、研究、情景、优化、再平衡和历史记忆 |
| `app/store/`、`app/security/`、`app/runtime/` | 运行基础 | 数据迁移、账户安全、密钥保护和数据模式 |
| `tests/` | 自动化验证 | 单元、接口、集成、数据规则和安全边界测试 |
| `tools/` | 工程工具 | 评测、HTTP 观测、备份恢复、配置和前端资源构建 |

## 本地运行

运行环境要求 64 位 Python 3.11 或 3.12，项目声明范围为 `>=3.11,<3.13`。

### Windows

双击 `start.bat`，或者在 PowerShell 中执行：

```powershell
.\start.bat
```

启动程序会选择 Python 3.12 或 3.11，创建 `.venv`，检查 Web 运行依赖并启动 Uvicorn。开发环境也可以手动创建：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,web]"
.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

### macOS

```bash
uv sync --extra dev --extra web
./start_mac.sh
```

也可以直接使用 `uv` 启动服务：

```bash
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

### 访问地址

| 地址 | 用途 |
| --- | --- |
| [http://127.0.0.1:8000/](http://127.0.0.1:8000/) | Prism 工作台 |
| [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs) | OpenAPI 文档 |
| [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health) | 进程、数据模式和能力摘要 |

需要独立的无认证开发预览时执行：

```powershell
.venv\Scripts\python.exe tools\dev_preview.py --fresh --port 8874
```

该入口使用独立 SQLite，并设置 `PRISM_DEV_NO_AUTH=true`，仅用于本机开发。

### 主要配置

| 配置 | 默认值或状态 | 用途 |
| --- | --- | --- |
| `PRISM_DB_PATH` | `data/private/prism.sqlite3` | SQLite 数据库路径 |
| `PRISM_DATABASE_URL` | 未设置 | 可选 PostgreSQL 连接，设置后优先使用 |
| `PRISM_SECRET_STORE_PATH` | `data/private/prism-secrets.json` | Windows DPAPI 保护的本地凭据文件 |
| `PRISM_DEV_NO_AUTH` | `false` | 开启无认证开发预览 |
| `HITHINK_FINANCE_API_KEY` | 未设置 | 扶摇服务端凭据 |
| `IWENCAI_API_KEY`、`IWENCAI_BASE_URL` | 未设置、`https://openapi.iwencai.com` | 问财 OpenAPI 凭据和地址 |
| `WENCAI_SKILLHUB_CONTRACT_VERIFIED` | `false` | 问财响应规则人工确认开关 |
| `PRISM_LLM_API_KEY`、`DEEPSEEK_API_KEY` 等 | 未设置 | 兼容 OpenAI API 的模型配置 |

Windows 的 `start.bat` 会读取仓库根目录中被 Git 忽略的 `.env`。供应商密钥不进入前端、业务数据库、日志或 Git。详细配置与维护命令见[本地部署说明](docs/local-deployment.md)。

### 开发检查

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m compileall app tools
node --check app/api/static/app.js
npm run build:workflow
npm run build:markdown
git diff --check
```

## 主要接口

完整接口及请求模型以运行时 [OpenAPI 文档](http://127.0.0.1:8000/api/docs) 和 `app/api/main.py` 为准。

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| `/api/health` | `GET` | 检查进程、数据模式和运行能力摘要 |
| `/api/v1/auth/*` | `GET`、`POST` | 本地账户注册、登录、退出和密码修改 |
| `/api/v1/runtime/data-mode` | `GET`、`PUT` | 读取或切换 `MOCK`、`LIVE` 数据模式 |
| `/api/v1/runtime/capability-gaps` | `GET` | 查看实时能力、缺少字段和验证条件 |
| `/api/v1/advisor/profile/*` | `GET`、`POST` | 问卷、画像预览、确认和摘要 |
| `/api/v1/advisor/portfolio/current` | `GET`、`PUT` | 读取或保存当前组合 |
| `/api/v1/advisor/portfolio/refresh` | `POST` | 使用已验证数据提供方刷新组合字段 |
| `/api/v1/advisor/queries` | `POST` | 执行结构化投顾查询并返回研究、审查和回执 |
| `/api/v1/copilot/chat` | `POST` | 投顾对话、工具进度和 SSE 响应 |
| `/api/v1/copilot/parse-portfolio*` | `POST` | 解析文本或图片中的持仓草稿 |
| `/api/v1/market/*` | `GET` | 市场目录、行情和技术分析 |
| `/api/v1/advisor/research-*` | `GET`、`POST` | 研究模板、运行及个股、基金、可转债研究 |
| `/api/v1/advisor/portfolio-optimization-*` | `GET`、`POST` | 目标结构与约束计算 |
| `/api/v1/advisor/rebalancing-*` | `GET`、`POST` | 整手、费用、现金和调整后风险测算 |
| `/api/v1/advisor/context-memory*` | `GET`、`POST` | 历史上下文保存、读取和检索 |
| `/api/v1/decision-events*` | `GET`、`POST` | 决策事件列表、详情和幂等写入 |
| `/api/v1/advisor/workflow*` | `GET`、`POST` | 固定研究工作流读取、保存和运行 |

认证模式下，服务端依据登录账户确定 `owner_id`。无认证开发模式中的 `X-Owner-ID` 只用于对象范围隔离。

## 系统边界

| 范围 | 当前处理方式 | 使用条件 | 范围外内容 |
| --- | --- | --- | --- |
| 实时研究 | 按运行能力调用问财、扶摇及其他已配置服务 | 凭据、额度、字段和来源满足要求 | 数据授权、长期稳定性与完整研究覆盖 |
| 固定数据 | 用于演示、自动化测试和确定性回放 | 页面与接口明确标记数据模式 | 不用于证明市场准确率 |
| 组合计算 | 提供暴露、预算、配置、情景和再平衡结果 | 画像、持仓、报价及规则版本有效 | 协方差、流动性压力、历史回测和全局约束求解 |
| 模型服务 | 处理意图、字段、工具选择和表达 | 配置兼容 OpenAI API 的服务 | 具体模型质量和长期可用性 |
| 外部操作 | 输出 `ADVISORY_ONLY` 研究与方案测算 | 用户检查结果及适用条件 | 券商同步、订单生成和交易执行 |
| 部署安全 | 本地账户、用户隔离、受保护凭据和访问审计 | 本地或受控网络环境 | 公网身份服务、独立审计、限流和长期监控 |

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [Prism.md](Prism.md) | 项目目标、总体约束与产品工程规范 |
| [竞赛技术文档](docs/submission/competition-technical-solution.md) | 需求、产品功能、核心技术、创新设计与验证案例 |
| [技术设计文档](docs/submission/technical-report.md) | 模块、接口、数据规则、部署结构、测试方法和系统边界 |
| [系统总体架构](docs/architecture.md) | 系统分层、运行流程与页面设计 |
| [本地部署说明](docs/local-deployment.md) | 账户、凭据、数据库、备份恢复和运行维护 |
| [问财数据接入说明](docs/iwencai-live-provider.md) | 问财配置、能力探测和真实查询规则 |
| [PRD 对接指南](docs/prd-integration-guide.md) | 产品联调所需模块、接口和数据状态 |
| [ADR-0001](docs/adr/0001-modular-monolith.md) | 模块化单体架构决策 |
| [TODO](TODO.md) · [LOG](LOG.md) | 当前任务与验证记录 |

Prism 用于证券研究与决策支持。页面展示、研究结论和组合测算不构成证券投资建议，任何真实交易均需由用户依据适用法律、账户规则和独立审查自行决定。
