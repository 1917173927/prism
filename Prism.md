# 个性化证券投顾智能体系统企划书
## Agent Execution Specification

> Working Title: Personalized Investment Copilot  
> Target: 同花顺 A18「基于同花顺问财 SkillHub 的个性化证券投顾智能体系统设计」  
> Status: Active Project Specification  
> Primary Principle: Evidence First, Deterministic Before Generative, Personalization Above Generic Advice

---

# 1. 项目目标

本项目旨在构建一套基于 **同花顺问财 SkillHub + 第三方大语言模型** 的个性化证券投顾智能体系统。

系统不是简单的金融聊天机器人，也不是让 LLM 根据用户问题直接生成买卖建议。

核心目标是建立以下完整链路：

```text
用户信息
    ↓
用户画像 / 风险偏好建模
    ↓
投资问题理解与任务规划
    ↓
主协调智能体 Orchestrator
    ↓
多个专业研究智能体并行分析
    ↓
可信金融数据 / Evidence
    ↓
交叉验证与分歧处理
    ↓
组合与风险分析
    ↓
合规检查
    ↓
个性化投资建议
    ↓
可解释展示 + 数据溯源
```

赛题明确要求系统支持用户画像、宏观研究、行业分析、个股研究、基金配置等多智能体协作，并形成“1 个主协调智能体 + N 个专业智能体”的体系。

系统最终至少覆盖：

```text
大盘研判
行业配置
个股分析
ETF / 基金筛选
可转债分析
资产组合优化
风险提示
仓位建议
投资逻辑解释
数据溯源
```

官方同时要求支持多轮交互、上下文记忆、投资逻辑展示以及用户风险画像。

---

# 2. 核心设计理念

本项目必须遵循以下优先级：

```text
数据真实性
>
确定性计算
>
证据完整性
>
风险与合规
>
Agent 推理
>
自然语言表现
```

不得采用：

```text
用户问题
↓
把所有原始数据塞给 LLM
↓
直接输出投资建议
```

必须采用：

```text
Data Provider
↓
Normalization
↓
Validation
↓
Fact / Evidence
↓
Research Agent
↓
Cross Validation
↓
Portfolio / Risk Engine
↓
Compliance
↓
Recommendation
```

---

# 3. 与现有项目的关系

本项目不是从零开发。

优先复用：

```text
daoyezongzi/tradeeye-copilot
daoyezongzi/TradeEye
```

开发 Agent 在实施任何大型重构前，必须先阅读两个项目：

```text
README.md
项目结构
models
datasource
rules
service
report
API
tests
```

原项目默认视为 **read-only upstream reference**。

除非用户明确要求，不直接破坏性修改原仓库。

推荐建立新的比赛项目，通过：

```text
extract
adapter
port
reuse
```

的方式吸收已有能力。

---

# 4. TradeEye Copilot 可复用能力

TradeEye Copilot 已经建立：

```text
Tushare
↓
结构化财务数据
↓
硬校验
↓
规则引擎
↓
Finding
↓
Evidence
↓
Company Research Card
↓
Agent QA
```

现有设计坚持：

- 确定性管道优先；
- 财务数字不交由 LLM 计算；
- 每条 Finding 绑定 Evidence；
- Agent 只能通过事实接口获得金融事实。

其 Agent Fact Contract 已包含：

```text
FactStatus

VERIFIED
UNAVAILABLE
INVALID
NOT_APPLICABLE
```

以及：

```text
RuleResultStatus

HIT
MISS
NOT_EVALUATED
BLOCKED
```

其中 `CompanyCard.facts` 是 Agent 的唯一事实接口，每条 VERIFIED Fact 都要求对应 Evidence。

该设计必须作为本项目 Evidence Architecture 的基础。

不要重新发明一套更弱的：

```text
source_url: "xxx"
```

式引用系统。

---

# 5. TradeEye 可复用能力

TradeEye 当前已经具备：

```text
股票筛选
风险门
ETF 独立评价
虚拟组合
仓位容量
交易状态
组合 NAV
回测
风险分析
主题资讯
自动化任务
```



这些能力可以分别演化为：

```text
TradeEye Stock Recommender
→ Stock Candidate Engine

TradeEye ETF
→ ETF Research Engine

TradeEye Portfolio
→ Portfolio Simulation Engine

TradeEye Risk Rules
→ Portfolio Risk Layer

TradeEye Backtest
→ Recommendation Evaluation
```

注意：

不要直接将原 TradeEye 的短线策略当作本项目最终投顾逻辑。

