# Reuse Matrix

本矩阵落实 [Prism.md](../Prism.md) 的 Phase 0 要求。上游默认只读；Prism 不进行跨仓库运行时导入。

## 当前核对基线

| 仓库 | 当前提交 | 与 `origin/main` | 当前测试 | 工作区 |
|---|---:|---|---:|---|
| `tradeeye-copilot` | `1675a87` | 一致 | 283 passed | clean |
| `TradeEye` | `8a1bd8c` | 一致 | 172 passed | clean |

核对日期为 2026-09-01。测试证明的是上游已有边界，不代表 Prism 的 SkillHub、画像、负载或端到端能力已经实现。

## 能力矩阵

| Capability | Existing Source | Reuse | Adapt | Design only | New | Notes |
|---|---|:---:|:---:|:---:|:---:|---|
| Evidence/Fact 状态与验证 | `tradeeye-copilot/copilot/models.py` | ✓ | | | | 小范围移植语义；Prism 增加新鲜度、质量和完整链闭包 |
| `CompanyCard.facts` 唯一事实入口 | `tradeeye-copilot/copilot/report/builder.py` | | ✓ | | | 泛化为跨资产 Fact Registry |
| Agent 引用白名单 | `tradeeye-copilot/copilot/agent/references.py` | ✓ | | | | 所有模型引用必须解析到本次已注册 ID |
| 只读工具契约 | `tradeeye-copilot/copilot/agent/tools.py` | | ✓ | | | 泛化为有界 Provider/Research tools |
| 硬校验与规则结果状态 | `tradeeye-copilot/copilot/checks`、`rules` | | ✓ | | | 保留 `HIT/MISS/NOT_EVALUATED/BLOCKED` 语义 |
| 作业所有权、暂停和取消语义 | `tradeeye-copilot/copilot/service/disclosure_jobs.py` | | ✓ | | | 存储改用数据库；保留 owner 隔离和状态机 |
| 同步公司研究管道 | `tradeeye-copilot/copilot/service/analyzer.py` | | | ✓ | | 领域步骤可参考，运行时重写为异步 DAG |
| SQLite snapshot/store | `tradeeye-copilot/copilot/store/sqlite.py` | | | ✓ | | 仅用于本地测试参考；生产目标为 PostgreSQL |
| 版本化强类型规则 | `TradeEye/tradeeye/strategies/rules.py` | ✓ | | | | 复用冻结配置、未知字段拒绝和版本校验模式 |
| Provider 降级语义 | `TradeEye/tradeeye/services/data.py` | | ✓ | | | 必需批次失败和可选源降级必须分离 |
| ETF 分支隔离 | `TradeEye/tradeeye/strategies/stock_recommender.py` | | ✓ | | | 复用隔离和状态，不复用评分权重 |
| 稳定 ID、幂等与原子提交 | `TradeEye/tradeeye/services/signal_store.py` | | ✓ | | | 保留语义，落到数据库事件/事务 |
| 组合交易状态机 | `TradeEye/tradeeye/services/portfolio.py` | | ✓ | | | 保留完整批次、幂等、陈旧估值语义；重写配置逻辑 |
| 策略/组合分层评估 | `TradeEye/tradeeye/services/backtest.py` | | ✓ | | | 扩展为画像一致性、证据覆盖和拒答正确性 |
| 原荐股权重、五槽位、三日交易 | `TradeEye` | | | ✓ | | 不进入个性化投顾逻辑 |
| CSV 生产持久化 | `TradeEye` | | | ✓ | | 不满足并发、事务和用户隔离目标 |
| 暖白/深墨/陶土橙视觉语法 | `tradeeye-copilot/web/styles.css` | | ✓ | | | 复用 token、排版和证据交互，不复制股票页面结构 |
| User Profile Engine | | | | | ✓ | 问卷规则 + 结构化提取 + 冲突确认 |
| SkillHub Provider | | | | | ✓ | 等待比赛专用接口、凭据和授权边界 |
| Structured Orchestrator | | | | | ✓ | 异步 DAG，不是 Agent 自由聊天 |
| Cross Validation | | | | | ✓ | 检查来源独立性、时间、口径和真实冲突 |
| Portfolio/Risk/Compliance | | | | | ✓ | 可借鉴状态机，业务策略重新设计 |
| Decision Receipt/Replay | | | | | ✓ | 保存画像、证据、规则、模型和建议版本 |

## 移植规则

1. 先写 Prism 契约测试，再移植最小代码；不得整体复制上游目录。
2. 每次移植记录来源文件、基线提交和后续修改。
3. 不把上游的短周期推荐权重包装成个性化投顾策略。
4. 上游根目录当前未发现 `LICENSE`、`COPYING` 或 `NOTICE`；比赛提交前必须确认代码归属和允许的复用范围。
5. 上游后续变化不自动同步；升级必须重新运行契约测试和差异审查。
