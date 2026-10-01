# Prism研究平台运行与复验

## 第1章 安装与运行

### 一、 依赖与应用

项目支持Python3.11—3.12，使用已提交的`uv.lock`。完整研究依赖通过显式extras安装：

```powershell
uv sync --extra dev --extra web --extra research --extra knowledge
uv run --no-sync python -m tools.cache_research_model
uv run --no-sync uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

缓存命令会访问Hugging Face下载固定模型修订；应用启动不隐式下载。模型与资料数据库均在`data/private/`，不提交Git。模型不可用时检索明确降级到关键词。

| 配置 | 默认值 | 作用 | 边界 |
| --- | --- | --- | --- |
| PRISM_DB_PATH | data/private/prism.sqlite3 | 默认SQLite资料及事实存储 | 启动执行普通表迁移；FTS独立初始化 |
| PRISM_DATABASE_URL | 空 | 可选PostgreSQL适配器 | 另安装postgres extra并提供服务端DSN |
| PRISM_RESEARCH_PROVIDER_LIMIT | 100 | LIVE研究Provider配额 | 本地限制不证明上游配额 |
| PRISM_RESEARCH_MODEL_LIMIT | 8 | 研究运行时模型槽位 | 当前结构化LIVE模板调用数为0 |
| PRISM_DEV_NO_AUTH | false | 默认账户认证 | 仅本地隔离测试才开启开发模式 |

活动100、等待400、每用户等待200、总预算60秒及32节点为当前固定边界。该准入器是单进程状态；多worker不能获得服务全局100保证。认证信息按请求读取，注入的HTTP客户端由调用者关闭。

### 二、 页面及接口

| 入口 | 页面／接口 | 主要功能 | 权限 |
| --- | --- | --- | --- |
| 技能 | #skill-store；/api/v1/skills | 注册版本、探测、启停、卸载、个人选择 | 管理操作管理员；个人选择当前账户 |
| LIVE | #live-research；/api/v1/research/runs | 提交、查询、取消及历史截止 | 服务端绑定owner |
| 模板 | /api/v1/research/templates、/runs/from-template | live-equity-basic.v1，不携带Fixture期望值 | 当前账户；目标为证券代码 |
| 指标 | /api/v1/runtime/research-metrics | 实际任务、排队、Provider与模型统计 | 管理员 |
| 事实 | /api/v1/research/facts/{id}、/snapshots/{id} | 归一化值、原始请求响应及版本 | 当前owner；哈希复验 |
| 论文 | #research-algorithms；/api/v1/research/algorithms/* | regime、five-factors、covariance | 当前账户；确定性计算 |
| 文献 | #research-knowledge；/api/v1/research/knowledge/* | 上传、文档、搜索、引用、原子声明、重建 | 私有当前账户；公共资料及来源管理员 |

接口完整字段以运行应用的`/api/docs`和OpenAPI为准。五因子必须声明`monetary_unit=CNY`；所有算法需要来源与带时区的as_of。金融收益为小数比例，日频图表为百分数。接口或页面返回缺口时不得缩短指标窗口或补造输入。

## 第2章 验证入口

### 一、 本地验证

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short
$env:PRISM_RUN_REAL_KNOWLEDGE_EMBEDDING='1'
.\.venv\Scripts\python.exe -m pytest tests/unit/test_knowledge_embedding.py
$env:OMP_NUM_THREADS='4'
$env:MKL_NUM_THREADS='4'
.\.venv\Scripts\python.exe -m tools.evaluate_research_knowledge --output output/research/keyword.json
.\.venv\Scripts\python.exe -m tools.evaluate_research_knowledge --hybrid --output output/research/hybrid.json
.\.venv\Scripts\python.exe -m tools.research_platform_load_test --mode controlled --repeats 3 --output output/research/load-controlled.json
.\.venv\Scripts\python.exe -m tools.verify_research_snapshot_algorithms
```

检索评测使用冻结合成资料，不自动放开生产混合模式。历史脚本读取留存市场快照，不调用远端金融Provider。负载脚本保留完整归一化节点和状态，Provider返回成功也不等于金融证据已验证。

### 二、 浏览器验证

隔离测试服务禁用真实金融Provider、模型服务和隐式模型下载，使用临时SQLite。先用`npm ci`安装锁定的浏览器测试依赖；服务在一个终端运行，浏览器脚本在另一个终端运行。Chrome路径可用PRISM_TEST_BROWSER覆盖。

```powershell
.\.venv\Scripts\python.exe tests/browser/research_platform_server.py --port 8022
```

```powershell
$env:PRISM_TEST_BASE_URL='http://127.0.0.1:8022/'
node tests/browser/test_research_navigation.mjs
node tests/browser/test_research_metrics.mjs
node tests/browser/test_skill_store.mjs
node tests/browser/test_research_tools.mjs
node tests/browser/test_research_ui_evidence.mjs
```

### 三、 外部复验

| 验证 | 命令或条件 | 写入范围 | 验收边界 |
| --- | --- | --- | --- |
| PostgreSQL | 设置专用PRISM_TEST_POSTGRES_DSN，执行tests/integration/test_research_postgres.py | 创建独立测试schema，finally删除 | 只使用测试数据库，保留迁移／回滚结果 |
| 公开来源 | python -m tools.verify_research_public_sources | 新建私有验证SQLite，输出output/research/crawler-live.json | 单轮有限公开来源，遵守间隔及大小约束 |
| 真实负载 | 配额与合同恢复后，在支持版本下执行load工具的--mode real --repeats 3 | 临时测试事实库；报告保留完整节点 | 遇额度、授权或权限错误即停止，不能重复消耗耗尽额度 |
| 人工金融门槛 | 真实资料逐原子声明标注及≥100问冻结 | 新增独立验收证据 | 数值100%、无依据≤1%、引用支持≥95%、Recall≥90%、错误拒答≤5% |

外部验收未通过时状态保留BLOCKED。引用存在性、逐字定位及金融真实性分别记录；零分母返回N/A。最新状态见[2026年10月1日验收报告](submission/research-platform-acceptance-20261001.md)。

2026年10月1日用户撤销Pages发布。自动发布工作流已删除，代码推送只负责Git归档；历史静态快照保留用于回归，不再要求公开页面发布。