应复用：

```text
工程结构
数据处理
评分框架
风险门设计
Portfolio 状态机
Backtest Infrastructure
```

策略本身必须允许替换。

---

# 6. 总体系统架构

目标架构：

```text
                         ┌─────────────────┐
                         │      User       │
                         └────────┬────────┘
                                  ↓
                    ┌─────────────────────────┐
                    │ User Profile / Memory   │
                    │ Risk Preference Engine  │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │     Main Orchestrator   │
                    │ Intent / Task Planning  │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼─────────────────────────┐
        ↓                        ↓                         ↓
 Macro Research           Industry Research         Stock Research
     Agent                     Agent                    Agent
        │                        │                         │
 SkillHub/API              SkillHub/API         TradeEye Copilot
        │                        │                         │
        └─────────────┬──────────┴───────────┬─────────────┘
                      ↓                      ↓
                  ETF Agent              Fund Agent
                      │                      │
                      └──────────┬───────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Evidence Aggregator     │
                    │ Cross Validation        │
                    │ Disagreement Resolver   │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Portfolio Engine        │
                    │ Allocation / Exposure   │
                    │ Scenario Analysis       │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Risk Engine             │
                    │ Compliance Guard        │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Recommendation Composer │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Explainable UI          │
                    │ Evidence Drill-down     │
                    └─────────────────────────┘
```

---

# 7. 不要构建“自由聊天式多 Agent”

不得设计：

```text
Macro Agent:
我觉得经济不好。

Stock Agent:
我不同意。

ETF Agent:
你们觉得呢？

...
```

这种自由 Agent 对话体系。

核心 runtime 应采用：

```text
Deterministic Workflow
+
Specialized LLM Nodes
+
Structured State
```

Agent 输出必须使用 Schema。

Agent 之间原则上不通过自然语言聊天传递关键事实。

---

# 8. ResearchState

整个系统维护统一状态对象：

```python
ResearchState
```

建议包含：

```python
class ResearchState:
    request_id
    user_id

    user_query
    intent

    user_profile

    task_plan

    market_context
    macro_research
    industry_research
    stock_research
    fund_research
    etf_research
    convertible_bond_research

    facts
    evidence
    findings

    disagreements
    validations

    portfolio_candidates
    portfolio_analysis

    risk_report
    compliance_report

    recommendation

    latency
    errors
```

所有 Agent 都只允许读写明确属于自己的字段。

---

# 9. 用户画像模块

实现：

```text
User Profile Engine
```

输入来源：

```text
自然语言
问卷
当前持仓
历史投资行为
投资期限
风险承受能力
收益预期
最大可接受回撤
资产规模区间
资产类别偏好
禁投领域
```

输出结构：

```python
UserProfile(
    risk_level,
    risk_score,
    investment_horizon,
    expected_return_range,
    max_drawdown_tolerance,
    liquidity_need,
    experience_level,
    asset_preferences,
    sector_preferences,
    exclusions,
    current_positions,
    concentration,
    confidence,
    evidence
)
```

风险画像不得完全由 LLM 主观决定。

采用：

```text
Questionnaire / Rules
+
Structured Extraction
+
Consistency Check
```

模式。

例如：

```text
问卷风险得分 = deterministic

自然语言描述
→ LLM extraction
→ structured parameters

二者冲突
→ 标记 conflict
→ 要求用户确认
```

---

# 10. Orchestrator

主协调智能体只负责：

```text
理解用户问题
判断任务类别
规划调用哪些专业 Agent
规划所需数据
控制并行任务
聚合结果
检测缺失信息
```

不得负责：

```text
自己计算全部金融指标
自己完成所有研究
绕过 Evidence 系统输出建议
```

示例：

用户：

```text
我风险偏好一般，准备持有两年，
现在有较多科技基金，
想看看是否需要降低科技仓位。
```

任务计划：

```json
{
  "tasks": [
    "market",
    "macro",
    "technology_industry",
    "fund_holdings",
    "portfolio_concentration",
    "risk"
  ]
}
```

然后并行执行。

---

# 11. Macro Research Agent

负责：

```text
市场环境
利率
流动性
宏观经济
主要指数
政策环境
风险事件
```

优先调用：

```text
问财 SkillHub
```

必要时允许通过 Provider Interface 接其他数据源。

输出：

```python
MacroResearchResult(
    facts,
    findings,
    regime,
    risks,
    confidence,
    evidence
)
```

---

# 12. Industry Research Agent

负责：

```text
行业景气
行业估值
盈利趋势
竞争格局
资金变化
政策影响
产业链
```

输出必须区分：

```text
事实 Fact
判断 Finding
假设 Hypothesis
```

不得混写。

---

# 13. Stock Research Agent

优先从 TradeEye Copilot 迁移。

职责：

```text
财务事实
财务异常
盈利质量
现金流
资产质量
估值
价格/市场上下文
重要公告
```

Agent 不自行计算核心财务算术。

所有财务计算走 deterministic layer。

---

# 14. ETF / Fund Agent

ETF Agent 可参考 TradeEye 已有 ETF 分支。

基金 Agent 至少分析：

```text
基金类别
跟踪指数
行业暴露
Top Holdings
历史波动
最大回撤
费用
集中度
与用户现有资产相关性
```

最终目的不是给基金单独打一个模糊的 AI 分数，而是为：

```text
Portfolio Engine
```

提供标准化资产信息。

---

# 15. Convertible Bond Agent

赛题要求覆盖可转债。

第一版不追求完整可转债量化模型。

最低实现：

```text
正股
转股价
转股价值
转股溢价率
债底
到期收益
信用情况
流动性
风险提示
```

所有公式走 deterministic code。

---

# 16. Evidence Architecture

定义统一对象：

```python
Evidence(
    evidence_id,
    provider,
    source,
    field,
    value,
    unit,
    period,
    timestamp,
    retrieved_at,
    quality_status
)
```

Fact：

```python
Fact(
    fact_id,
    subject,
    metric,
    value,
    unit,
    period,
    status,
    evidence_ids
)
```

Finding：

```python
Finding(
    finding_id,
    type,
    severity,
    statement,
    fact_ids,
    confidence,
    methodology
)
```

Recommendation：

```python
Recommendation(
    recommendation_id,
    action_type,
    asset,
    allocation_range,
    rationale,
    finding_ids,
    risk_ids,
    compliance_status
)
```

必须形成：

```text
Recommendation
      ↓
Finding
      ↓
Fact
      ↓
Evidence
```

完整可追溯链。

---

# 17. Cross Validation

实现：

```text
CrossValidationEngine
```

专业 Agent 不允许简单投票：

```text
3 Agent 看多
1 Agent 看空
→ 看多
```

应检查：

```text
是否使用不同数据
是否只是重复同一 Evidence
数据时间是否一致
指标口径是否一致
结论是否真正冲突
```

输出：

```python
ValidationResult(
    claim,
    support,
    contradiction,
    unresolved,
    confidence
)
```

如果存在无法解决的重要矛盾：

```text
系统必须显式展示不确定性
```

而不是强行输出确定结论。

---

# 18. Portfolio Engine

Portfolio Engine 不交由 LLM 直接决定仓位。

LLM 可以：

```text
解释资产配置逻辑
生成场景描述
解释风险
```

实际配置计算通过确定性程序完成。

第一版支持：

```text
风险预算
资产类别上限
单资产上限
行业集中度
相关性
用户最大回撤要求
流动性要求
```

允许采用简单、可解释的：

```text
rule-based allocation
risk parity simplified
mean-variance optional
```

不要为了“高级”直接堆复杂优化器。

---

# 19. 风险系统

风险检查至少包括：

```text
单一资产集中度
行业集中度
高波动资产占比
最大回撤风险
流动性
期限错配
资产相关性
用户画像匹配度
数据不足
异常市场状态
```

Risk Engine 必须返回结构化对象：

```python
RiskFinding(
    risk_type,
    severity,
    description,
    affected_assets,
    evidence,
    mitigation
)
```

---

# 20. Compliance Guard

这是硬模块，不允许只使用 Prompt：

```text
“请遵守证券法规。”
```

Compliance Guard 至少包含：

```text
Rule Layer
+
LLM Semantic Review
```

规则层负责：

```text
禁止无证据收益承诺
禁止保证盈利
禁止伪造确定概率
禁止隐藏风险
禁止将数据不足包装为确定结论
投资建议必须附风险提示
推荐必须能够追踪到事实依据
```

输出：

```python
ComplianceResult(
    passed,
    violations,
    required_disclosures,
    sanitized_output
)
```

赛题本身要求系统建立风控与合规审核流程。

---

# 21. Recommendation Composer

Recommendation Composer 是最后的语言层。

输入：

```text
UserProfile
Validated Findings
Portfolio Analysis
Risk Findings
Compliance Result
```

输出展示：

```text
结论
建议配置
为什么
支持证据
风险
不确定性
什么时候需要重新评估
```

禁止生成没有 Evidence 支撑的：

```text
“强烈推荐”
“必涨”
“目标收益 30%”
“稳赚”
```

---

# 22. SkillHub Adapter

必须支持同花顺问财 SkillHub。

定义统一 Provider Protocol：

```python
class FinancialProvider:
    async get_market_data(...)
    async get_company_data(...)
    async get_industry_data(...)
    async get_macro_data(...)
    async get_fund_data(...)
    async search_news(...)
    async search_reports(...)
```

实现：

```text
WencaiSkillHubProvider
```

允许保留：

```text
TushareProvider
```

作为辅助 Provider。

核心目标：

```text
Agent 不绑定具体 API。
```

---

# 23. 性能设计

赛题要求：

```text
≥100 用户并发
单次投顾响应 ≤3 秒
可用性目标 ≥99.9%
```



因此禁止五个 Agent 串行执行。

使用：

```text
asyncio
parallel tool calls
connection pooling
cache
pre-computation
timeouts
circuit breaker
fallback
```

典型流程：

```text
Orchestrator
     ↓
async gather(
    macro,
    industry,
    stock,
    fund
)
     ↓
validation
```

建议缓存：

```text
市场状态
宏观指标
行业指标
行情
基金持仓
财务数据
新闻搜索结果
```

用户画像等私人数据不得进入跨用户公共缓存。

---

# 24. 延迟预算

以 3 秒为硬目标进行设计：

```text
request parsing       <100ms
profile retrieval     <100ms
planning              <300ms
parallel data calls   <1000ms
research nodes        <1000ms
validation            <300ms
portfolio/risk        <200ms
final composition     <500ms
```

不要假定每个外部 API 都能稳定满足该预算。

必须：

```text
benchmark
measure
record
```

如果实际无法达到，测试报告必须如实展示结果，不得伪造性能指标。

---

# 25. API

推荐 FastAPI。

基础路由：

```text
POST /api/profile
GET  /api/profile/{id}
PATCH /api/profile/{id}

POST /api/advisor/query
GET  /api/advisor/jobs/{id}

GET  /api/research/{id}
GET  /api/evidence/{id}

POST /api/portfolio/analyze

GET  /api/health
GET  /api/metrics
```

内部：

```text
/api/internal/providers/*
/api/internal/eval/*
```

不得直接暴露外部凭据。

---

# 26. 前端

产品形态应是：

```text
Investment Research Workspace
```

而不是纯 ChatGPT 克隆。

推荐页面：

```text
Overview
Portfolio
Research
Advisor
Evidence
Risk Profile
```

Advisor 页面：

```text
┌──────────────────────────────────────┐
│ User / Risk Profile                  │
├──────────────────────────────────────┤
│ Conversation        │ Analysis       │
│                     │                │
│                     │ Macro          │
│                     │ Industry       │
│                     │ Stock          │
│                     │ Fund           │
├─────────────────────┼────────────────┤
│ Recommendation      │ Evidence       │
│ Allocation          │ Risk           │
└──────────────────────────────────────┘
```

所有重要结论必须可以点击：

```text
Why?
Evidence
Source
```

---

# 27. 推荐的代码结构

```text
project/
│
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── orchestration/
│   ├── agents/
│   │   ├── macro/
│   │   ├── industry/
│   │   ├── stock/
│   │   ├── etf/
│   │   ├── fund/
│   │   └── convertible_bond/
│   │
│   ├── profile/
│   ├── evidence/
│   ├── validation/
│   ├── portfolio/
│   ├── risk/
│   ├── compliance/
│   │
│   ├── providers/
│   │   ├── base.py
│   │   ├── wencai.py
│   │   └── tushare.py
│   │
│   ├── llm/
│   ├── store/
│   └── service/
│
├── web/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── load/
│   └── eval/
│
├── docs/
│   ├── architecture.md
│   ├── evidence-contract.md
│   ├── agent-contracts.md
│   ├── compliance.md
│   ├── testing.md
│   └── demo-script.md
│
├── Prism.md
├── TODO.md
├── LOG.md
└── README.md
```

---

# 28. Agent Contracts

每个 Agent 必须具有：

```text
Purpose
Allowed Inputs
Required Inputs
Allowed Tools
Output Schema
Failure Modes
Timeout
Fallback
```

禁止 Agent：

```text
任意访问所有 state
任意修改其他 Agent 输出
任意生成未经验证数字
```

---

# 29. Failure Model

必须主动处理：

```text
SkillHub unavailable
LLM timeout
market data unavailable
partial financial data
stale data
provider disagreement
invalid user profile
insufficient evidence
portfolio infeasible
```

数据不足时：

```text
UNKNOWN / BLOCKED
```

不得转换成：

```text
NORMAL
NO RISK
NO PROBLEM
```

---

# 30. MVP 范围

第一阶段必须优先形成完整闭环：

```text
User Profile
      ↓
Orchestrator
      ↓
Macro + Industry + Stock + ETF
      ↓
Evidence
      ↓
Cross Validation
      ↓
Portfolio Risk
      ↓
Compliance
      ↓
Personalized Recommendation
      ↓
Explainable UI
```

不要在 MVP 阶段优先投入：

```text
复杂动画
大量 Agent persona
长期自治 Agent
复杂知识图谱
自研模型训练
微服务拆分
Kubernetes
```

---

# 31. P0 / P1 / P2

P0：

```text
SkillHub Provider
User Profile
Evidence Contract
Stock Agent
Industry Agent
Macro Agent
ETF Agent
Orchestrator
Cross Validation
Risk
Compliance
Recommendation
Basic UI
```

P1：

```text
Fund Agent
Convertible Bond Agent
Portfolio Optimization
Persistent Memory
Load Test
Provider Cache
Fallback
Advanced Evidence UI
```

P2：

```text
Scenario Simulation
Recommendation History
Portfolio Rebalancing
Evaluation Dashboard
Advanced Explainability
Copilot Interactive Task Center (Phase 38)
Live LLM Cognitive Agent & Providers (Phase 39)
```

P3（下一步进阶目标）：

```text
Multi-Agent Graph & Pipeline Workflow Builder (Phase 40, 引入成熟开源图引擎)
Session Truth Blackboard & Anti-Hallucination Panel (Phase 41)
```

P3 目标致力于打破固定问答模板：引入成熟开源图引擎（如 AntV X6 / LiteGraph / Flow）构建多 Agent 可视化工作流编排面板（对标 Coze），支持用户自定义投研 DAG、节点拖拽连线与参数自由调优；并在多轮交互层面构建会话全局研判黑板，实现上下文漂移警告、自洽性核验与一键手动纠偏。全量赛题任务与 PRD 对接规范详见唯一技术架构规范 [系统总体技术架构与方案设计规范](docs/architecture.md)。

截至 2026-09-02，P1 路线与 P2 (Phase 34–39) 已完成全面验收并收敛至 Copilot 默认工作台；P3 进阶能力作为下一阶段核心演进目标。







---

# 32. 测试要求

不得只测试：

```text
API 返回 200。
```

必须覆盖：

```text
金融算术
Fact contract
Evidence integrity
Agent structured output
provider failure
data missing
cross validation
portfolio constraints
compliance
user isolation
timeouts
concurrency
```

---

# 33. Agent Evaluation

建立固定测试集：

```text
eval_cases/
```

至少包含：

```text
低风险用户
高风险用户
短期限用户
长期用户
高度集中持仓
科技重仓
市场数据缺失
Agent 数据冲突
财报数据异常
新闻与基本面冲突
```

评估：

```text
Fact Accuracy
Evidence Coverage
Hallucination Rate
Recommendation Consistency
Profile Alignment
Risk Detection Rate
Compliance Violation Rate
Latency
```

---

# 34. Definition of Done

一个功能不得因为：

```text
代码写完
```

就被标记完成。

必须满足：

```text
implementation
+
tests
+
real run
+
error handling
+
documentation
+
UI/API integration
```

---

# 35. 比赛最终验收场景

至少准备以下完整 Demo：

### Demo A — 用户画像

用户完成问卷和自然语言描述。

系统建立：

```text
风险等级
期限
收益目标
最大可接受回撤
当前持仓
```

---

### Demo B — 个性化查询

用户：

```text
我科技基金仓位比较高，
最近市场波动很大，
是否应该降低科技资产暴露？
```

系统展示：

```text
Macro Agent
Industry Agent
Fund Agent
Portfolio Engine
Risk Engine
```

---

### Demo C — Evidence

点击：

```text
“科技资产集中度过高”
```

展开：

```text
具体持仓
行业暴露
比例
来源
时间
```

---

### Demo D — Agent disagreement

例如：

```text
Macro Agent = 谨慎
Industry Agent = 积极
```

系统不强行覆盖，而是展示：

```text
冲突原因
各自 Evidence
最终处理方法
```

---

### Demo E — 数据异常

模拟一个 Provider 失败。

系统：

```text
降级
标注数据缺失
不产生虚假事实
```

---

### Demo F — 个股研究

调用 TradeEye Copilot 迁移后的能力：

```text
财务事实
异常
Evidence
风险
```

---

# 36. 项目材料

最终必须准备：

```text
项目概要
项目详细方案
架构文档
产品说明
测试报告
开发记录
项目分工
PPT
演示视频
```

这是官方提交要求。

---

# 37. 开发过程规则

Coding Agent 在开发过程中遵循：

```text
inspect
→ understand
→ plan
→ implement
→ test
→ run
→ inspect diff
→ record
```

开始任何阶段前：

1. 阅读 Prism.md。
2. 阅读 TODO.md。
3. 阅读 LOG.md。
4. 检查 git status。
5. 查看相关已有代码。
6. 再决定是否新增模块。

不得因为现有代码“不够漂亮”而无意义重写。

优先：

```text
reuse > adapt > refactor > rewrite
```

---

# 38. 禁止事项

禁止：

```text
为了满足“多智能体”而制造没有必要的 Agent。

让多个 LLM Agent 自由讨论关键金融事实。

让 LLM 计算核心财务数字。

用 Prompt 代替风险控制。

用 Prompt 代替合规。

数据缺失时自行脑补。

隐藏 Agent 之间的结论冲突。

为了 Demo 写死最终结论。

为了达到比赛指标伪造延迟和压力测试结果。

直接将 TradeEye 的历史策略包装成“AI 个性化投顾”。

破坏已有 TradeEye / TradeEye Copilot 仓库。
```

---

# 39. 产品差异化

本项目的竞争力不应描述为：

```text
“我们用了多个 Agent。”
```

而应描述为：

> 一个以用户画像为条件、以可信金融事实为基础、通过多个专业研究模块协作，并且能够将每一个投资判断追溯到底层证据的个性化投顾 Copilot。

技术护城河：

```text
Personalization
       +
Evidence Grounding
       +
Deterministic Finance
       +
Multi-Agent Orchestration
       +
Cross Validation
       +
Risk / Compliance
```

---

# 40. 最重要的系统不变量

无论后续如何修改架构，都不得破坏以下原则：

```text
1. Facts must be traceable.

2. Financial arithmetic must be deterministic.

3. Missing data must remain missing.

4. LLM inference must not become financial fact.

5. Recommendations must derive from validated findings.

6. User risk profile must materially affect recommendations.

7. Risk and compliance must be independent from recommendation generation.

8. Multi-agent architecture must solve real domain separation,
   not exist only for presentation.

9. External provider failure must degrade explicitly.

10. Every claimed capability must have fresh test evidence.
```

---

# 41. Agent 首次接手任务

第一次读取本企划书后，不要立刻大规模编码。

首先执行：

```text
PHASE 0 — Repository Reconnaissance
```

检查：

```text
TradeEye
TradeEye Copilot
当前新项目目录
```

输出一份：

```text
Reuse Matrix
```

格式：

| Capability | Existing Source | Reuse | Adapt | New | Notes |
|---|---|---|---|---|---|
| Evidence | tradeeye-copilot | ✓ | | | |
| Financial validation | tradeeye-copilot | ✓ | | | |
| Stock research | tradeeye-copilot | | ✓ | | |
| ETF analysis | TradeEye | | ✓ | | |
| Portfolio state | TradeEye | | ✓ | | |
| User profile | | | | ✓ | |
| SkillHub adapter | | | | ✓ | |
| Orchestrator | | | | ✓ | |
| Compliance | | | | ✓ | |

随后制定：

```text
Implementation Plan
```

必须明确：

```text
哪些代码直接复用
哪些代码抽象为公共模块
哪些只借鉴设计
哪些必须重新实现
```

得到这一结果后，才进入正式开发。

---

# 42. 最终目标

最终产品应让评委看到的不是：

```text
“这是一个会聊天的股票 AI。”
```

而是：

```text
User
 ↓
Personalization
 ↓
Specialized Research Agents
 ↓
Verified Facts
 ↓
Evidence
 ↓
Cross Validation
 ↓
Portfolio / Risk
 ↓
Compliance
 ↓
Explainable Recommendation
```

即：

# Evidence-Grounded Personalized Investment Copilot

这是本项目所有工程设计的中心。
