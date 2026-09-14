# LOG

## 2026-09-15：问财九 Skill 项目级真实接入

- 将公告、新闻、研报、行情、财务、行业、宏观、基金和可转债九个官方 Skill 的 ID、版本、端点及下载包 SHA-256 固化为项目清单，并纳入 wheel 包数据；运行时不依赖本机全局 SkillHub CLI，也不执行下载包脚本。
- 修正官方请求头与路由：综合搜索和结构化查询均发送 Plugin 占位头，严格要求 `status_code=0`；ProviderOperation 按项目清单选择专用 Skill ID，聊天支持公告、新闻和研报频道。
- 问财密钥复用现有 Windows DPAPI 保护存储，使用项目级 `provider:wencai` 槽，填写一次后跨热重载和重启恢复；读取接口不返回明文。真实九 Skill 探测全部通过后才持久化契约验证状态并开放问财 LIVE 能力。
- 当前凭据真实验收：九个 Skill 均返回 HTTP 200、Provider `SUCCESS`；`/api/v1/runtime/provider-query` 公告查询返回真实记录；LIVE 聊天完成真实 LLM → `query_wencai_semantic` → 问财 → SSE 闭环，无错误事件。
- 修复聊天四阶段卡片未挂载：界面现在按真实 SSE 事件显示“理解问题、查询真实数据（按需）、核验事实与约束、组织回答”，多工具全部结束后才进入核验；普通问答把外部检索标为无需执行，失败阶段明确标记。该卡片表示处理阶段，不冒充四个并行子 Agent。
- 问财回复改为列示最多三条真实记录的标题、发布日期和正文摘要，并约束模型在纯公告问题中只调用问财；所有已成功执行的工具结果均保留，“公告 + 行情”或“公告 + 组合体检”等复合意图不会丢结果。新增“清空上下文”，仅中止当前生成并清除本机 owner 范围的聊天历史，不删除画像、持仓、模型配置或问财凭据。
- 最终严格探测要求九个 Skill 均返回非空可展示条目，实测九项全部 `SUCCESS`、各 1 条；真实浏览器纯公告问题仅调用问财并显示三条实际记录。全量 733 项收集结果为 724 passed、9 skipped；独立复审无 P0/P1，Python 编译、JavaScript 语法和差异检查通过。
- 边界：底层九 Skill 已可用，但既有 Fixture 研究矩阵、完整专题研究、优化、情景模拟和固定工作流仍需独立 LIVE service adapter；动态中文列到组合刷新标准字段的稳定映射尚未完成，不据此宣称全部产品功能真实化。

## 2026-09-14：聊天发送回归与本机模型密钥恢复

- 根因一：前端把 session truth 的 `DRIFT_DETECTED` / `INPUT_REQUIRED` 错当成所有聊天的发送硬门槛，导致请求在 `/api/v1/copilot/chat` 前直接返回。现在只有 `LOCKED` 前提会绑定画像和持仓；未锁定时可发送一般问答，并在审计提示中明确禁止个性化配置结论。
- 后端同步剥离未绑定 truth 的客户端画像、持仓、版本和历史，CopilotAgent 使用中性未核验上下文；概念型金融教育问题允许模型正文，实时行情、标的判断和个人组合建议仍要求真实工具。畸形 SSE 事件改为失败，不再静默保存空答案。
- 根因二：Windows 无认证本地模式原先只把页面填写的模型密钥保存在进程内，热重载即丢失。现在使用 DPAPI 加密的单机 `local:workbench` 槽，启用账户认证后仍按 owner 隔离；命名空间已隔离，避免与同名认证账户碰撞，API 不回读明文。
- 前端静态资源版本已更新，避免浏览器继续使用旧发送逻辑。真实浏览器在 stale truth 与显式 MOCK 下已完成发送、SSE 和答案渲染闭环；LIVE 请求已到达后端并明确报告当前未配置模型。真实模型密钥已在此前热重载中丢失，需在“更多 → 模型设置”最后重新填写一次，之后重启可恢复。
- 验证：项目 `.venv` 全量收集 `721` 项，结果 `712 passed, 9 skipped`；35 项聊天/会话前提/模型持久化定向回归通过；`node --check`、`compileall`、`git diff --check` 通过。系统 Python 3.14 的 OCR 字体环境会导致 3 项现金识别断言失败，但项目 Python 3.12 虚拟环境中 OCR 3/3 及全量测试均通过。

## 2026-09-14：本地可修复的真实化边界与密钥持久化

- 新增 Windows DPAPI 保护的 owner-scoped 密钥存储。个人模型配置先写入受保护文件再更新进程缓存，重启后按 owner 恢复；删除、损坏文件和错误密文均失败关闭，响应不包含明文密钥。
- 已启用账户身份绑定的 Windows 桌面入口使用 `data/private/prism-secrets.json`，可由 `PRISM_SECRET_STORE_PATH` 覆盖。文件位于既有 Git 忽略的 `data/private/`，只保存 DPAPI 密文；未认证开发模式保持进程内配置，非 Windows 环境不启用不安全的明文持久化回退。
- LIVE 模式对七类默认 Fixture 研究服务及固定合成工作流增加统一硬闸门，返回 `LIVE_RESEARCH_NOT_AVAILABLE`，不再让页面或 API 把 Fixture 结果带入 LIVE。MOCK 模式的显式演示/回归能力不变。
- 首轮独立三路审查发现 GET 模板、再平衡模板、离线评测和工作流标签仍有 Mock 旁路，同时发现密钥缓存跨实例失效、文件写入缺少跨进程锁及未认证 owner 可伪造。现已增加十个 GET/看板硬闸门、动态工作流 provenance、跨进程锁与唯一临时文件、DPAPI 明文缓冲擦除、每次读取持久层以同步轮换/删除，并只在身份绑定后启用持久化。
- 后续审查又定位到 OCR 缺价时使用内置静态价格并可确认到 LIVE 的旁路。现在 owner OCR 在 LIVE 下会用扶摇真实 A 股报价覆盖缺失价格、绑定观察时间并清除静态成本/行业推断；不受真实报价支持或请求失败时拒绝保存。两个确认入口也会拒绝仍带 `MISSING_OBSERVED_FIELDS` 的输入。
- 验证：新增保护存储、并发写入、跨应用重启/轮换/删除、owner 身份绑定、开发模式不落盘、十个 Fixture GET、工作流保存、八条执行拒绝及 LIVE OCR 报价/行业来源回归；全量 `718` 项收集结果为 `709 passed, 9 skipped`。Windows DPAPI 在认证账户下实际跨 `create_app()` 重启通过；真实扶摇请求返回 `600519.SH` 行情和 `510300.SH` 十条披露持仓，均为 `is_synthetic=false`；`compileall`、三个 JavaScript 语法检查、`git diff --check` 通过。
- 仍未完成：问财当前进程未配置，完整股票财务、基金指标、可转债数据和七类 LIVE 研究适配器不能在没有外部权限/字段契约时实现；这些入口现在明确不可用，不再以 Mock 冒充。

## 2026-09-14 — 真实模型工具调用与快捷按钮链路修复

- 根因是 OpenAI-compatible 接口将工具名称和 JSON 参数拆成 `tool_calls` 增量，而 Agent 只处理完整调用；现按调用索引组装并校验 JSON 对象，支持多个调用，畸形参数返回安全错误且不回显原文。
- Agent 对工具名、必填项、类型及额外字段执行白名单校验；LIVE 未实现或未知工具 fail closed，不再穿透 MOCK/Fixture。金融数据问题若模型只返回正文而未调用工具，拒绝展示未核验内容；多个工具先收集后统一生成，问财真实结果已接入响应合成。
- AUTO 在无模型配置时返回 `MODEL_NOT_CONFIGURED`，AUTO/LIVE 均要求工具数据同时处于 LIVE，只有显式 MOCK 才允许演示。个人模型配置现在同时覆盖聊天、自然语言画像和语义记忆；旧全局配置接口改为 owner 作用域并复用官方 HTTPS 地址白名单。
- 修复动态“研究 300750”等标签丢失 target 的旧输入框依赖；真实浏览器显示宁德时代 `LIVE_PRIMARY` 行情，扶摇请求 `is_synthetic=false`，无控制台错误。组合未实际刷新时，来源说明不再宣称已使用公告或语义检索。
- 验证：项目 Python 3.12 虚拟环境全量 `695 passed, 9 skipped`，跳过项为未启动的 PostgreSQL；Node 语法、Python 编译及差异检查通过。真实扶摇接口取得 300750 行情和 510300 最近一期披露持仓，均标记非合成。开发热重载后个人模型 Key 按既定安全设计被清空，因此本轮修改后的真实 LLM 端到端复测仍需重新填写 Key；分片协议、工具执行与失败闭合由回归测试覆盖。
- 独立三路审查确认并推动修复 LIVE→MOCK 穿透、参数泄露、多工具遗漏、问财结果遗漏和前端来源误报。仍未完成真实财务基本面、问财/SkillHub、默认 Fixture 研究服务替换与个人模型密钥跨进程持久化，不宣称主要功能已全部真实化。

## 2026-09-14 — 指数 K 线与个人中心信息架构修正

- 保留已配置的扶摇/iFinD A 股指数历史行情为主链路；为无凭据环境补充腾讯公开指数 90 日日线降级读取，并对日期、有限正数、OHLC 边界和重复交易日执行确定性校验。真实浏览器已取得上证指数 90 根日 K 线。
- AI 与工具数据状态移入右上角“更多”，不再常驻顶栏；主题切换同步移入该菜单，切换后继续按账户保存。
- 删除个人中心“外观与数据授权”和自然语言画像提案重复区块。持仓自动读取固定关闭，仅保留截图、文本和手动确认入口；行情数据固定启用，不再暴露可关闭开关。
- Node 语法、相关回归和全量测试通过；独立空数据库预览完成桌面与 390px 验收，390px 页面无水平溢出。原有 9 项 PostgreSQL 环境跳过保持不变。

## 2026-09-14 — 五项界面反馈修正

- 对话右栏正文与控件提高至 14px，标题 16px，统一回答详细度与偏好操作；保留原有灰白与橙色风格。
- 持仓明细右侧集中展示资产配置、风险预算。原行业饼图 CSS 覆盖环图 stroke/线宽导致不可见，现使用独立 allocation-slice 类；浏览器验证真实绘制颜色与 24px 线宽。
- 大盘四个指数使用显式按钮，点击切换查询；加入响应顺序保护，行情与行业表格统一卡片排版。深证成指切换实测返回对应行情与 63 根日线。
- 个人中心改用分行设置、主题选择与授权开关，修复账户初始化前加载授权导致长期“读取中”；右上角分别展示 AI/工具数据状态并打开统一配置面板，普通用户仍受原全局模式切换权限限制。
- 17 项相关回归与 Node 语法检查通过；桌面和 390px 浏览器验证，原数据库未修改。本轮没有重跑后端全量回归。

## 2026-09-14 — PRD 页面与持仓链路修复

- 882c7d8 为 9 月 10 日界面提交，PR #1 于 9 月 13 日合并；遵照用户要求保留 PR 后的侧栏、卡片与橙色强调风格。修复未测评时导航隐藏，首次欢迎引导保留浏览入口；新增独立空数据库预览工具。
- 六项功能按钮填入输入前缀；Marked 与 DOMPurify 本地构建支持安全 Markdown；等待状态移至发送按钮左侧，支持取消与超时，审计详情置于回复后。新增静态资源版本与首页重验证，避免继续加载旧界面。
- 恢复截图/文字导入入口，将原分析视图整合进持仓页；增加手动添加、删除及 CSV 导出。后端 Decimal 计算市值、现金分布与盈亏，成本或昨收缺失保持不可用；删除空组合及模式冲突有明确处理。非演示目录内的有效沪深股票可确认持仓，未知行业保持 Unclassified。
- 普通账户可从更多菜单配置官方模型服务、测试连接和恢复默认；个人密钥仅存在服务端当前进程内存，不返回浏览器。开发者更多菜单提供独立 AI 模拟开关，模拟回复明确标识，不伪造真实调用。
- 现有 HITHINK_FINANCE_API_KEY 受控调用成功；A 股指数专用接口修复上证指数误用平安银行报价。浏览器取得 63 根上证日线及 12 行行业观察数据。未证实独立 iFinD 账户登录或港美股权限；不等同于已完成整个 PRD。
- 验证：全量 682 passed、9 skipped、2 项既有依赖警告；随后补丁相关 19 项通过。实际浏览器验证 Markdown、前缀、文字导入、添加持仓、分布图、配置入口、真实指数与行业；390px 无页面水平溢出。测试采用临时 SQLite，原用户数据库未修改。截图 OCR 准确率和真实模型质量未在本轮验收。

## 2026-09-14 — Windows 一键启动与依赖安装修复

- 根因包含三层：根目录同时存在功能脚本与纯转调脚本；默认 Python 3.14 超出 `rapidocr-onnxruntime 1.4.4` 的 `<3.13` 支持边界，但项目错误声明为 `Python >=3.11`；原 BAT 补装时遗漏 `web` extra，并在括号块内使用预展开的 `%errorlevel%`，可能在安装成功后仍误报失败。
- 保留唯一入口 `start.bat`，删除重复中文别名。启动器现在固定使用仓库 `.venv`，首次运行依次选择 Python 3.12、3.11 创建环境，安装 `.[web]`，并对 FastAPI、Uvicorn、multipart、Pillow 与 RapidOCR 执行完整导入检查。BAT 明确采用 CRLF，项目和锁文件的 Python 范围同步为 `>=3.11,<3.13`。
- 验证：默认 Python 3.14 安装会明确返回版本不兼容；全新 Python 3.12 虚拟环境实际完成依赖安装及导入探针；`start.bat` 实际拉起 Uvicorn，`/api/health` 返回 HTTP 200。全量测试 `676 passed, 9 skipped`，保留 2 条既有依赖弃用警告；差异检查通过。

## 2026-09-08 — 工作流双视图与结构化事实黑板

- X6 画布与流水线卡片共用图模型，按拓扑阶段显示依赖和执行状态；环路/未知依赖显示 BLOCKED，未保存修改禁止套用旧版本执行结果。范围仍为固定八节点 MOCK 演练。
- 黑板展示已锁定画像、持仓、现金与来源；新前提须先预览，再携带事实指纹及版本确认，源数据变化返回冲突。新增结构化事实与明确买入禁投检查，Decimal 比较数量/金额/画像值，无法判断的约束保留 UNVERIFIED；不代表完整适当性或通用自然语言幻觉检测。
- 分析中断在本页保留最多 20 条定位链接，刷新及切换账户清空。确认失败在弹窗内显示，现金使用金额单位。模式切换恢复持仓后同步刷新黑板标签。
- 全量 655 passed、9 skipped、2 条既有依赖弃用警告（63.67 秒）；本次未启动临时 PostgreSQL，其九项测试明确跳过。最后补入模式切换标签刷新回归，相关 32 项全部通过。Node 语法、X6 构建与源文件差异检查通过。
- 浏览器完成双视图切换、八节点运行、环路阻断、未保存版本拒绝、黑板 20%/25% 错误及正确值核验、预览取消；未保存测试环路或覆盖账户。收尾遇启动探测 UPSTREAM_TIMEOUT，使用现有重试入口后行情和基金披露均 VERIFIED，恢复 LIVE；原五项证券及 28,000 元现金仍在 SQLite，未改变持仓。
- README/TODO/部署文档与任务计划同步。正式问财授权、券商环境、真实模型质量、外部长期 SLA、任意实时工作流及逐句幻觉检测仍待验收；PPT、视频、提交版测试报告继续排除。

## 2026-09-08 — PostgreSQL 可选后端及最终验收

- 新增 PostgresDecisionEventStore 与 PRISM_DATABASE_URL 选择入口，显式连接失败拒绝启动且不回退 SQLite；异常不包含 DSN、密码或原始数据库正文。复用现有领域契约与 owner/摘要校验，以事务 advisory lock 保留跨连接 CAS；迁移 DDL 与版本登记原子提交，失败回滚并释放连接。
- 在临时目录运行真实 PostgreSQL 17.11，仅监听 127.0.0.1:55439，未迁移或切换用户 SQLite 主库。九项 PostgreSQL 回归覆盖所有存储契约、应用重开、跨连接 CAS、并发迁移、锁超时后恢复、批量回滚及损坏检测。
- 最终全量 638 passed、2 条既有依赖弃用警告，56.39 秒；该次设置 PRISM_TEST_POSTGRES_DSN，无 DSN 时九项 PG 测试明确跳过。九个固定评测用例全部通过。Node 语法、X6 构建、Python 编译与隔离 wheel 构建通过，wheel 包含迁移和第三方许可，不含私有运行文件。
- README/TODO 区分历史阶段和当前状态，修正扶摇 LIVE、画像/记忆、认证、数据库及 P3 边界。真实账户再次生成调仓测算：100 股茅台减持，费用 99.51，假设现金 10.55%，HHI 3186.53 > 2500，维持 REVIEW_REQUIRED；没有执行交易或覆盖持仓。
- 本地认证可选但主服务尚未设置用户密码；原 SQLite 保留。正式问财授权、券商环境、真实模型质量及外部长期 SLA 仍未具备验收条件；完整 P3 双视图和通用幻觉检查未宣称完成。PPT、视频与提交版测试报告按用户要求排除。代码仅本地提交，未自动推送；保留原 README 链接及未跟踪 PRD 指南。

## 2026-09-08 — 顶部风险画像标签一致性

- 浏览器发现默认业务角色标签 R3 与已确认问卷的成长型 73 分不一致。顶部和首页标签现在读取已确认的有效风险画像，未读取或未确认时显示待确认问卷；不再用业务角色默认文案表示正式风险等级。
- 全量工作流/记忆批次 626 项通过；本次标签及相关前端 6 项通过、Node 语法通过。浏览器刷新后显示已确认成长型 73 分，与当前画像一致。
- 继续核对并修正行业全景、证据说明和聊天风险标签的六处相同来源错误；前端行为回归 8 项通过，刷新后两处主标签一致，浏览器无错误。

## 2026-09-08 — 历史记忆检索与工作流编排

- 历史检索只读取 owner 最近 100 条显式保存记录；配置模型时排序候选 ID 与已存在字段，无模型时标注有限关键词匹配。超时、越界输出或错误会降级并关闭生成器，拒绝查询凭据；输出携带来源、时间、内容哈希与 HISTORICAL_ONLY，不隐式恢复财务状态。
- 工作流采用 AntV X6 3.1.8，复用既有八节点合成研究执行器。只开放位置与依赖，服务端保留来源、操作与验证规则；定义追加版本、预期版本冲突拒绝，环路和预算校验在服务端，超时取消执行。前端 bundle 及第三方许可证入库，可用 npm run build:workflow 重建。
- 验证：新增及相关记忆、工作流 28 项回归通过；浏览器完成画布显示、拖动、依赖编辑、保存、指定版本运行 COMPLETED，以及历史检索空结果路径，浏览器错误日志为空。实际模型相关性与真实数据工作流尚未验收；运行轨迹仅返回当前页面。

## 2026-09-08 — 会话分析前提与流式错误处理

- 新增 session_truth 版本表，服务端从已确认问卷、有效画像、当前模式持仓派生事实，不接受客户端自填事实。owner/session 隔离，摘要校验、预期版本 CAS 与追加修订避免静默覆盖。
- 选择锁定的会话在聊天前和流式输出各步检查当前事实；版本、持仓引用或模式漂移阻断，重新确认生成新版本。聊天使用服务端锁定画像与持仓覆盖客户端描述；未启用锁定的旧 API 仍兼容。
- 页面显示前提状态并提供显式锁定/更新入口，真实页面已锁定当前账户第 1 版。该能力检测结构化前提漂移，不宣称识别所有自然语言错误或收益幻觉。
- 修复 SSE error 被忽略和提前断流误显示完成；失败答案不入聊天历史，释放 reader 和服务端生成器。模型错误仅显示安全状态/异常类别，不透传上游正文。
- 验证：前提持久化、隔离、摘要破坏、版本冲突、持仓变化、中途漂移及生成器关闭均通过；相关 30 项通过，新增 Node 流错误/截断行为回归通过。

## 2026-09-08 — 自然语言偏好提取

- profile-extractions 复用已配置服务端模型，只返回画像槽位、逐字原文及置信度；数字必须在引用原文中，矛盾字段留空，超时、超长或无依据输出拒绝。评分与风险预算仍由确定性服务完成。
- 无模型配置时采用明确标注的有限措辞识别，拒绝周边否定、第三人称与假设表述，不伪装成通用理解。原文仅用于当前请求，不写入存储。
- 画像页面增加候选提取与冲突审阅，使用已确认问卷比较；提案确认结果不替代正式 19 题问卷或改变有效等级。浏览器实测长期投资/现金需求/15% 回撤提取，期限与原 25% 回撤形成两项显式冲突，原 C4 保持。
- 单元及相关前端回归 27 项通过，Node 语法通过；模型结构输出以故障注入验证，本机没有配置模型，不宣称真实模型泛化验收完成。

## 2026-09-08 — 真实 HTTP 负载观测

- 新增只读 TCP/HTTP 压测入口 tools/http_load_test.py，保留样本窗口、分位延迟、HTTP 失败和连接异常计数；拒绝 URL 内嵌密码，不输出响应正文或原始异常。
- 本地 8000 实测 100 并发：08:28:19 UTC 健康检查 100/100 成功，P95 939.649ms；08:28:30 UTC 当前持仓读取 100/100 成功，P95 326.038ms。没有向扶摇执行 100 并发查询。
- 失败分类与分位数单测通过；样本始终不标记 SLA 验收，长期 99.9% 和供应商性能继续待验证。

## 2026-09-08 — 本地身份隔离、审计与备份

- 依照用户本地运行目标，新增可选标准 HTTP Basic；身份在服务端绑定 owner，普通账户无法伪造其他 owner、修改全局配置或指定聊天模型出站地址。账户文件只保存随机盐和 scrypt 摘要，CLI 交互录入密码，不生成公共默认账户。
- 认证模式在初始化前取得身份，隐藏示例账户和成员管理入口，聊天、密钥、界面备注仅页内保留；已确认问卷和持仓仍由服务端恢复。当前用户 8000 页面复测恢复 5 笔持仓与 C4 画像，认证关闭兼容正常。
- 新增 007 访问审计迁移和 owner 范围查询；仅记录路径模板、状态码、时间和 owner；独立只读复核发现的 500 漏记与成员模型地址入口已修复。
- 新增 SQLite 在线备份／恢复工具，目标路径必须不存在，恢复完整性校验并保留原库。docs/local-deployment.md 写明本地认证、开发模式、凭据与恢复边界。
- 验证：第一次全量 591 项通过；随后新增 500 回归及模型地址限制，相关 27 项通过，Node 语法和差异检查通过。没有启用用户主实例认证或替用户设定密码；不宣称公网认证、PostgreSQL或防篡改审计已完成。

## 2026-09-08 — 剩余缺口执行：现金目标与交易后风险复核

- 目标请求增加兼容字段 minimum_cash_pct、confirmed_profile，原调用保持默认语义；当前界面传入已确认画像及体检现金下限，避免用旧问卷重建另一套风险等级。
- 先应用现有风险上限，再从最大非现金桶释放不足的现金下限权重；缺少现金桶或上下限冲突返回 BLOCKED，所有目标仍闭合为 100%。
- 已确认画像的减持目标按现有交易单位向上满足目标数量，并接受后续费用、换手和风险复核；买入预留现金下限与费用。未携带画像的旧接口保留原向下取整行为。
- 用实际可执行数量和费用构建只用于计算的假设持仓，重算完整体检及风险预算；任何不满足项保持 REVIEW_REQUIRED。返回 post_trade_health，界面明确未修改实际账户持仓。
- 当前用户五笔持仓浏览器复测：100 股茅台减持测算，费用 99.51 元，现金 10.55%；HHI 3186.53 > 2500，仍需复核。该规则不是收益最优或全局最优求解器。
- 验证：全量 587 项通过，2 条既有依赖弃用警告；Node 语法与差异检查通过。

## 2026-09-08 — 剩余缺口执行：数据源受控恢复

- 用户授权执行剩余缺口，排除正式 PPT、视频、提交版测试报告；明确本地运行、准备远端代码交付。清单为 docs/plans/2026-09-08-gap-closure.md。
- 复现已配置扶摇但启动探测失败后前端拒绝重试；Provider 原来丢弃错误类型，只留下 PROBE_FAILED。保留安全错误码并允许通过既有模式切换接口重新探测，不自动启用未验证数据。
- 故障注入验证 UPSTREAM_TIMEOUT、权限错误保留，重试成功清除旧错误；相关 25 项测试及 Node 语法检查通过。当前 8000 浏览器点击重新验证后于 16:05:49 +08:00 返回 LIVE / VERIFIED，两项能力均可用。
- 瞬时 UPSTREAM_UNAVAILABLE 已恢复，但没有历史网络链路记录，不将其断言为密钥错误或长期上游故障。

## 2026-09-08 — 零交易调仓误标就绪

- 在用户当前 8000 服务复现：茅台权重 52.19%、目标 50.00%，约 25 股理论减持量按现有 100 股单位向下取整后为 0。后端将动作改为 HOLD 却未写入执行问题，返回 PASS；主卡固定绿色 CALCULATED，明细不显示原因。
- 取整归零且超出死区时返回 REVIEW_REQUIRED，并保留目标及未执行原因；主卡与明细显示状态、原因和实际变动字段。现金作为交易余额而非直接买入动作解释。
- 通过兼容字段 minimum_cash_pct（旧调用默认 0）将体检现金下限传入再平衡，确定性比较目标现金及扣费后现金。本账户目标现金 4.05% < 5.00%、实际现金 1.86% < 5.00%，均明确列为复核问题，不能将零交易解释为风险解除。
- 保留原数量算法，未擅自将不足整手的理论减持放大至 100 股。目标优化器仍只按既有上限规则分配，尚未实现现金下限与整手约束的联合修复；本次完成安全状态及可解释性修复，不宣称已生成可解除全部风险的方案。
- 验证：新增 2 项后端回归，扩展前端零交易原因测试；全量 584 项通过，后续文案调整相关 28 项通过，Node 语法及差异检查通过。用户当前浏览器路径确认返回 REVIEW_REQUIRED 和三个具体问题；不修改其持仓与问卷。

## 2026-09-08 — 持仓持久化与用户路径复核

- 根因：文本持仓仅存前端内存；默认服务使用内存 SQLite；页面启动未恢复确认持仓。桌面入口改为 `data/private/prism.sqlite3`（可用 `PRISM_DB_PATH` 指定），工厂测试保持内存隔离。当前持仓按 owner 和 LIVE/MOCK 分开保存，保留数量、成本、现金及确认时点，不保存截图原图。
- 页面恢复在问卷和运行模式加载后执行，拒绝过期响应覆盖新确认数据；模式切换清除旧持仓、草稿与标签，切回原模式恢复对应记录。保存成功后的体检失败单独反馈。
- 浏览器复现并修复风险画像页面“添加持仓”弹窗被隐藏父容器遮蔽；回归复现第二份截图确认因重复快照编号返回 409，改为每次导入独立编号，同时保留相同截图重复确认的幂等性。修正 OCR 高置信度被误述为风险核验通过的文案。
- 独立 SQLite 测试服务通过真实页面完成 19 题问卷、用户五笔原文导入、完整刷新、服务进程重启、体检、压力测试、宁德时代行情研究、调仓测算、模式往返与截图确认。五笔原文现金 28000 元，刷新和重启后总资产均保持确认时的 1505235 元；外部报价随时间变化。
- 验证：全量 582 项测试通过；随后模式标签和模式快照一致性补丁的相关 28 项回归通过；Node 语法及差异检查通过。仍有 2 条既有依赖弃用警告。问财刷新和财务字段缺口保留明确提示，不以合成数据补齐。旧版本已丢失的内存数据无法追溯恢复，需要重新确认一次。

## 2026-09-08 — 持仓取价瞬时超时处理

- 用户报告扶摇超时；现场五只股票单项请求均成功，约 0.4–0.6 秒。代码确认每只股票总等待上限为 1.5 秒，原导入在任意一次取价失败后立即中止；未取得用户当次超时的底层网络记录，不认定上游持续故障。
- 仅对导入取价的超时、上游不可用增加一次重试，保留原单次超时上限；权限、凭据及数据校验错误不重试。最终失败指出证券名称和代码，提示稍后重试或补填现价，不用成本价/合成价格替代。
- 回归覆盖瞬时失败恢复、连续超时停止、凭据错误不重试，相关 38 项测试通过；用户完整五笔原文在 LIVE 接口约 2.6 秒返回 SUCCESS，现金 28000 元、资产 5 项。

## 2026-09-08 — 自然语言持仓千位分隔符修复

- 使用用户原文在 8000 页面复现“解析出错: 接口请求失败”：数字提取未处理千位逗号，1000/2000 股变成 0 股、1500 股变成 500 股、1680 元成本变成 1 元、28000 元现金变成 0，确认接口因此拒绝数量。
- 在提取前仅去除合法千位分组内部的英文逗号，保留普通标点和小数；沿用既有股票行情及持仓校验路径。
- 新增原文、无分隔符对照和多组千位小数 3 项回归；原文测试修复前失败、修复后通过。相关 37 项测试通过，2 条既有依赖弃用警告，差异检查通过。
- 浏览器在已核验 LIVE 模式下重新提交原文，成功确认 5 项资产及 28000 元现金；各股数量为 600、1000、800、2000、1500，成本为 1680、225、48、58、42。行情价格随查询时点变化，买入均价不作为现价。

## 2026-09-08 — 真实数据用户流程缺陷修复

- 在独立内存数据库服务中完成 19 题问卷、文本持仓导入、体检、股票与基金研究、聊天、调仓拒绝和压力测试拒绝的浏览器体验；未增加业务功能。
- 修复未确认画像/持仓时自动采用示例数据、首页持续计算中、辅助视图固定暴露值，以及仅 HHI 超限导致行业环图异常的问题。
- 文本导入保留用户填写的现价和成本；LIVE 缺少股票价格时使用真实报价，基金缺少现价时要求复核。修正 ETF 数量和代码误识别；LIVE OCR/文本确认不附加合成基金行业分布。
- 股票财务空值与基金行业空值显式保留；ETF 使用基金接口；聊天按用户代码查询并引用本次工具的数据模式。研究请求过期后不覆盖新上下文。
- 缺失穿透数据时，调仓显示后端拒绝原因；压力测试返回带说明的 422，避免服务器 500。基金底层暴露目标不得直接变成账户交易清单。
- 验证：全量 572 项测试通过，2 条既有依赖弃用警告；15 项新增回归覆盖上述边界，Node 语法、Python 编译及差异检查通过。浏览器验证 100 股 × 1400 元 + 20 万现金 = 340000 元；510300 基金导入 80000 元且未分类暴露保留；真实基金聊天已返回 510300，而非旧代码 512480。
- 数据边界：扶摇行情及基金定期披露可用，问财组合刷新仍不可用；财务字段与完整基金行业穿透缺失仍需复核。未验证实盘交易、外部大模型账户及生产 SLA。
- 原有 README.md 与 docs/prd-integration-guide.md 工作区内容保留，不纳入本轮提交。

## 2026-09-07 — Engineering backlog TASK-01 至 TASK-05

### Decisions & Accomplishments

- 行情自动建档改为 Tencent、Sina、静态底稿三级降级链，设置单级 1.5 秒、总计 2.0 秒预算，并输出供应商层级、延迟与新鲜度；删除网络失败后伪造行情和财务数据的旧分支。
- OCR 增加证券简称模糊纠错、市值偏差 0.5% 校验、组合权重 1% 容差、逐行置信等级和零股复核提示。
- 调仓服务增加 A 股整手约束、零股清仓规则以及印花税、过户费、最低佣金和净换手成本；缺少报价的新增标的明确进入复核态。
- 新增五行业自定义冲击接口和滑块，由 Python 确定性计算组合损益、波动率及 95% 单日 VaR；前端增加 Micro-Store，并将调仓与情景卡片接入后端结果。
- 修复分析依据弹窗被隐藏画像弹窗包裹的问题；行业环图点击结果改为紧邻图表呈现。按用户要求保留侧边栏与页面分区。

### Verification

```text
.venv\Scripts\python.exe -m pytest -q
# 498 tests passed; 2 dependency deprecation warnings
node --check app/api/static/app.js
rg "innerHTML|outerHTML" app/api/static/app.js
# no matches
Browser: custom stress slider recalculated loss/volatility/VaR; sector click rendered inline detail; evidence lineage modal opened.
```

## 2026-09-02 — Frontend product UX pass completed

### Decisions & Accomplishments

- Reframed the default workbench around three user tasks: portfolio health check, asset research, and rebalancing plan generation.
- Moved detailed research, evidence, history, evaluation, and local owner controls behind an explicit “更多工具” path while preserving their existing IDs and API flows.
- Replaced internal-first labels in the primary task flow with user-facing explanations of inputs, outputs, boundaries, and next actions; kept technical identifiers available in the detailed workbench for audit use.
- Added responsive topbar and detailed-workbench rules, including mobile wrapping for long evidence and receipt identifiers; no horizontal overflow remains at the tested 390px viewport.

### Verification

```text
python -m pytest
# 472 passed, 1 warning
node --check app/api/static/app.js
git diff --check
Browser: default and 390px viewport; default expert workspace hidden, explicit expand/return path, health-check task, analysis drawer, and no console errors.
```

## 2026-09-02 — P2 Milestones (Phase 34, 35, 36, 37) Completed & Accepted

### Decisions & Accomplishments

- **Phase 34 Recommendation History**:
  - Implemented immutable decision receipt query and comparison contracts in `app/history/contracts.py`.
  - Created `RecommendationHistoryService` in `app/service/recommendation_history.py` providing owner-isolated receipt history and audit trail comparison.
  - Exposed `GET /api/v1/advisor/recommendation-history` and `POST /api/v1/advisor/recommendation-history/compare`.
  - Added unit and integration tests (`tests/unit/test_recommendation_history.py`, `tests/integration/test_phase34_recommendation_history.py`).

- **Phase 35 Portfolio Rebalancing**:
  - Implemented deterministic portfolio rebalancing contracts in `app/rebalancing/contracts.py`.
  - Created `PortfolioRebalancingService` in `app/service/portfolio_rebalancing.py` implementing exact Decimal conservation, deadband threshold suppression (0.50%), turnover cap checks, and liquidity-ordered step execution (SELL before BUY).
  - Exposed `GET /api/v1/advisor/rebalancing-template` and `POST /api/v1/advisor/rebalancing-runs`.
  - Added unit and integration tests (`tests/unit/test_portfolio_rebalancing.py`, `tests/integration/test_phase35_portfolio_rebalancing.py`).

- **Phase 36 Evaluation Dashboard**:
  - Implemented evaluation scorecard and case report contracts in `app/evaluation/contracts.py`.
  - Created `EvaluationDashboardService` in `app/service/evaluation_dashboard.py` running the versioned `eval_cases/` suite and tracking Pass Rate, Profile Alignment, Evidence Coverage, 0.00% Hallucination, and P50/P95 Latency.
  - Exposed `GET /api/v1/advisor/evaluation-dashboard-summary` and `POST /api/v1/advisor/evaluation-dashboard-runs`.
  - Added unit and integration tests (`tests/unit/test_evaluation_dashboard.py`, `tests/integration/test_phase36_evaluation_dashboard.py`).

- **Phase 37 Advanced Explainability**:
  - Implemented full-chain explainability contracts in `app/explainability/contracts.py` (Causal DAG, Key Decision Drivers, Counterfactuals, Invalidation Triggers).
  - Created `AdvancedExplainabilityService` in `app/service/advanced_explainability.py` generating deterministic causal trees, quantified contribution percentages, counterfactual scenario rules, and invalidation thresholds.
  - Exposed `GET /api/v1/advisor/explainability-template` and `POST /api/v1/advisor/explainability-runs`.
  - Added unit and integration tests (`tests/unit/test_advanced_explainability.py`, `tests/integration/test_phase37_advanced_explainability.py`).

- **Workbench UI & Integration**:
  - Localized 4 dedicated interactive panels in `index.html` (`#recommendation-history`, `#portfolio-rebalancing`, `#advanced-explainability`, `#evaluation-dashboard`).
  - Added CSS styling in `styles.css` for metric scorecards, rebalancing tables, action badges, and driver bars.
  - Integrated safe DOM-based event handlers and async API callers in `app.js` with zero `innerHTML` and zero external CDN script dependencies.
  - Passed all 463 automated unit & integration tests (`python -m pytest`) and verified 100% case pass rate in `python -m tools.evaluate_mvp --json`.

## 2026-09-02 — Phase 33 Scenario Simulation (P2) Accepted

### Decisions & Accomplishments

- Implemented the deterministic, owner-isolated Scenario Simulation engine in `app.simulation` and `app.service.scenario_simulation`.
- Integrated 4 bounded overlay scenarios (`BASELINE_READY`, `TIGHTER_TECH_CAP`, `TOP_ASSET_TRIM_10PP`, `LOOKTHROUGH_PARTIAL`) without mutating real observed assets.
- Enforced strict three-state degradation (`READY`, `REVIEW_REQUIRED`, `BLOCKED`) without fabricating missing values or zero diffs.
- Exposed `GET /api/v1/advisor/scenario-simulation-template` and `POST /api/v1/advisor/scenario-simulation-runs` with defensive identity and contract validation.
- Localized and wired the `#scenario-simulation` Chinese workbench panel with scenario selector, baseline vs simulated cards, metric diffs table, and deterministic invalidation lists.
- Added browser end-to-end smoke test `tools/scenario_simulation_smoke.cjs` and passed all 450 automated tests.
- Formally accepted Phase 33 (`docs/plans/2026-09-02-mvp-phase-33-scenario-simulation.md` marked ACCEPTED).

## 2026-09-01 — Independent repository foundation

### Decisions

- `Prism.md` is the project master document; no duplicate `PROJECT.md` will be created.
- Prism is an independent repository. `tradeeye-copilot` and `TradeEye` remain read-only upstream references and are not runtime dependencies.
- The first product slice is portfolio-to-adjustment decision support for a technology-fund-concentrated user, not a broad financial chat clone.
- The runtime will be a modular monolith with a bounded structured research DAG. LLM nodes do not calculate financial facts or bypass deterministic profile, portfolio, risk and compliance engines.
- Product differentiation is an auditable personalized adjustment delta: the user can see which profile constraint changed the recommendation, the quantified pre/post effect, the evidence chain and the invalidation conditions.
- Fund/ETF look-through analysis moves into P0 because the flagship scenario depends on it. The load-test harness also moves forward to the Provider/foundation phase.

### Upstream evidence

- `tradeeye-copilot` at `1675a87`, equal to `origin/main`, clean: 283 tests passed.
- `TradeEye` at `8a1bd8c`, equal to `origin/main`, clean: 172 tests passed.
- Reusable code and non-reusable strategy/storage boundaries are recorded in `docs/reuse-matrix.md`.
- Neither upstream root exposed a `LICENSE`, `COPYING`, or `NOTICE` file during the current inspection; provenance remains a submission gate.

### Implemented

- Initialized Git on branch `main`.
- Updated the master specification to identify `Prism.md`—not a duplicate `PROJECT.md`—as the execution entrypoint.
- Added project metadata, repository hygiene files and a truthful README.
- Added ADR-0001, implementation architecture, Reuse Matrix, Evidence Contract and a durable foundation plan.
- Added strict immutable Pydantic contracts for Evidence, Fact, Finding, Recommendation and DecisionTrace.
- Enforced timezone-aware retrieval timestamps, non-zero-vs-missing semantics, reference closure, matching fact/evidence values and periods, and independent compliance states.
- Allowed missing evidence to explain a `BLOCKED` decision while preventing it from supporting actionable recommendations.

### Verification

```text
python -m pytest
8 passed
```

This verifies only the initial domain contract. No real SkillHub request, financial recommendation, browser workflow, concurrency target or availability target is claimed yet.

### Open constraints

- Competition-specific SkillHub interface and usage authorization are not present in the repository.
- The scoring appendix referenced in the brief is not present in the repository.
- Storage, Provider, profile, research, portfolio, risk, compliance, API and Web workbench remain unimplemented.

## 2026-09-01 — Gemini MVP Phase 1 delegation contract

### Decision

- Gemini may execute the overall MVP route one accepted phase at a time; it does not own or rewrite the route in `Prism.md`.
- The first delegated phase is narrowed to the fixture-first Provider boundary. Live SkillHub, storage, profile, research, portfolio and UI are explicitly excluded.
- Each Gemini phase must run on an isolated branch/worktree, satisfy an executable acceptance contract, create a local commit without pushing, and return evidence for independent review.
- Provider call identity is split into a per-call `request_id` and a deterministic semantic `request_fingerprint`; credentials are excluded from both fixtures and fingerprints.

### Artifact

- Added `docs/plans/2026-09-01-mvp-phase-1-provider-protocol.md` as the copy-ready Gemini execution contract.
- The contract defines allowed files, four-state invariants, fixture data, timeout/redaction behavior, Evidence conversion, a 100-request isolation smoke test, stop conditions and the required handoff format.

### Current evidence boundary

- This change is planning only. No Provider implementation or real external request has been added.
- Phase 1 remains incomplete until Gemini's implementation is independently reviewed and accepted.

### Verification

- Existing baseline: `python -m pytest` -> 8 passed.
- Python compilation: passed.
- Local Markdown link validation: passed.
- Staged diff check: passed.

## 2026-09-01 — MVP Phase 1 fixture-first provider protocol

### Decisions

- Implemented the fixture-first Provider Protocol strictly adhering to `docs/plans/2026-09-01-mvp-phase-1-provider-protocol.md`.
- Enforced strict four-state execution invariants: `SUCCESS`, `PARTIAL`, `EMPTY`, and `FAILED` cannot be interchanged or masqueraded.
- Separated per-call correlation (`request_id`) from deterministic canonical SHA-256 semantic query fingerprints (`request_fingerprint`).
- Hardened contract safety based on review feedback:
  - Added `FrozenDict` deep immutability to prevent runtime parameter mutation and fingerprint drift;
  - Added recursive forbidden key detection (`_find_forbidden_key`) traversing nested dictionaries and sequences;
  - Enforced per-record required field validation in `SUCCESS` (requiring all records to have all required fields with non-None values);
  - Enforced veracity checking on `PARTIAL.missing_fields` (ensuring missing fields were actually requested and actually missing in records);
  - Added record identity to `evidence_id` (`ev:{provider}:{source}:{record_identity}:{field}:{period}`) to prevent duplicate Evidence IDs across multiple records and ensure DecisionTrace closure;
  - Added fixture template validation and duplicate fingerprint detection at FixtureProvider initialization.
- Created purely synthetic, credential-free fixtures covering all four result states.
- Normalization safely converts `SUCCESS` to `VERIFIED` Evidence, `PARTIAL` to `PARTIAL` Evidence with quality notes, and `EMPTY`/`FAILED` to zero Evidence (preventing false zeros).
- Standard library `asyncio` execution budget wrapper maps timeouts and internal errors safely without leaking stack traces or credentials.
- 100-concurrent request in-memory smoke test verified request ID isolation and fingerprint stability.

### Implemented

- `app/providers/contracts.py`: ProviderOperation, ProviderStatus, ProviderIssueCode, FrozenDict, ProviderRequest, ProviderRecord, ProviderIssue, ProviderResult, FinancialProvider protocol, and validate_result_for_request.
- `app/providers/fingerprint.py`: canonical JSON request dictionary, SHA-256 fingerprinting, and recursive redaction.
- `app/providers/fixture.py`: FixtureFinancialProvider with in-memory fingerprint indexing, template validation, and deterministic execution.
- `app/providers/runtime.py`: execute_with_budget async wrapper with timeout and error mapping.
- `app/providers/normalization.py`: normalize_result_to_evidence converter to Evidence domain model with record-identity-aware Evidence IDs.
- `app/providers/__init__.py`: package exports.
- `tests/fixtures/providers/*.json`: synthetic test fixtures (fund_data_success, fund_data_partial, fund_data_empty, fund_data_failed).
- `tests/unit/test_provider_contract.py`, `tests/unit/test_provider_fingerprint.py`, `tests/integration/test_fixture_provider.py`: 35 new tests covering all 21 acceptance cases and 6 review hardening items (43 total tests in repo).
- `docs/provider-protocol.md`: comprehensive documentation of the provider protocol.

### Verification

```text
python -m pytest
43 passed in 0.33s

python -m compileall -q app
passed

python -c "from app.providers import FinancialProvider, FixtureFinancialProvider; print('provider-import-ok')"
provider-import-ok

git diff --check
passed
```

### Current evidence boundary

- Live SkillHub network requests, production credentials, storage persistence, user profiles, research DAG, and UI workbench remain un-implemented and are explicitly out-of-scope for Phase 1.

## 2026-09-01 — Phase 1 hardening and takeover

### Decisions

- Codex took over the phase gate after an independent review of Gemini's `68ed7ff` implementation. Phase 2 remains blocked until this hardening pass is independently verified.
- The original `JsonValue` semantics are preserved while adding recursive freezing; `FrozenDict` must reject non-JSON values and `ProviderRecord.units` must contain strings.
- `PARTIAL.missing_fields` must exactly account for requested fields missing or null in any record; issue-only partial results may keep the set empty when no required field is missing.
- Evidence IDs encode provider/source/record/field/period and request fingerprint, and duplicate effective record identities are rejected before creating Evidence.

### Implemented

- Added `docs/plans/2026-09-01-mvp-phase-1-hardening.md` with explicit scope, non-goals, design decisions, acceptance cases and stop conditions.
- Added regression tests for non-JSON values, deep nested sequence mutation, `|=`, unit types, omitted partial fields, duplicate record IDs, missing record identity, delimiter-safe IDs and cross-request ID isolation.
- Preserved fixture-first, offline-only behavior; no upstream, network, credential, storage or UI changes.

### Verification

```text
python -m pytest
50 passed

python -m compileall -q app
passed

python -c "from app.providers import FinancialProvider, FixtureFinancialProvider, FrozenDict; print('provider-import-ok')"
provider-import-ok

git diff --check
passed
```

Independent adversarial checks passed: actual PARTIAL omissions are rejected; non-JSON parameters are rejected; nested sequences and `|=` cannot mutate requests; duplicate record identities are rejected; delimiter-containing and cross-request Evidence IDs remain distinct.

### Current evidence boundary

- Phase 1 hardening was accepted in local commit `84bbe3b`; Phase 2 began only after that gate.
- Real external providers, credentials, production concurrency/SLA and all later product layers remain unimplemented.

## 2026-09-01 — MVP Phase 2 profile and portfolio contracts

### Plan and boundary

- Added `docs/plans/2026-09-01-mvp-phase-2-profile-portfolio-contracts.md` and committed it before implementation in `ae9c68c`.
- The phase fixes two input boundaries for the flagship vertical slice: deterministic user risk profiles with explicit extraction conflict confirmation, and raw owner-scoped position/fund/ETF imports.
- Portfolio analytics, exposure, risk budgets, recommendations, LLM/network access, persistence, API, UI and upstream changes remain explicitly out of scope.

### Implemented locally

- Added immutable, versioned `RiskQuestionnaire`, `ProfileExtractionProposal`, `ProfileConflict`, `ProfileDraft` and `RiskProfile` contracts.
- Added fixed Decimal scoring and fixed risk-level thresholds; maximum drawdown remains an independent user constraint.
- Added explicit `USE_QUESTIONNAIRE` / `USE_EXTRACTION` resolution with no silent overwrite and no raw natural-language field.
- Added immutable `Position`, `PositionSnapshot`, four-state `PositionImportResult`, safe import issues, raw `LookThroughHolding`, `FundHoldingSnapshot` and owner/parent-closed `PortfolioImportBundle` contracts.
- Added credential-free synthetic fixtures, unit反例 and integration tests.

### Current review evidence

- Final full suite: `69 passed` (the original 50 Phase 1/Evidence tests remain green).
- Compilation, import, `git diff --check`, fixture JSON parsing and import checks passed after commit.
- Independent adversarial checks passed for stale conflicts, unknown resolutions, risk-level tampering, owner mismatch, deep tuple mutation, four-state misuse, illegal weights and unknown fund parents.
- Phase 2 was accepted in the single local commit `0de0c43`; no Phase 3 implementation has started yet.

## 2026-09-01 — MVP Phase 3 look-through exposure plan

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-3` on branch `codex/mvp-phase-3-exposure-risk` from Phase 2 accepted commit `0de0c43`.
- Added `docs/plans/2026-09-01-mvp-phase-3-lookthrough-exposure.md` before implementation.
- The plan narrows this phase to deterministic base-currency direct/look-through attribution, residuals and data coverage; concentration, risk budgets and recommendations remain deferred.

### Current boundary

- No Phase 3 implementation or real data-source access has started.
- The Phase 3 plan is ready for implementation after its plan commit; Phase 2 artifacts remain unchanged.

## 2026-09-01 — MVP Phase 3 look-through exposure implementation

### Implemented locally

- Added immutable `ExposureContribution`, `ExposureReport`, `ExposureIssue` and `ExposureResult` contracts with complete/partial/failed invariants.
- Added deterministic Decimal attribution for direct positions, valid fund/ETF holdings and explicit unlooked-through residuals.
- Added non-base-currency and future-snapshot safety issues, fixed technology-sector classification, contribution closure and deterministic IDs.
- Added synthetic multi-position fixture and unit/integration counterexamples; no network, FX, LLM, persistence, risk or recommendation code was introduced.

### Current review evidence

- Final full suite: `79 passed` (Phase 1/2's 69 tests remain green).
- Compilation, import, `git diff --check`, fixture JSON/sensitive-field scan and post-commit independent adversarial checks all passed.
- Phase 3 was accepted in the single local implementation commit `f6a1af4`; the next concentration/risk plan must use a new worktree.

## 2026-09-01 — MVP Phase 4 concentration and risk-budget plan

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-4` on branch `codex/mvp-phase-4-concentration-risk` from Phase 3 accepted commit `f6a1af4`.
- Added `docs/plans/2026-09-01-mvp-phase-4-concentration-risk-budget.md` before implementation.
- The phase narrows the next slice to deterministic asset/sector concentration and profile-conditioned risk-budget assessment; correlation, liquidity, optimization and recommendations remain deferred.

### Current boundary

- No Phase 4 implementation or real data-source access has started.
- The Phase 4 plan is ready for implementation after its plan commit; Phase 1/2/3 artifacts remain unchanged.

## 2026-09-01 — MVP Phase 4 concentration and risk-budget implementation

### Implemented locally

- Added immutable concentration groups/reports/results with Decimal asset/sector aggregation, HHI, deterministic tie-breaking and upstream status propagation.
- Added versioned fixed `RiskBudget` rules selected by `RiskProfile` risk level and explicit `RiskBudgetBreach` / `RiskBudgetAssessment` states (`PASS`, `REVIEW_REQUIRED`, `BLOCKED`).
- Preserved unlooked-through and unknown data, enforced owner/profile/exposure closure, and added synthetic offline tests without recommendations or real data access.

### Current review evidence

- Final full suite: `92 passed` (Phase 1/2/3's 79 tests remain green).
- Compilation, import, `git diff --check`, fixture scan and post-commit independent adversarial checks all passed.
- Phase 4 was accepted in the single local implementation commit recorded by this worktree; the final commit hash is reported by `git log -1` and the handoff message. The next optimization/recommendation plan must use a new worktree.

## 2026-09-01 — MVP Phase 5 allocation-envelope implementation

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-5` on branch `codex/mvp-phase-5-minimal-adjustment` from the accepted Phase 4 worktree.
- Added `docs/plans/2026-09-01-mvp-phase-5-allocation-envelope.md` before implementation.
- The phase is limited to deterministic profile-conditioned constraint bands and per-constraint impact; it does not create executable recommendations or modify the Evidence Contract.

### Implemented locally

- Added immutable `AllocationBand`, `ConstraintImpact`, `AllocationEnvelope` and `AllocationResult` contracts with owner/profile/report closure and `READY`/`REVIEW_REQUIRED`/`BLOCKED` semantics.
- Added deterministic asset, sector, technology and unclassified bands using the fixed Phase 4 budget; partial inputs stay `UNRESOLVED`, and each impact is explicitly constraint-only without cross-dimension reallocation.
- Added a synthetic offline fixture, unit/integration counterexamples and `docs/allocation-envelope.md`; no network, credentials, LLM, persistence, API, UI, order, price, quantity or return calculation was introduced.

### Independent review evidence

- Full suite: `103 passed` (Phase 1–4's 92 tests remain green).
- `python -m compileall -q app`, allocation import, `git diff --check`, fixture JSON and source/fixture sensitive-field scans passed.
- Independent adversarial checks passed for deterministic repeatability, partial/failed propagation, stale/tampered budget breaches, blocked outputs and absence of recommendation/order/secret-shaped output fields.
- Phase 5 is accepted in this worktree after the above review; the next structured-research/cross-validation plan must use a new worktree.

## 2026-09-01 — MVP Phase 6 structured research and cross-validation plan

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-6` on branch `codex/mvp-phase-6-research-cross-validation` from the accepted Phase 5 worktree.
- Added `docs/plans/2026-09-01-mvp-phase-6-research-cross-validation.md` before implementation.
- The phase narrows structured research to scalar observation contracts, four-state node results and lineage-aware validation; live providers, orchestration and Evidence/Finding conversion remain deferred.

### Implemented locally

- Added immutable `ResearchObservation`, `ResearchNodeResult`, `ValidationClaim`, `CrossValidationResult` and safe issue contracts.
- Added deterministic equality/lineage validation: duplicate lineage rows count once, no-lineage rows cannot prove independence, non-VERIFIED and scope-mismatched observations stay visible but cannot support a claim, and conflicts become `UNRESOLVED`.
- Added synthetic offline fixture, unit/integration counterexamples and `docs/research-cross-validation.md`; no network, credentials, LLM, provider adapter, DAG, persistence, API, UI or recommendation path was introduced.

### Independent review evidence

- Full suite: `122 passed` (Phase 1–5's 103 tests remain green).
- `python -m compileall -q app`, research import, `git diff --check`, fixture JSON and source/fixture sensitive-field scans passed.
- Independent adversarial checks passed for repeated-lineage de-duplication, no-lineage insufficiency, support/contradiction conflicts, non-VERIFIED exclusion, scope mismatch, partial/failed nodes, forged result rejection, stable IDs and absence of recommendation/order/secret-shaped output fields.
- Phase 6 is accepted in this worktree after the above review; the next bounded-orchestration/Evidence-integration plan must use a new worktree.

## 2026-09-01 — MVP Phase 7 bounded orchestration plan

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-7` on branch `codex/mvp-phase-7-bounded-orchestration` from the accepted Phase 6 worktree.
- Added `docs/plans/2026-09-01-mvp-phase-7-bounded-orchestration.md` before implementation.
- The phase narrows orchestration to a pure, owner-scoped DAG/run state contract with explicit budget, deadline, dependency and degradation semantics; it does not execute a Provider or Agent.

### Implemented locally

- Added immutable `ResearchNodeSpec`, `ResearchPlan`, `ResearchNodeRun` and `ResearchRunState` contracts with deterministic topology, metadata closure and terminal-state invariants.
- Added pure transitions for run creation/start, dependency-gated node results, required/optional degradation, deadline failure, blocked descendants and cancellation; old states remain unchanged and raw exceptions/payloads are not stored.
- Added synthetic offline fixture, unit/integration counterexamples and `docs/bounded-orchestration.md`; no network, credentials, LLM, Provider, async executor, persistence, API, UI or recommendation path was introduced.

### Independent review evidence

- Full suite: `138 passed` (Phase 1–6's 122 tests remain green).
- `python -m compileall -q app`, orchestration import, `git diff --check`, fixture JSON and secret-like assignment scans passed.
- Independent adversarial checks passed for deterministic topology, request normalization, deadline rejection, active-node closure, required-node failure, dependency cancellation, forged state rejection, safe cancellation reasons and immutable source states.
- Phase 7 is accepted in this worktree after the above review; the next Evidence-grounded Finding/compliance plan must use a new worktree.

## 2026-09-01 — MVP Phase 8 Evidence-grounded Fact/Finding bridge

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-8` on branch `codex/mvp-phase-8-evidence-finding` from the accepted Phase 7 commit `3e5a021`.
- Added `docs/plans/2026-09-01-mvp-phase-8-evidence-finding.md` and committed the plan before implementation (`b9e7dc5`).
- The phase is limited to deterministic closure from `CrossValidationResult` plus owner/lineage-bound `ResearchObservation` and normalized `Evidence`; Recommendation, compliance, network, persistence and UI remain out of scope.

### Implemented locally

- Added `EvidenceFindingBridgeResult` with explicit `READY`, `REVIEW_REQUIRED` and `BLOCKED` states and safe issue codes.
- Added `bridge_cross_validation` / `build_evidence_grounded_finding`: only a clean `SUPPORTED` result with two independent lineages, VERIFIED evidence, exact scope/value/unit/period/provenance and owner closure can produce stable `VERIFIED Fact -> Finding` objects.
- Added bounded sensitive-input filtering, no raw validation issue/payload propagation, deterministic fact/finding IDs, synthetic fixture, unit/integration counterexamples and `docs/evidence-finding-bridge.md`.
- No Provider execution, LLM, Recommendation, order, database, API, UI or upstream repository change was introduced.

### Independent review evidence

- Phase-specific bridge tests and independent adversarial review pass; full suite reports `156 passed` (Phase 1–7's 138 tests remain green).
- `python -m compileall -q app`, research bridge import, `git diff --check`, fixture JSON and sensitive-value scans all pass.
- Adversarial checks cover stable ordering, DecisionTrace closure, forged `SUPPORTED`, duplicate lineage, missing/unknown evidence, owner/provenance tampering, sensitive text/IDs and immutable inputs.
- Phase 8 is accepted in this worktree; the next bounded fixture-backed async research execution plan must use a new worktree.

## 2026-09-01 — MVP Phase 9 fixture-backed async research run

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-9` on branch `codex/mvp-phase-9-fixture-research-run` from the accepted Phase 8 commit `6606be1`.
- Added `docs/plans/2026-09-01-mvp-phase-9-fixture-research-run.md` and committed the plan before implementation (`8d1cabb`).
- The phase is limited to an injected-provider execution adapter: bounded parallel ready nodes, dependency gating, four-state mapping, and normalized Evidence/Observation output. Live SkillHub, LLM, persistence, UI and recommendation generation remain out of scope.

### Implemented locally

- Added `ResearchNodeRequest`, `ResearchRunExecutionResult` and `execute_research_run`/`run_research` under `app/orchestration/executor.py`.
- Reused `execute_with_budget`, `normalize_result_to_evidence` and all Phase 7 transitions; ready roots run concurrently, children wait for completed parents, and required/optional/deadline semantics remain authoritative.
- Mapped Provider `SUCCESS/PARTIAL/EMPTY/FAILED` and timeout/exception paths to safe typed research results. Textual Evidence is retained, finite scalar fields become owner-bound Observations, and missing lineage remains visible without counting as independent support.
- Added synthetic multi-node fixture, unit/integration counterexamples and `docs/fixture-research-run.md`; no raw exception, credential, zero fallback, network call, LLM, persistence, UI or Recommendation path was introduced.

### Independent review evidence

- Phase-specific tests and independent review pass; full suite reports `169 passed` (Phase 1–8's 156 tests remain green).
- Parallel timing, dependency order, four-state mapping, timeout/exception safety, provider identity, sensitive value filtering, no-lineage behavior, output closure and input immutability are covered.
- `python -m compileall -q app`, orchestration import, `git diff --check`, fixture JSON and sensitive-value scans all pass.
- Phase 9 is accepted in this worktree; the next Evidence/Finding consumer plus risk/compliance gate plan must use a new worktree.

## 2026-09-01 — MVP Phase 10 research-to-Evidence pipeline

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-10` on branch `codex/mvp-phase-10-research-evidence-pipeline` from the accepted Phase 9 commit `7ae186b`.
- Added `docs/plans/2026-09-01-mvp-phase-10-research-evidence-pipeline.md` and committed the plan before implementation (`405f80e`).
- The phase is limited to consuming a `ResearchRunExecutionResult`: run-aware Cross Validation and Phase 8 Evidence/Finding registration. Risk, compliance, Recommendation, network, persistence and UI remain out of scope.

### Implemented locally

- Added `ResearchClaimSpec`, `ResearchEvidencePipelineResult`, safe pipeline issue contracts and `build_research_evidence_pipeline`/`evaluate_research_run`.
- Complete runs with two independent lineages can produce READY `VERIFIED Fact -> Finding` objects and a closed `DecisionTrace`; PARTIAL/FAILED/EMPTY runs downgrade supported claims to explicit unresolved review and expose no Facts/Findings in the trace.
- Added deterministic claim ordering, validation/bridge closure, duplicate/owner checks, sensitive-output filtering, two-lineage fixture and unit/integration counterexamples; no Recommendation, network, LLM, persistence, UI or upstream change was introduced.

### Independent review evidence

- Phase-specific pipeline tests and independent adversarial review pass; full suite reports `177 passed` (Phase 1–9's 169 tests remain green).
- Verified complete/partial/contradictory/single-lineage semantics, forged execution/evidence, duplicate/foreign claims, sensitive text, closed DecisionTrace and input immutability.
- `python -m compileall -q app`, imports from both orchestration and research pipeline modules, `git diff --check`, fixture JSON and sensitive-value scans all pass.
- Phase 10 is accepted in this worktree; the next independent risk/compliance gate plan must use a new worktree.

## 2026-09-02 — MVP Phase 11 independent risk and compliance gates

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-11` on branch `codex/mvp-phase-11-risk-compliance-gates` from the accepted Phase 10 commit `039c7c8`.
- Added `docs/plans/2026-09-01-mvp-phase-11-risk-compliance-gates.md` and committed the plan before implementation (`98dc23f`).
- The phase is limited to independent Recommendation eligibility checks over existing profile, research, risk-budget, and allocation artifacts. It does not create a Recommendation or call a network/LLM/storage/UI boundary.

### Implemented locally

- Added frozen `AdvisoryCandidate`, risk/compliance issue and result contracts, `DecisionGateResult`, fixed disclosure codes, and `PASS`/`REVIEW_REQUIRED`/`BLOCKED` semantics under `app/gates`.
- Added `evaluate_risk_gate`, which revalidates every input and closes owner/profile/version/drawdown, research trace quality, budget limits, report identities, timestamps, band limits, breach references, and assessment/allocation status. A complete deterministic breach may pass only as explicit remediation eligibility bound to the exact breach IDs; partial or unresolved risk data still requires review.
- Added `evaluate_compliance_gate`, which closes candidate Finding references through VERIFIED Facts/Evidence, requires four explicit disclosures, and blocks credential-shaped input, guarantee/no-loss language, and numeric target-return promises without echoing rejected prose.
- Added `evaluate_decision_gates`; Recommendation eligibility is true only when both independent gates PASS. Gate IDs bind full inputs through local content signatures, while outputs contain no candidate prose, Recommendation, action, order, or return target.
- Added a full offline fixture and unit/integration counterexamples. No real SkillHub, credential, LLM, persistence, API, UI, order execution, optimization, or legal-coverage claim was introduced.

### Independent review evidence

- Phase-specific gate tests: `20 passed`.
- Final full regression suite after adversarial hardening: `197 passed` (Phase 1–10's 177 tests remain green).
- `python -m compileall -q app`, public gate imports, all 15 fixture JSON files, `git diff --check`, no-network/storage/LLM import scan, and fixture sensitive-key scan passed.
- Independent post-commit checks passed for wrong-type inputs, 100-run determinism, immutable inputs, sensitive owner redaction, combined review/block precedence, candidate prose non-echo, content-bound IDs, deterministic breach remediation, bridge/trace divergence, and absence of Recommendation/action fields.
- Phase 11 is accepted in this worktree. Phase 12 must start from this accepted commit in a new worktree and may consume only a dual-PASS gate result; no push was performed.

## 2026-09-02 — MVP Phase 12 Recommendation and Decision Receipt

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-12` on branch `codex/mvp-phase-12-recommendation-receipt` from accepted Phase 11 commit `38c53c2`.
- Added `docs/plans/2026-09-02-mvp-phase-12-recommendation-decision-receipt.md` and committed the plan before implementation (`5796192`).
- The phase is limited to deterministic Recommendation composition after a dual-PASS gate and an in-memory self-validating Decision Receipt; API, persistence, UI, live providers and LLM remain out of scope.

### Implemented locally

- Added frozen `RecommendationBinding`, `DecisionReceipt`, `RecommendationCompositionResult`, rule-version and issue contracts under `app/recommendation`.
- Added `compose_recommendations`: revalidates all profile/portfolio/research/risk/allocation/candidate/gate inputs, reruns the Phase 11 gate, emits only ASSET `HOLD` for no-breach envelopes or breach-bound `REDUCE` within exact allocation bands, and rebuilds a closed `DecisionTrace`.
- Added an explicit aggregate-breach guard: sector/technology/unclassified breaches without an asset mapping are blocked rather than presented as a fake security recommendation.
- Added canonical content signatures and a receipt builder recording owner/profile/snapshot/report/gate/evidence/fact/finding/recommendation identities, rule versions, deterministic generation mode, band/breach bindings, trace hash and content hash.
- Added balanced/conservative fixtures, unit/integration counterexamples, and `docs/recommendation-decision-receipt.md`. No ADD/EXIT, price, quantity, target return, order, cash redistribution, LLM, network, persistence or UI behavior was introduced.

### Current review evidence

- Phase-specific Recommendation/Receipt tests: `17 passed`.
- Full regression suite: `215 passed`.
- `python -m compileall -q app`, public Recommendation imports, all fixture JSON
  parsing, `git diff --check`, no-network/storage/LLM boundary scan, and fixture
  sensitive-value scan passed.
- Additional adversarial checks cover non-VERIFIED trace reuse, forged extra
  remediation breaches, gate/candidate/run/assessment/allocation receipt identity,
  non-ASSET REDUCE rejection, receipt hash tampering, 100-run determinism and
  input immutability.
- Independent post-commit review passed on commit `d0fe0b6`: clean worktree,
  full `215 passed`, compile/import checks, fixture/sensitive scans, and
  no-network/storage/LLM boundary checks all passed.
- Phase 12 is accepted locally. No push was performed; Phase 13 must start from
  this accepted commit in a new worktree.

## 2026-09-02 — MVP Phase 13 owner-scoped API, persistence and explainable UI

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-13` on branch
  `codex/mvp-phase-13-api-persistence-ui` from accepted Phase 12 commit `076e1e6`.
- Added the Phase 13 plan before implementation: owner-scoped SQLite decision
  events, FastAPI health/create/list/detail boundaries, and a zero-build
  explainable workbench first slice. Real authentication, PostgreSQL, live
  providers and API-triggered orchestration remain explicitly out of scope.

### Implemented locally

- Added immutable `DecisionEvent`/summary contracts, idempotent content hashes,
  a migration-backed SQLite store with owner queries, conflict detection,
  corruption checks and serialized read/write revalidation.
- Added FastAPI app factory with safe validation/conflict/scope errors and
  health/create/list/detail routes. `PASS` events retain a closed Receipt;
  `REVIEW_REQUIRED`/`BLOCKED` events remain empty-trace refusals.
- Added the Prism workbench first slice with Overview, Advisor, Evidence and
  Risk Profile panels, CSP, text-only DOM insertion and the reused warm-white /
  deep-ink / clay visual grammar.
- Added Phase 13 unit/API tests and updated architecture/API documentation.

### Pre-commit verification

- Phase-specific store/API/fixture tests: `12 passed` (one upstream
  Starlette/httpx deprecation warning only).
- Full regression suite: `227 passed`; `python -m compileall -q app`, public API/store
  imports, all fixture JSON parsing, `git diff --check`, and static DOM/boundary
  scans passed.
- Built a local wheel with `--no-build-isolation` and confirmed the SQLite migration
  and all three static workbench assets are packaged.
- Real local browser acceptance against uvicorn: the owner-scoped workbench loaded
  four fixture events, showed balanced `HOLD` and conservative `REDUCE`, expanded
  `Finding → Fact → Evidence`, and rendered explicit `待复核`/`已阻断` empty-result
  states without a Receipt or executable recommendation.

Independent post-commit adversarial review and final acceptance are still pending.

### Independent post-commit review and acceptance

- Re-ran the committed tree at `e7eddd2`: full suite `227 passed`, with only the
  installed Starlette/httpx deprecation warning; compile/import, all fixture JSON,
  `git diff --check`, full-app network/LLM boundary, static DOM safety, and wheel
  package-data checks passed.
- Replayed owner isolation, idempotent retry/conflict, JSON/hash corruption,
  sensitive owner/body rejection, and non-PASS Receipt/trace invariants through the
  tests and store/API boundary.
- Restarted uvicorn from the committed worktree and verified the real browser: four
  owner-scoped events, BALANCED `HOLD`, CONSERVATIVE `REDUCE`, expandable
  `Finding → Fact → Evidence`, and explicit `待复核`/`已阻断` states. The latter two
  expose no Receipt or executable recommendation.
- Phase 13 is accepted locally. No push was performed. The next phase must start in
  a new worktree from `e7eddd2` and keep the API owner-scoped while adding only the
  planned fixture-query/Profile/Portfolio integration.

## 2026-09-02 — MVP Phase 14 Advisor query, Profile and Portfolio integration

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-14` on branch
  `codex/mvp-phase-14-api-fixture-query-profile-portfolio` from accepted Phase 13
  commit `0156f1b`.
- Added `docs/plans/2026-09-02-mvp-phase-14-advisor-query-profile-portfolio.md` and
  committed the plan before implementation (`52bb2e3`).
- This phase is limited to a structured, offline fixture-first Advisor query. It
  does not add live SkillHub/Tushare, credentials, LLM/chat, production storage,
  orders, target prices or a new UI business structure.

### Implemented locally

- Added immutable `AdvisorQueryRequest`/`AdvisorQueryOutput` contracts with owner
  closure, timezone replay anchor, bounded identifiers, extra-field rejection and
  sensitive-input refusal.
- Added a fixture manifest and two independent source/record/lineage Provider
  fixtures. The service reuses Profile, Portfolio Exposure/Concentration, Risk
  Budget, Allocation, Research Executor/Pipeline, Risk/Compliance Gates,
  Recommendation Composer and DecisionEvent Store rather than duplicating rules.
- Added `POST /api/v1/advisor/queries`; successful calls persist an owner-scoped,
  content-addressed DecisionEvent and repeated fixed inputs return `created=false`.
  Provider degradation remains REVIEW_REQUIRED/BLOCKED with no executable receipt,
  recommendation or trace.
- Added `docs/advisor-query-api.md`, package data declarations, unit/API tests and
  updated README, architecture, TODO and this execution log.

### Current verification

- Phase-specific tests: `11 passed`.
- Full regression suite: `238 passed` with only the installed Starlette/httpx
  deprecation warning.
- Deterministic replay now uses the injected `generated_at` clock through fixture
  load and execution; evidence integrity checks match each expected source,
  record, lineage, field, unit, period and Decimal value.
- Post-commit compile/import, fixture JSON, package-data, source boundary, static UI
  and real-browser acceptance all passed. Browser evidence shows an API-triggered
  BALANCED `HOLD` Receipt with expanded Finding→Fact→two Evidence sources; another
  owner sees no events.
- Independent adversarial review passed for Pydantic-bypass revalidation, 100-run
  deterministic/concurrent execution, one-for-one manifest evidence integrity,
  owner/error isolation and non-executable degraded results.
- Phase 14 is accepted locally at the current worktree `HEAD`. No push was
  performed; the next phase
  must start in a new worktree with a plan committed before implementation.

## 2026-09-02 — MVP Phase 16 four-track research specialist matrix

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-16` on branch
  `codex/mvp-phase-16-research-node-matrix` from accepted Phase 15 `HEAD`.
- Committed the plan before implementation as `33892dd`. Scope is deterministic
  Macro/Industry/Stock/ETF-Fund source recipes and a fixture-first matrix runner;
  SkillHub/Tushare, authentication, Gemini/LLM, persistence, UI and orders remain
  explicitly out of scope.

### Implemented locally

- Added `ResearchSpecialistRole`, owner-closed `ResearchSpecialistNode` and
  `ResearchSpecialistMatrix` contracts with a shared kind→Provider operation whitelist,
  deterministic dependency validation, dual-lineage claim closure and safe replay request.
- Added packaged four-track manifest and eight synthetic Provider fixtures. The service
  rebinds owner, creates the existing `ResearchPlan`, runs all roots through the existing
  bounded executor, scopes multi-claim observations safely and consumes the existing
  Cross Validation/Evidence bridge.
- Extended `ResearchClaimSpec` with an explicit observation scope that cannot omit an
  executed observation of the same subject/metric/unit/period; repeated pipeline issue
  codes are aggregated without losing per-claim bridge detail.
- Added unit/integration/adversarial tests, package-data configuration and the
  [research specialist matrix contract](research-specialist-matrix.md).

### Independent review and acceptance

- Full regression: `257 passed` with only the installed Starlette/httpx deprecation
  warning; compile/import, JSON/fixture, wheel, static and `git diff --check` checks passed.
- Review covered four-kind/operation and cycle rejection, owner/Pydantic bypass, source
  and Provider identity tampering, conflict/partial/failed/timeout degradation, no-zero
  semantics, deterministic replay, scope anti-bypass, and 100 concurrent runs.
- No network, LLM/Gemini, transaction, recommendation or order path was introduced.
  Phase 15 API/UI regression remains green; no new browser flow was required by this
  plan because it does not change the UI.
- Phase 16 is accepted locally at the current worktree `HEAD`; no push was performed.
  The next phase must begin in a new worktree with a plan-only commit.

## 2026-09-02 — MVP Phase 15 structured Advisor Query workbench

### Plan and worktree

- Created dedicated worktree `D:\Github_Storage\prism-phase-15` on branch
  `codex/mvp-phase-15-query-workbench` from the accepted Phase 14 tree.
- Committed the plan before implementation as `765d64c`. Scope is a structured,
  owner-scoped query form and packaged synthetic template; live Provider access,
  authentication, LLM/chat, CRUD, new financial rules and orders remain out of scope.

### Implemented locally

- Added a validated `AdvisorQueryTemplate` contract and packaged two-lineage synthetic
  query template. The service rebinds every owner-bearing nested model and rejects
  sensitive or mismatched templates.
- Added `GET /api/v1/advisor/query-template` and a form with explicit risk, horizon,
  liquidity, experience, return-expectation and drawdown fields. Submission reuses the
  Phase 14 `AdvisorQueryRequest`/service/store chain and keeps CSP/text-only DOM safety.
- Added focused contract/API/static tests and the [structured workbench contract](docs/advisor-query-workbench.md).

### Independent acceptance

- Full regression: `243 passed`; compile/import, fixture JSON, wheel package-data,
  `git diff --check`, no-network/LLM/transaction and static DOM boundary scans passed.
- Adversarial review passed template owner isolation, sensitive and forged-input refusal,
  generic error handling, 100 concurrent deterministic runs, unique events, and replay.
- Real local browser passed BALANCED `HOLD`, CONSERVATIVE `REDUCE`, `PASS · 已复用`,
  `Finding → Fact → Evidence` expansion and a second owner seeing `0 events`.
- Phase 15 is accepted locally at the current worktree `HEAD`; no push was performed.
  The next phase must start in a new worktree after a plan-only commit.

## 2026-09-02 — MVP Phase 17 Research Tracks 工作台

## 计划与 worktree

- 在已接受的 Phase 16 `b04740c` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-17`，分支为
  `codex/mvp-phase-17-research-workbench`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `aeefebc`；本阶段仍不接入真实 SkillHub/Tushare、鉴权、LLM、生产持久化或交易。

## 本地实现

- 在 `app/api` 增加 owner-scoped `research-matrix-template` 与 `research-runs` 路由，
  使用严格 `ResearchSpecialistMatrixRequest`，统一映射 owner scope、invalid input
  和 matrix refusal 错误；输出只保留节点状态、交叉验证和闭合 DecisionTrace。
- 增加 Research Tracks 静态工作台区域：四类轨道的节点状态、独立 lineage 数、
  READY/REVIEW/BLOCKED 语义和 Finding → Fact → Evidence 展开均来自既有 pipeline；
  动态文字继续用 text-only DOM/CSP 渲染，owner 切换和异步竞态会清空旧研究状态。
- 新增 [Research Tracks 工作台契约](docs/research-workbench.md) 与 Phase 17 API、
  owner 隔离、降级、重放、伪造 Pydantic 输出和静态安全测试。

## 独立审查与验收

- 实现提交：`8db4246`；补强伪造输出/敏感输入/无时区/100 次重放测试并修正空白：
  `9d210bc`。
- 全量回归：`264 passed`，仅已知 Starlette/httpx deprecation warning；
  `compileall`、公开导入、`node --check`、`git diff --check` 通过。
- 100 次相同 API request replay 返回完全相同的 run/pipeline/trace，且不写入
  `DecisionEventStore`；PARTIAL fixture 通过 API 保持 `REVIEW_REQUIRED`/`FAILED`，
  不暴露 Fact/Finding/Recommendation。
- adversarial review 覆盖额外字段、敏感 owner、无时区、未知矩阵、跨 owner、
  `model_copy(update=...)` 伪造输出与异常安全映射；没有发现可将研究状态升级为
  Recommendation/Receipt 的路径。
- wheel package-data 检查确认静态资源、四轨道 manifest/provider fixtures 和
  service 均在包内；边界扫描确认没有新增外网、LLM/Gemini、订单或事务路径。
- 真实本地浏览器完成最新代码的 owner→研究矩阵→8 节点/4 role READY→展开
  Finding/Fact/Evidence→换 owner 清空；同一浏览器还回归了 Advisor `HOLD` 与
  `REDUCE` 两条 Receipt 路径，浏览器错误日志为空。

Phase 17 在本地 worktree 接受，未 push；下一阶段必须从本阶段接受提交创建新
worktree，并先提交计划书。

## 2026-09-02 — MVP Phase 18 旗舰上下文工作台

### 计划与 worktree

- 在已接受的 Phase 17 `30c6926` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-18`，分支为
  `codex/mvp-phase-18-flagship-flow`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `599d37f`；本阶段继续保持 fixture-first，不接入真实 Provider、认证、LLM、
  生产持久化或交易。

### 本地实现

- 在现有工作台增加只读 Portfolio Snapshot 区域，消费已验证的
  `GET /api/v1/advisor/query-template`，显示 owner、bundle/snapshot、as-of、
  基准币种、持仓和基金/ETF look-through 原值。
- 在 Risk Profile 区域增加同一模板的问卷上下文，显示 questionnaire/owner/回答
  时间、承受分数、期限、流动性、经验、收益预期和最大回撤，并保留原有 Receipt
  绑定元数据。
- 增加统一 owner 上下文清理、模板错误安全清空和 owner/sequence 异步保护；直接
  从 Advisor/Research 操作新 owner 也不会保留上一 owner 的上下文。动态值继续使用
  `textContent`，不增加计算、CRUD、外部网络或订单入口。
- 新增 Phase 18 API/静态/重放测试与
  [Portfolio/Risk Profile 上下文工作台契约](docs/flagship-context-workbench.md)。

### 独立审查与验收

- 实现提交为 `2d40112`；独立复查后补强直接 owner 切换、模板失败清空、事件详情
  异步 owner 保护并通过浏览器复验。
- 全量回归：`267 passed`，仅已知 Starlette/httpx deprecation warning；
  `compileall`、公开导入、`node --check`、`git diff --check`、100 次模板重放和
  wheel package-data 检查通过。
- 真实本地浏览器验证 Portfolio 持仓/基金穿透、Risk Profile 问卷、Advisor
  BALANCED `HOLD`、CONSERVATIVE `REDUCE`、Research Tracks `READY`/8 节点/
  Finding → Fact → Evidence 及 owner 切换清空；浏览器错误日志为空。
- adversarial review 确认没有跨 owner 渲染、XSS sink、前端金融重算、
  Recommendation/Receipt 伪造、LLM/Gemini、外部网络、订单或交易路径。

Phase 18 在本地 worktree 接受，未 push；下一阶段必须从本阶段接受提交创建新
worktree，并先提交计划书。

## 2026-09-02 — MVP Phase 19 早期负载测试骨架

### 计划与 worktree

- 在已接受的 Phase 18 `1bcaddb` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-19`，分支为
  `codex/mvp-phase-19-load-test`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `6ab60c8`；本阶段只建立本地基线，不宣称真实外部 100 用户/3 秒/99.9% SLA。

### 本地实现

- 新增 `tools.load_test`，复用 `create_app`、既有 API contracts、owner dependency
  和 `SQLiteDecisionEventStore`，支持 `template`、`research`、`advisor` 三种场景、
  有界 concurrency/requests-per-user 参数和版本化 JSON 报告。
- 报告记录逻辑操作数、HTTP 请求数、完成/失败、状态与安全错误分类、P50/P95/P99、
  owner mismatch 和事件存储前后行数；Advisor 显式记录模板→查询两步，模板/研究
  场景预期无 DecisionEvent 副作用。
- 新增九项 Phase 19 负载/契约测试，覆盖 100 并发 owner 闭合、Advisor 事件隔离、
  percentile 边界、空样本、非法参数、HTTP 失败、敏感错误 payload、owner mismatch
  和 CLI smoke；失败不会被吞掉或改写成成功。
- 新增 [早期负载测试工具文档](docs/load-test.md)，说明 ASGI transport 与真实部署
  的差异和禁止外推的指标边界。

### 独立审查与验收

- 实现提交为 `b77cd16`，随后以 `dc23e01` 修正失败报告计数/Research trace 完整性
  不变量；没有修改 `app/` 生产业务规则。
- 全量回归：`276 passed`，仅已知 Starlette/httpx deprecation warning；
  `compileall`、公开导入、CLI smoke、`git diff --check` 和 wheel package-data
  检查通过。
- 最终 100 并发本地 ASGI fixture 基线：Template P50/P95/P99
  `81.790/93.394/95.937 ms`，Research `578.552/796.039/807.497 ms`，Advisor
  模板→查询 `873.164/1419.673/1451.030 ms`；三场景均 100/100 完成、owner mismatch
  为 0、error 为 0，Advisor 写入 100 条 owner-scoped 事件，其余为 0。
- adversarial review 确认只有 in-process ASGI transport 和现有 API，错误/敏感响应
  分类安全，无外部 Provider、LLM/Gemini、凭据、金融重算、订单/交易或 raw exception
  泄露路径；基线数字不代表生产 SLA。

Phase 19 在本地 worktree 接受，未 push；下一阶段必须从本阶段接受提交创建新
worktree，并先提交计划书。
## 2026-09-02 — MVP Phase 20 结构化上下文确认

### 计划与 worktree

- 在已接受的 Phase 19 `1a0ccf3` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-20`，分支为
  `codex/mvp-phase-20-context-input`。
- 先提交计划书 `3e1fbbe`，明确 Portfolio/Risk Profile 结构化确认、复用边界、
  产品差异化、做与不做项及验收门；真实账户上传、认证、Provider、LLM、生产持久化和
  交易均延期。

### 本地实现

- 增加严格 `portfolio-context-request.v1` / `portfolio-context-response.v1` 与
  `profile-context-request.v1` / `profile-context-response.v1` contracts；重新验证
  owner、snapshot/position/fund parent/holding、ID、时区、数值和敏感/额外字段。
- 增加 owner-scoped Portfolio/Profile 确认 API。Portfolio 只返回已验证 bundle 与
  结构计数；Profile 只调用既有 `build_profile_draft`/`finalize_profile` scorer，确认
  不写 DecisionEventStore、不生成 Recommendation。
- 工作台增加本地粘贴 Portfolio JSON 与当前问卷确认动作；确认上下文只存浏览器会话，
  Advisor 优先消费已确认 bundle，Receipt/DecisionEvent 绑定实际 bundle/snapshot。
  owner 切换、模板失败、竞态和无效输入都会清空确认状态；动态内容保持 text-only
  DOM/CSP 边界。
- 新增 Phase 20 API、owner/敏感/额外字段/无时区、确定性画像、Advisor Receipt 绑定、
  存储副作用和静态边界测试，并记录 [结构化上下文确认契约](docs/context-input.md)。

### 独立审查与验收

- 实现提交为 `912dedc`；复查后以 `35e27fd` 强化 Profile ID 对完整问卷内容的确定性
  绑定，并补齐 Profile 敏感/额外字段、缺 owner 和变化输入测试。
- 全量回归：`283 passed`，仅已知 Starlette/httpx deprecation warning；
  `compileall`、公开导入、`node --check`、`git diff --check`、wheel package-data
  检查通过。
- 本地 100 并发 ASGI replay（Template/Research/Advisor，各 1 op/owner）全部完成，
  owner mismatch/error 均为 0；Advisor 写入 100 条预期事件，其他场景无副作用。
- 真实本地浏览器完成 Portfolio JSON→确认、Risk Profile→确认、BALANCED `HOLD`、
  CONSERVATIVE `REDUCE`、Evidence/Receipt 展开及 owner 切换清空旧 bundle/profile/
  文本；浏览器错误日志为空。
- 独立边界审查确认无前端金融重算、认证假象、跨 owner 泄露、Recommendation 伪造、
  外部网络、LLM/Gemini、订单或交易路径。Phase 20 已接受，本地未 push；下一阶段必须
  从本提交创建新 worktree 并先提交计划书。

## 2026-09-02 — MVP Phase 24 研究场景与不确定性可见化

### 计划与 worktree

- 在已接受的 Phase 23 `063111c` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-24`，分支为
  `codex/mvp-phase-24-research-scenarios`。
- 先提交计划书 `f0937e5`，明确只做离线 fixture-first 场景目录、Provider 四态回放
  与 Research Tracks 可见化；真实 SkillHub、LLM/Gemini、认证、生产持久化、交易和
  Recommendation 旁路均不做。

### 本地实现

- 增加严格 `ResearchScenarioId`/场景定义与模板 catalog，覆盖
  `BASELINE_READY`、`SOURCE_DISAGREEMENT`、`SOURCE_PARTIAL`、`SOURCE_EMPTY`、
  `SOURCE_FAILED`；请求可选 `scenario_id`，旧请求默认基线，响应闭合回显安全场景
  元数据。
- 在既有 `FixtureFinancialProvider` 外增加只读 scenario overlay，所有变体重新经过
  `ProviderResult`/请求校验、bounded executor、四态节点、lineage Cross-Validation
  和 Evidence/Finding pipeline。分歧保留双方 Evidence 但不升级 Fact/Finding；缺失、
  无结果和失败分别保留对应状态并安全降级。
- Research Tracks 工作台从 API 加载场景选择器，非 READY 显示 validation、支持/反对
  证据和未升级 Evidence；owner/场景切换和异步竞态仍清空旧结果，动态值保持
  text-only DOM/CSP 边界。新增 [研究场景契约](docs/research-scenarios.md)。

### 独立审查与验收

- 实现提交为 `773b636`；独立复查发现同一 request ID 跨场景复用 run ID，随后以
  `2003a1e` 将场景纳入确定性 run identity，并补充场景目录初始加载与回放测试。
- Phase-specific tests `15 passed`；全量回归 `314 passed`，仅已知 Starlette/httpx
  deprecation warning。`compileall`、公开导入、`node --check`、`git diff --check`、
  DOM/runtime 范围扫描通过。
- `python -m tools.evaluate_mvp --repeat 100 --json` 仍为 9/9，全部 case/profile/
  risk/compliance/evidence/replay 指标为 `1.0`；Template/Research/Advisor 本地
  100 并发均 100/100、error/owner mismatch 为 0，P50/P95/P99 分别为
  `86.095/99.482/104.064 ms`、`584.614/814.973/825.665 ms`、
  `917.155/1489.606/1523.550 ms`，不外推为生产 SLA。
- wheel 复核为 88 entries，包含场景-aware service/contracts/static 和现有 evaluator/
  9 cases；真实本地浏览器完成场景目录、READY、分歧双方值、PARTIAL/EMPTY/FAILED
  降级、无 Fact/Finding、owner 清理，错误日志为空。

Phase 24 已在本地 worktree 接受，未 push；下一阶段必须从本接受提交创建新
worktree，并先提交 Phase 25 计划书。

## 2026-09-02 — MVP Phase 21 固定评测集与语义回放

### 计划与 worktree

- 在已接受的 Phase 20 `b241b4c` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-21`，分支为
  `codex/mvp-phase-21-evaluation-harness`。
- 先提交计划书 `9797f45`，落实 `Prism.md` 的固定评测集/指标要求；真实市场准确率、
  收益回测、SkillHub、LLM、认证、生产监控和交易均明确不做。

### 本地实现

- 新增 9 个严格 `mvp-eval-case.v1` 案例，覆盖 BALANCED/HOLD、CONSERVATIVE/REDUCE、
  GROWTH/HOLD、科技集中阻断、穿透缺失阻断、Provider PARTIAL、Provider 冲突安全错误、
  跨 owner 拒绝和无时区拒绝。
- 新增 `tools.evaluate_mvp` 与 `mvp-evaluation-report.v1`，复用既有 Advisor、Profile、
  Portfolio、Research、Gate、Recommendation/Receipt contracts；输出安全 case 摘要、
  status/action、Evidence/Fact/Finding 计数、错误分类、语义 fingerprint 和 P50/P95，
  支持最多 100 次语义回放。新增 `docs/mvp-evaluation.md`，并将 evaluator/cases 加入
  wheel data。
- 评测器只在临时目录变体复制既有 Provider fixture，不写 DecisionEventStore、不访问
  外网、不引入新金融公式或运行时分支。

### 独立审查与验收

- 实现提交为 `680ffed`；复查后以 `02dc8bd` 补齐报告计数闭合/安装路径，
  `73d926f` 将语义回放上限提升至 100 并完成 100 次检查。
- `python -m tools.evaluate_mvp --repeat 100 --json`：9/9 case 通过，case/profile
  alignment、risk/compliance coverage、evidence coverage、semantic replay equality
  均为 `1.0`；Provider 冲突和非法输入只保留安全错误分类。
- Phase-specific tests：`5 passed`；全量回归：`288 passed`，仅已知 Starlette/httpx
  deprecation warning。`compileall`、公开导入、CLI smoke、fixture/schema、静态边界、
  `node --check`、`git diff --check` 和 wheel package-data 检查通过；wheel 包含 evaluator
  和 9 个案例。
- 独立审查确认评测指标没有冒充市场准确率/收益/SLA，且无前端金融重算、认证假象、
  Recommendation 伪造、外部网络、LLM/Gemini、订单/交易或持久化路径。Phase 21 已接受，
  本地未 push；下一阶段必须从本提交创建新 worktree 并先提交计划书。

## 2026-09-02 — MVP Phase 22 结构化投资意图与任务计划预览

### 计划与 worktree

- 在已接受的 Phase 21 `f86c73f` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-22`，分支为
  `codex/mvp-phase-22-intent-planning`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `9393226`；本阶段继续保持 fixture-first，不接入自然语言理解、LLM/Gemini、
  SkillHub、认证、生产持久化或交易。

### 本地实现

- 新增 `InvestmentIntentType`、`advisor-intent-request.v1` 和
  `advisor-plan-response.v1`，严格校验 owner、ID、时区、敏感字段、角色覆盖和
  稳定 plan ID。
- 新增 owner-scoped `POST /api/v1/advisor/plans`，只复用现有
  `FixtureResearchSpecialistMatrixService.matrix_template` 生成四轨道计划元数据；
  不执行 Provider/Research、不写 DecisionEvent、不生成 Recommendation。
- Advisor 工作台增加科技暴露复核/组合风险复核选择和计划预览；计划随 owner、
  Portfolio/Risk Profile、问卷、意图或异步序列变化清理，动态值继续 text-only。
- 新增 [Intent/Plan 契约](docs/intent-planning.md) 与 Phase 22 integration tests；
  Advisor 原有 HOLD/REDUCE、Evidence/Receipt 链保持不变。

### 独立审查与验收

- 实现提交为 `4f7786b`，无 push；公共 API 导出、静态边界和错误脱敏均通过。
- Phase-specific tests `5 passed`；全量回归 `293 passed`，仅已知
  Starlette/httpx deprecation warning。`compileall`、公开导入、`node --check`、
  `git diff --check`、100 次 `mvp-evaluation` replay、wheel package-data 与运行时
  范围扫描均通过。
- 三场景本地 ASGI 100 并发均 100/100、error/owner mismatch 为 0；Advisor 写入
  100 条预期事件，Template/Research 仍为 0 条；这些是 fixture 基线，不代表生产 SLA。
- 真实本地浏览器完成 Technology Exposure → 计划 → BALANCED `HOLD`、Portfolio
  Risk → 计划 → CONSERVATIVE `REDUCE`、Evidence/Receipt 展开与 owner 切换清空，
  浏览器错误日志为空。
- 独立审查确认无自然语言/LLM/Gemini 假象、前端金融重算、跨 owner 泄露、
  Recommendation 伪造、外部网络、订单/交易或新的持久化路径。Phase 22 已接受，
  下一阶段必须从本提交创建新 worktree 并先提交计划书。

## 2026-09-02 — MVP Phase 23 结构化画像提取提案与冲突确认

### 计划与 worktree

- 在已接受的 Phase 22 `abd9a35` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-23`，分支为
  `codex/mvp-phase-23-profile-confirmation`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `952ce5a`；本阶段继续不接入自然语言解析、LLM/Gemini、SkillHub、认证、原文
  持久化或交易。

### 本地实现

- 新增 owner-scoped `advisor-profile-proposal-request.v1` /
  `advisor-profile-proposal-response.v1` 与
  `advisor-profile-confirmation-request.v1` /
  `advisor-profile-confirmation-response.v1`；服务端始终重建
  `ProfileDraft`，不信任客户端 draft，并保留 resolved conflict 审计。
- 新增 `POST /api/v1/advisor/profile-proposals` 和 `/confirm`，复用 Phase 2
  `build_profile_draft`/`finalize_profile`；确认请求 resolutions 以深度不可变
  `FrozenDict` 保存，未知/未解决/跨 owner/敏感/无时区/extra 输入安全拒绝，接口不写
  `DecisionEventStore` 或生成 Recommendation。
- Risk Profile 工作台增加脱敏 typed proposal 预览、逐冲突选择和确认结果；owner、
  问卷变化、模板失败和异步竞态清理旧提案与 JSON，Advisor HOLD/REDUCE 纵切保持不变。
- `ProfileExtractionProposal` 增加敏感字段扫描；新增 [画像提案确认契约](docs/profile-proposal-confirmation.md)
  与 Phase 23 integration tests。

### 独立审查与验收

- 实现提交为 `5b24d68`，随后以 `dd21d06` 完成 resolutions 深度不可变硬化；无 push。
- Phase-specific tests `6 passed`；全量回归 `299 passed`，仅已知 Starlette/httpx
  deprecation warning。`compileall`、公开导入、`node --check`、`git diff --check`、
  wheel package-data、运行时范围/DOM sink 扫描均通过。
- `python -m tools.evaluate_mvp --repeat 100 --json` 仍为 9/9，所有 case/profile/
  risk/compliance/evidence/replay 指标为 `1.0`；Template/Research/Advisor 三场景
  本地 100 并发均 100/100、error/owner mismatch 为 0，Advisor 写入 100 条预期事件。
- 最新真实本地浏览器完成 5 冲突提案预览、混合选择并生成 Profile、Advisor
  `HOLD`/`REDUCE`、Evidence/Receipt 展开、问卷变化清理和 owner 切换清空；浏览器
  错误日志为空。
- 独立审查确认没有自然语言/LLM/Gemini 假象、前端评分、原文持久化、跨 owner 泄露、
  外部网络、订单/交易或新的 Recommendation 路径。Phase 23 已接受，下一阶段必须
  从本提交创建新 worktree 并先提交计划书。
## 2026-09-02 — MVP Phase 25 个股研究 Evidence Card（Demo F）

### 计划与 worktree

- 在已接受的 Phase 24 `8c38a3a` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-25`，分支为
  `codex/mvp-phase-25-stock-research`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `f1ebbd5`；本阶段继续保持 fixture-first，不接入真实 SkillHub/同花顺网络、
  在线鉴权、LLM/Gemini、估值/价格预测、交易或 Recommendation。

### 本地实现

- 新增 `StockResearchRequest`、manifest、template/response、节点状态、五场景和
  `StockRiskSummary` 严格契约；请求/结果绑定 owner、subject、period、timezone-aware
  时间，拒绝 extra、敏感字段、未知场景和跨 scope。响应逐节点公开状态、缺失字段、
  范围说明和安全 issue。
- 新增两条独立 lineage 的六指标公司财务 fixture 与
  `FixtureStockResearchService`。它复用既有 Provider 四态校验、bounded run、
  Cross-Validation、Evidence/Finding bridge 和 DecisionTrace；场景 overlay 只重建
  并重新验证 `ProviderResult`。
- READY 基线形成六个 VERIFIED Fact；服务端 `Decimal` 确定性计算现金流质量、应收
  占比和杠杆 Findings，并生成 HIGH_RISK 摘要。分歧、PARTIAL、EMPTY、FAILED 均保留
  Evidence 和降级原因，不泄露 Fact/Finding，不写 DecisionEvent，不生成
  Recommendation。
- 新增 owner-scoped `/api/v1/advisor/stock-research-template` 与
  `/api/v1/advisor/stock-research-runs`，并接入 Demo F 静态工作台；动态值只用节点
  API/`textContent`，同源 fetch，owner/场景/序列切换清理旧结果。
- 新增 [个股研究 Evidence Card 契约](docs/stock-research-card.md)，同步架构、README
  和 TODO 的实现边界。

### 独立审查与验收

- 首版实现提交为 `daad1b0`；审查发现非 READY 响应虽保留 Evidence，但 UI/API 没有
  展示具体来源节点降级原因；`6d8a349` 强化响应边界，`3a46b92` 增加
  `StockResearchNodeResponse`、节点 reason 投影及场景断言。
- Phase-specific tests：`11 passed`；全量回归：`325 passed`，仅已知
  Starlette/httpx deprecation warning。`compileall`、公开导入、`node --check`、
  `git diff --check` 通过。
- `python -m tools.evaluate_mvp --repeat 100 --json`：9/9 case 通过，case/profile/
  risk/compliance/evidence/replay 指标均为 `1.0`。本地 ASGI 100 并发基线为：
  `template` 100/100，P50/P95/P99 `99.815/114.745/118.167 ms`；`research` 100/100，
  `671.476/917.163/925.097 ms`；`advisor` 100/100 logical operations（200 requests），
  P50/P95/P99 `1025.719/1612.853/1643.036 ms`；三场景 error、owner mismatch 均为 0，
  仅作为 fixture/ASGI 基线，不外推生产 SLA。
- wheel 复核为 94 entries，包含 stock manifest、双 provider fixture、service/contracts
  和静态资源；运行时范围扫描确认没有上游运行时导入、外网、LLM/Gemini、凭据、HTML
  sink、订单或 Recommendation 旁路。
- 真实本地浏览器完成模板/五场景：基线显示六个 Fact、异常和 HIGH_RISK；分歧显示
  双方债务率 Evidence 与 lineage；PARTIAL/EMPTY/FAILED 显示节点状态和具体 reason，
  且没有 Fact/Finding；切换 owner 清空旧卡并重新绑定。浏览器 console error 为 `[]`。

Phase 25 已在本地 worktree 接受，未 push；下一阶段必须从本提交创建新 worktree，
并先提交 Phase 26 计划书。

## 2026-09-02 — MVP Phase 26 ETF/Fund 资产研究 Evidence Card（Demo G）

### 计划与 worktree

- 在已接受的 Phase 25 `956d753` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-26`，分支为
  `codex/mvp-phase-26-fund-research`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `975cfe6`；本阶段继续保持 fixture-first，不接入真实 SkillHub/同花顺网络、在线
  鉴权、LLM/Gemini、组合调仓或 Recommendation。

### 本地实现

- 新增 `FundResearchRequest`、manifest/template/response、节点状态、五个安全场景和
  `FundRiskSummary` 严格契约；六个指标为科技权重、前十大集中度、费率、年化波动率、
  最大回撤和跟踪误差。请求/结果绑定 owner、subject、period、timezone-aware 时间，
  拒绝 extra、敏感字段、未知场景和跨 scope。
- 新增两条独立 `FUND_DATA` lineage 的合成基金 fixture 与
  `FixtureFundResearchService`。它复用既有 Provider 四态校验、bounded run、
  Cross-Validation、Evidence/Finding bridge 和 DecisionTrace；场景 overlay 只重建
  并重新验证 `ProviderResult`。
- READY 基线形成六个 VERIFIED Fact；服务端 `Decimal` 确定性计算科技集中度、前十
  大集中度、波动、回撤和费率 Finding，并生成 HIGH_RISK 摘要。分歧、PARTIAL、EMPTY、
  FAILED 均保留 Evidence 与节点降级原因，不泄露 Fact/Finding，不写 DecisionEvent，
  不生成 Recommendation。
- 新增 owner-scoped `/api/v1/advisor/fund-research-template` 与
  `/api/v1/advisor/fund-research-runs`，接入 Demo G 静态工作台；动态值只用节点
  API/`textContent`，同源 fetch，owner/场景/序列切换清理旧结果。新增
  [ETF/Fund 资产研究 Evidence Card](docs/fund-research-card.md)，同步架构、README
  和 TODO。

### 独立审查与验收

- 首版实现提交为 `5a32d4f`。审查发现 Fund 节点投影未覆盖状态不变量，
  `d076ff2` 对齐底层 PENDING/RUNNING/COMPLETE/PARTIAL/EMPTY/FAILED/CANCELLED
  语义，并增加 11 条对抗性回归。
- 第二项审查发现注入服务可通过 `model_copy(update=...)` 绕过输出校验，且缺少
  request subject/period/scenario 闭合；`bcb77a2` 在 API 边界重新验证输出、拒绝漂移，
  并将错误安全映射为 `FUND_RESEARCH_ERROR`。
- 第三项审查发现风险摘要可能隐藏已触发的 WARNING/CRITICAL Finding；`6efa834` 要求
  READY 风险状态与全部非 INFO Finding 闭合，并增加风险伪造回归。
- Phase-specific tests：`24 passed`；全量回归：`349 passed`，仅已知 Starlette/httpx
  deprecation warning。`compileall`、公开导入、`node --check`、`git diff --check`
  通过。
- `python -m tools.evaluate_mvp --repeat 100 --json`：9/9 case 通过，所有指标为
  `1.0`。本地 ASGI 100 并发基线为：`template` 100/100，P50/P95/P99
  `89.246/105.397/110.999 ms`；`research` 100/100，`633.268/846.385/858.832 ms`；
  `advisor` 100 logical operations（200 requests），`939.101/1478.687/1520.639 ms`；
  三场景 error、owner mismatch 均为 0，Advisor 写入 100 条预期事件，另两场景为 0。
  这些仍是 fixture/ASGI 基线，不外推生产 SLA。
- wheel 复核为 `100` entries，包含 fund manifest、双 provider fixture、service/contracts
  和静态资源；运行时范围扫描确认没有上游运行时导入、外网、LLM/Gemini、凭据、HTML
  sink、订单或 Recommendation 旁路。
- 真实本地浏览器完成模板与五场景：基线显示六个 Fact、五类确定性 Finding 和
  HIGH_RISK；分歧显示双方科技权重 Evidence 与 lineage；PARTIAL/EMPTY/FAILED 显示
  节点状态、缺失/范围/安全 issue 且没有 Fact/Finding；展开 Finding → Fact → Evidence
  链路；owner 切换清空旧卡；console error 为 `[]`。

Phase 26 已在本地 worktree 接受，未 push；下一阶段必须从 `21714f8` 创建新 worktree，
并先提交 Phase 27 计划书。下一阶段优先补齐 Prism.md 明确要求的最低可转债资产卡，
继续保持真实 Provider、认证、生产持久化和交易执行延期。

## 2026-09-02 — MVP Phase 27 最低可转债资产研究 Evidence Card（Demo H）

### 计划与 worktree

- 在已接受的 Phase 26 `21714f8` 上创建独立 worktree
  `D:\Github_Storage\prism-phase-27`，分支为
  `codex/mvp-phase-27-convertible-bond`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `04790a7`；本阶段保持 fixture-first，不接入真实 SkillHub/同花顺网络、在线鉴权、
  LLM/Gemini、交易执行、组合优化或 Recommendation。

### 本地实现

- 新增 `CONVERTIBLE_BOND_DATA` Provider operation、`CONVERTIBLE_BOND` research node
  kind，以及严格的 Convertible Bond manifest/request/template/response、节点、场景、
  风险摘要契约；七个原始指标和两个派生指标均有稳定 metric/unit 定义，面值固定为
  100 CNY，信用/流动性等级只接受 manifest 的安全序数标签。
- 新增两条独立 lineage 的合成可转债 Provider fixture 与
  `FixtureConvertibleBondResearchService`。它复用既有四态 Provider、bounded executor、
  lineage-aware Cross-Validation、Evidence/Finding bridge 和 DecisionTrace；服务端以
  `Decimal`/`ROUND_HALF_UP` 计算转股价值与转股溢价率，并生成版本化风险 Finding。
- 新增五场景 owner-scoped API 与静态工作台：基线闭合 9 个 Fact、16 条 Evidence 和
  五类非 INFO 风险；分歧、PARTIAL、EMPTY、FAILED 保留 validation/Evidence/节点原因，
  不升级 Fact/Finding/风险，也不写 DecisionEvent。
- 新增 [可转债资产研究 Evidence Card](docs/convertible-bond-research-card.md)，同步
  架构、README、TODO 与 package-data；wheel 安装后可从包内 fixture 实例化 service。

### 独立审查与验收

- 首版实现提交为 `d88d7ea`。审查发现响应模型只校验公式输入时间排序，未防止注入
  服务伪造派生值；`d2d1295` 加入精确 Decimal 复算、正数/等级范围、公式 Evidence
  Finding 引用和风险摘要闭合，并增加对抗性回归。
- 后续审查发现风险摘要可隐藏已触发 Finding、API 注入输出可漂移 scope，以及响应未
  强制每个原始指标对应 validation、双节点数量和 required 语义；`d2d1295`、`4b2627c`
  和 `4105ce9` 分别完成 API/风险、response-contract 与 manifest/node identity 修复。
- 阶段测试：`28 passed`；全量回归：`377 passed`，仅已知 Starlette/httpx deprecation
  warning。`compileall`、公开 import、`node --check`、`git diff --check` 通过。
- `python -m tools.evaluate_mvp --repeat 100 --json`：9/9 case 通过，所有指标为
  `1.0`。可转债本地 ASGI 100 并发基线为：template 100/100，P50/P95/P99
  `165.328/180.471/183.205 ms`；research 100/100，P50/P95/P99
  `790.712/1308.629/1364.426 ms`；错误、owner mismatch 和存储行数均为 0；不外推
  真实市场准确率或生产 SLA。
- wheel 共 `106` entries，包含可转债 manifest、双 Provider fixture、service/contracts
  和静态资源；wheel 安装目录实例化 service 成功。运行时范围扫描无外网、LLM/Gemini、
  上游运行时导入、凭据、HTML sink、订单或 Recommendation 旁路。
- 真实本地浏览器完成模板、基线、分歧、PARTIAL、EMPTY、FAILED 与 owner 切换；9 个
  指标、派生公式、HIGH_RISK、节点状态、validation、Finding → Fact → Evidence 与
  lineage 可见；控制台错误为 `[]`，无外部请求；等级卡片重复单位已修正。

Phase 27 已在本地 worktree 接受，最终验收记录见
`docs/plans/2026-09-02-mvp-phase-27-convertible-bond.md`；未 push。下一阶段必须从本
阶段接受提交创建全新 worktree，并先提交 Phase 28 计划书。

## 2026-09-02 — MVP Phase 28 确定性组合优化目标结构提案（Demo I）

### 计划与 worktree

- 从已接受的 Phase 27 提交 `5fbd022` 创建独立 worktree
  `D:\Github_Storage\prism-phase-28`，分支为
  `codex/mvp-phase-28-portfolio-optimization`。
- 先提交范围、复用边界、产品差异化、验收门和明确不做项计划
  `8ad10b5`；本阶段保持 fixture-first，不接入真实 Provider、在线鉴权、LLM/Gemini、
  生产持久化、相关性/流动性模型、交易执行或 Recommendation。

### 本地实现

- 新增 `app/optimization` 严格请求、模板、场景、目标、约束、Issue、Trace 和响应契约，
  复用既有 Portfolio/Exposure/Concentration/Risk Budget/Profile 确认边界；READY 目标、
  资产/行业/Technology/UNCLASSIFIED 约束和 Decimal 舍入均闭合，非 READY 不返回目标。
- 新增五资产、多行业、双状态 replay 的合成 optimization fixture 与
  `FixturePortfolioOptimizationService`，实现单一版本化 `CAP_AND_REDISTRIBUTE_V1`：
  按画像预算截断超限 bucket，按稳定 headroom 重分配，并在行业内以单资产 cap 和整数
  百分点余数闭合到 100.00%。
- 新增 owner-scoped `portfolio-optimization-template` / `portfolio-optimization-runs`
  API 与静态 Optimization 工作台；复用 owner/sequence 清理、DOM text-only 渲染和
  同源 fetch。所有结果只读展示，不写 `DecisionEventStore`，不进入 Recommendation/Receipt。
- 初版实现提交 `b7d118d`；首次审查发现响应未强制目标行与资产/行业/聚合约束精确闭合、
  多个 Technology 标签可能突破全局上限，随后在 `9d343da` 修复。第二轮审查又发现
  一个百分点级 sector current rounding 闭合风险、FrozenDict 规则可变性测试缺口、
  缺少 look-through/画像/bundle 注入回归和未分类标签规范化，最终在 `585809e` 收口：
  约束全引用、无代表 aggregate 只能为零、非 READY 不暴露 constraints，并拒绝显式
  UNCLASSIFIED 被当作已知行业。

### 独立审查与验收

- Phase-specific tests：`21 passed`；300 组随机整数百分点权重 fuzz 均保持 READY、
  100.00% 总和和单资产 cap（另有 profile 轮换）。
- 全量回归：`398 passed`，仅已知 Starlette/httpx deprecation warning；
  `compileall`、公开 import、`node --check`、`git diff --check` 和固定评测（9/9、
  全部指标 `1.0`）通过。
- 本地 ASGI 100 并发（每 owner 一次 template + 一次 BASELINE_READY run）全部 HTTP
  200，owner mismatch/error 均为 0，DecisionEventStore 行数为 0；template
  P50/P95/P99=`178.984/247.547/276.055 ms`，run P50/P95/P99=`199.332/246.561/256.845 ms`。
  这些是 fixture/ASGI 基线，不外推真实外部 100 用户或 3 秒 SLA。
- wheel 共 `110` entries，包含 optimization contracts/service/fixture、静态资源和
  package-data；临时安装目录实例化 service 并读取
  `portfolio-optimization-demo-i-001` 成功。运行时范围扫描未发现外网、LLM/Gemini、
  上游导入、凭据、HTML sink、订单或 Recommendation 旁路。
- 真实本地浏览器完成模板、BALANCED/CONSERVATIVE 目标变化、PARTIAL/INFEASIBLE 阻断
  和 owner 切换清理；方法、当前→目标权重、cap/delta、约束算术、画像/报告身份与
  失效条件可见，控制台错误为 `[]`，请求保持本地同源。
- 明确产品差异：不输出黑箱最优权重或买卖列表，而是把画像、快照、暴露、预算、约束
  算术和失效条件绑定在可重放提案上；输入不完整时保留 REVIEW_REQUIRED/BLOCKED，绝不
  以零值掩盖缺失。Phase 28 已在独立 worktree 接受，未 push。

## 2026-09-02 — MVP Phase 29 structured context memory

### 计划与边界

- 从 Phase 28 接受提交 `ba5d316` 创建全新 worktree
  `D:\Github_Storage\prism-phase-29`，分支为
  `codex/mvp-phase-29-persistent-context`。
- 先提交 `docs/plans/2026-09-02-mvp-phase-29-persistent-context-memory.md`（`24b1a7e`），
  明确本阶段只做已确认结构化上下文的显式保存、读取和恢复；自然语言聊天、语义/向量
  检索、自动恢复、云端同步、生产认证、实时 Provider、删除/TTL、交易和 Recommendation
  旁路均不做。

### 本地实现

- 新增 `ContextMemoryWriteRequest`、`ContextMemoryRecord`、`ContextMemoryReferences`、
  列表/写入响应契约；重验 questionnaire/profile/portfolio 的 owner、问卷、bundle、
  snapshot 闭合，并验证可选 Intent/Plan 与固定研究/优化引用。
- 复用 DecisionEventStore 的 WAL、RLock、事务、迁移 runner、owner 校验和安全损坏语义，
  新增 `002_context_memory.sql`、append-only 幂等写入、UTC 稳定列表和跨重启读取；
  `memory_id` 与 canonical SHA-256 `content_hash` 由服务端派生，客户端不能伪造。
- 新增 owner-scoped `POST/GET /api/v1/advisor/context-memory` 与静态工作台卡片；刷新
  只读取列表而不自动覆盖表单，恢复必须显式点击并清空旧 Advisor/Research/Optimization
  派生结果。动态内容继续使用 DOM 节点和 `textContent`，不保存聊天或 Provider 原文。
- 实现提交 `474b853`；审查修复提交 `08a5567` 收口直接 owner 切换、过期异步错误和
  `STORE_CORRUPT` 安全响应。

### 独立审查与验收

- Phase 29 tests：`19 passed`；覆盖合法/重复/漂移/敏感/extra/naive-time、hash/id、
  migration/restart、损坏 payload/hash/timestamp/owner、limit、owner 隔离、无
  DecisionEvent 副作用与 100 次并发幂等写入。
- 全量回归：`417 passed`，仅已知 Starlette/httpx deprecation warning；
  `compileall`、公开 import、前端 `node --check`、`git diff --check` 通过。
- 固定评测 `python -m tools.evaluate_mvp --repeat 100 --json` 保持 9/9 cases、全部
  指标 `1.0`。
- `python -m tools.context_memory_load_test --owners 100`：并发写入/读取各 `100 x
  HTTP 200`，错误 `0`，owner mismatch `0`，store rows `100`，重启后 `100`；写入
  P50/P95/P99=`361.860/401.891/408.182 ms`，读取=`125.547/141.201/143.637 ms`。
  这些是本地 fixture/ASGI/SQLite 基线，不是生产 SLA。
- wheel 构建、隔离安装、公开 import 与 migration versions `[1, 2]` 通过；运行时扫描
  未发现新增外网、LLM/Gemini、凭据、raw chat、HTML sink、订单或 Recommendation 旁路。
- 真实本地浏览器完成确认 Profile/Portfolio → 保存 → 刷新读取且不自动恢复 → 显式恢复
  → 重新运行 Advisor/Optimization；owner 直接切换先清空旧记忆；可见 hash、画像/快照
  身份、保存时间和“本地记忆非认证”边界，控制台错误 `[]`。
- Phase 29 已在独立 worktree 接受，未 push；下一阶段必须从该接受提交创建新的 worktree
  并先提交计划书。

## 2026-09-02 — MVP Phase 30 Provider Cache/Fallback

### 计划与 worktree

- 从 Phase 29 接受提交 `fcf35ba` 创建全新 worktree
  `D:\Github_Storage\prism-phase-30`，分支为
  `codex/mvp-phase-30-provider-cache-fallback`。
- 先提交 `docs/plans/2026-09-02-mvp-phase-30-provider-cache-fallback.md`
  （`29c6982`），明确只做进程内、有界、fixture-first 的 Provider cache、一次备用
  provider 和 stale 语义；实时 SkillHub、生产缓存/断路器、动态限流、完整 Evidence UI
  和私人上下文公共缓存均排除。

### 本地实现

- 新增 `ProviderServingMode` 与 `ProviderResult` mode/age 契约；新增
  `InMemoryProviderCache`（provider+fingerprint key、fresh TTL/stale grace、LRU、
  RLock、不可变校验 payload、private/secret bypass）和 `ProviderExecutionPolicy`。
- 扩展 `execute_with_budget`/`execute_research_run`：fresh cache → primary → 一次
  fallback → stale cache → FAILED，EMPTY 不触发 fallback；fallback 与 stale 保留
  provider/source/lineage，stale normalization 变为 `STALE` Evidence 和 PARTIAL 节点。
- 将 provider、serving mode、cache age 贯穿研究节点、矩阵/个股/基金/可转债 API
  projection；Specialist Matrix service 支持显式注入共享 policy，默认 direct 行为
  不变。
- 新增 Phase 30 resilience 单测与 `tools/provider_resilience_load_test.py`，补充
  `docs/provider-cache-fallback.md` 和复审记录。

### 独立复审与验收

- 初版 `a2df871` 经第二轮复审发现两个 P1：result 侧 private payload 可能入 cache，
  以及 public node response 丢失 provenance；分别由 `3972f40`、`1541fce` 修复，
  复审结论见 `docs/reviews/2026-09-02-phase-30-provider-cache-fallback-review.md`。
- Phase 30 tests `14 passed`；全量回归 `431 passed`（Phase 29 的 `417` 项基线保持
  绿色），仅已知 Starlette/httpx deprecation warning。
- `python -m tools.evaluate_mvp --repeat 100 --json`：9/9，所有指标 `1.0`；
  `python -m tools.provider_resilience_load_test --requests 100`：fresh/stale 各
  100/100，错误 `0`，request IDs 唯一，healthy 回源 `1` 次。
- compileall、公开 import、前端 `node --check`、`git diff --check`、wheel `115`
  entries/隔离安装和静态边界扫描通过。真实本地浏览器运行四轨道矩阵为 READY、8 cards、
  外部请求 `[]`、console errors `[]`。
- 产品差异：缓存/备用/陈旧不是静默答案变体，而是可审计 mode；stale 自动失去
  VERIFIED 资格，用户可以知道何时需要复核。Phase 30 已在独立 worktree 接受，未 push。

## 2026-09-02 — MVP Phase 31 Advanced Evidence UI（已验收）

### 计划与 worktree

- 从 Phase 30 接受提交 `63f6a4e` 创建全新 worktree
  `D:\Github_Storage\prism-phase-31`，分支为
  `codex/mvp-phase-31-evidence-ui`。
- 先提交 `docs/plans/2026-09-02-mvp-phase-31-advanced-evidence-ui.md`（`7826035`），
  明确只做当前会话 Evidence explorer、来源/新鲜度/降级可视化与 owner/run 清理；不做
  后端索引、实时 SkillHub、认证、云持久化、LLM/Gemini 或 Recommendation 旁路。

### 初版实现与复审修复

- `fd56d19` 增加 Evidence chain explorer：聚合 Advisor、Research Matrix、Stock、
  Fund 和 Convertible Bond 的 owner-bound trace，提供搜索、质量/serving mode/轨道/
  promotion 筛选、键盘可达 rows、详情 metadata 和实际 Finding → Fact → Evidence /
  Validation 路径；所有动态内容使用 DOM API/textContent。
- `fba69ec` 修正多节点同 Provider 时的 provenance 选择，并将 fallback 明确显示为需
  复核而非绿色通过。
- `467bfb5` 修正复审发现的 Context Memory 恢复残留：清空旧 selected receipt、详情与
  explorer selection，要求恢复后重新运行 Advisor；同时保留既有 Evidence chain 文案
  兼容性。
- 新增 `docs/advanced-evidence-ui.md`、静态契约测试和
  `tools/advanced_evidence_ui_smoke.cjs`；实测浏览器路由注入 stale/fallback，仅用于
  本地 UI 语义验证，不改变服务端契约。

### 验证与验收

- 阶段静态测试 `3 passed`；全量回归 `434 passed`，仅已知 Starlette/httpx
  deprecation warning。
- `compileall`、`node --check`、`git diff --check` 通过；真实本地 headless 浏览器已
  覆盖 Research Matrix、Stock、Fund、Convertible Bond、Advisor、Evidence ID 搜索、
  VERIFIED/stale/fallback mode、cache age、owner 切换清理、窄屏键盘 focus；外部请求
  `[]`、console errors `[]`。
- 独立复审记录见 `docs/reviews/2026-09-02-phase-31-advanced-evidence-ui-review.md`；发现的
  provenance、Context Memory restore 和 event reload 残留均已修复，计划状态改为
  `ACCEPTED`。
- 最终 `evaluate_mvp --repeat 100` 为 `9/9`、所有指标 `1.0`；resilience load 为 fresh /
  stale 各 `100/100`、错误 `0`；wheel `115` entries 的静态资源与隔离 import 通过；
  真实浏览器 smoke 覆盖五轨道、Advisor、stale/fallback、context restore、owner 清理、
  窄屏键盘和无外部请求。
- Phase 31 已在独立 worktree 接受，未 push；下一阶段必须从该接受提交创建全新 worktree。

## 2026-09-02 — MVP Phase 32 中文 UI 与导航选中态（已验收）

### 计划、实现与独立审查

- 从 Phase 31 accepted `d6fccd7` 创建全新 worktree
  `D:\Github_Storage\prism-phase-32`，分支为
  `codex/mvp-phase-32-ui-localization-navigation`；先提交计划
  `docs/plans/2026-09-02-mvp-phase-32-ui-localization-navigation.md`（`b6f958c`）。
- 将静态 HTML、动态状态/错误/方法说明、Evidence 元数据、研究场景与无障碍文案统一为
  中文；保留 Provider/source/lineage、Evidence ID、schema/API 字段和稳定枚举代码，
  只在展示层建立“中文说明 + 可检索代码”映射。
- 左侧导航保留既有 section hash，在点击、`hashchange`、首次加载和直接打开 hash 时
  同步 `.active` 与 `aria-current="location"`；不新增路由、请求或后端契约。
- 独立审查记录于
  `docs/reviews/2026-09-02-phase-32-ui-localization-navigation-review.md`：修复场景
  option 机器值被翻译、降级分支英文描述/小写单位泄漏和 ISSUE 标题大小写问题；确认
  owner/异步清理、text-only DOM/CSP、稳定 ID 和无外部请求边界未回归。

### 验证与产品边界

- 新增中文 UI/导航静态契约并更新历史静态断言；全量回归 `436 passed`，仅已知
  Starlette/httpx deprecation warning；`node --check`、`compileall`、`git diff --check`
  通过。
- `evaluate_mvp --repeat 100 --json` 为 `9/9`、所有质量指标 `1.0`；resilience load 为
  fresh/stale 各 `100/100`、错误 `0`；wheel `115` entries，包含静态资源且隔离检查通过。
- 真实本地 headless 浏览器 smoke 覆盖导航点击/直接 hash、五轨道与 Advisor、场景
  PARTIAL、stale/fallback、Evidence 详情、Context Memory 恢复、owner 清理、窄屏键盘；
  `external_requests=[]`、`console_errors=[]`。
- 本阶段不实现 Scenario Simulation、Recommendation History、Portfolio Rebalancing、
  Evaluation Dashboard、实时 SkillHub、认证、云持久化或后端索引；下一阶段必须从本
  阶段接受提交另建全新 Phase 33 worktree，并先阅读其 P2 计划。

## 2026-09-02 — MVP Phase 33 Scenario Simulation（计划已提交，待实现）

- 从 Phase 32 accepted `134efe7` 创建全新 worktree
  `D:\Github_Storage\prism-phase-33`，分支为
  `codex/mvp-phase-33-scenario-simulation`；当前只写入计划，不改动实现。
- 计划 `docs/plans/2026-09-02-mvp-phase-33-scenario-simulation.md` 明确四个固定、
  fixture-first 的假设场景：`BASELINE_READY`、`TIGHTER_TECH_CAP`、
  `TOP_ASSET_TRIM_10PP`、`LOOKTHROUGH_PARTIAL`；输出基线→模拟的 Decimal 差异、
  假设和失效条件，保持 `READY/REVIEW_REQUIRED/BLOCKED`，不产生 Fact/Finding/
  Recommendation/DecisionEvent。
- 计划固定复用 Phase 24 场景目录、Phase 28 暴露/风险/优化算术、Phase 31 Evidence
  explorer 和 Phase 32 中文映射/导航，禁止实时 SkillHub、LLM/Gemini、预测、回测、
  交易、持久化、Recommendation History、Portfolio Rebalancing 与 Dashboard。
- 当前状态为 `PLANNED`；下一 agent 应先读计划并执行契约先行、独立审查和全量验收，不能
  把本阶段计划或 Phase 32 的 `436 passed` 冒充为 Phase 33 实现证据。
## 2026-09-07 — 扶摇金融数据服务端接入

- 新增服务端 `FuyaoFinanceProvider`，通过 `HITHINK_FINANCE_API_KEY` 调用扶摇 REST API；密钥不进入前端、响应、日志或仓库文件。
- LIVE 模式已接通 A 股行情快照和基金重仓披露接口。行情记录上游时间、延迟与新鲜度；基金持仓固定标记为 `PERIODIC_DISCLOSURE`，行业分布不可用时显式保留 `missing_fields`。
- 扶摇 HTTP 200 业务错误按响应体 `code` 拦截；LIVE 失败返回明确错误，不回退到 MOCK 静态底稿。
- 启动时先对行情与场内基金能力执行真实请求探测，只有至少一项验证成功才允许进入 LIVE；Copilot 工具与自动建档路径均复用同一服务端实例，LIVE 数据不会写入 MOCK 静态底稿。
- 首次能力探测采用单事务锁避免并发覆盖；每项能力记录最近校验时间和失败码，运行中失效会同步到前端，最后一项能力失效时明确切回 MOCK。扶摇公开调用增加不超过 1.5 秒的端到端墙钟截止时间。
- 真实连通性验证：`600519.SH` 行情成功；`510300.SH` 返回 10 条最近一期披露持仓；Prism 模式、行情、基金三个 HTTP 路径均成功。
- 验证：当前环境未安装 `uv`，使用项目虚拟环境执行等价全量命令 `.venv\\Scripts\\python.exe -m pytest`，结果为 `519 passed`；`compileall`、`node --check`、`git diff --check` 通过；`app.js` 保持 0 `innerHTML` / 0 `outerHTML`；浏览器完成 LIVE → MOCK → LIVE 往返，并在受控 SSE 权限失效场景中同步切回 MOCK，控制台无错误。

## 2026-09-07 — 扶摇与问财能力合并

- 在远端问财公告、语义检索、通用查询和组合刷新实现之上合并扶摇实时行情与基金披露能力。两套 Provider 独立裁决，不以一方静默替代另一方。
- 扶摇单独可用时，问财刷新会明确标记为未执行，组合体检与调仓继续使用用户已确认持仓，由 Python 确定性服务完成计算。
- 问财返回认证、权限、超时、传输或上游失败后，运行时会撤销问财能力并记录失败码；若扶摇仍可用则保留 LIVE，若无外部能力则切回 MOCK。
- 浏览器验收确认顶栏显示 `LIVE · 扶摇数据`，并准确提示问财能力不可用；体检区显示未刷新原因且成功返回 Python 验算结果。真实 HTTP 验证中，`600519.SH` 行情和 `510300.SH` 的 10 条披露持仓均来自扶摇且 `is_synthetic=false`。
- 验证：全量测试 `526 passed`；`compileall`、`node --check`、`git diff --check` 通过；`app.js` 保持 0 `innerHTML` / 0 `outerHTML`。

## 2026-09-14 — 国内、港股、美股大盘鉴别增强

- 建立三市场固定指数注册表与 `/api/v1/market/catalog`、`/api/v1/market/quotes/{market}`、`/api/v1/market/analysis/{market}/{index_id}` 接口；港美股代码或iFinD权限未验证时明确返回 `UNAVAILABLE`。
- 新增服务端iFinD QuantAPI适配器，认证信息仅从服务端环境读取；历史OHLCV、月线聚合、BOLL、MACD、KDJ、量能比及宏观相关性均由确定性代码计算。
- 将大盘页面升级为国内、港股、美股三级标签、横向指数卡片、本地Lightweight Charts 5.2.1多窗格图表、日/月周期、范围缩放、十字线与宏观因子卡片；行业观察仅在国内市场展示。
- 美国10年期国债收益率、Brent原油和COMEX黄金独立降级；国内及港股因子采用严格前序观测，防止使用本地收盘之后产生的美国市场数据。

## 2026-09-15 — 真实组合刷新、优化与调仓闭环

- 修复问财 SkillHub `items/columns` 包装结果未映射到 `price_cny/observed_at/sector` 导致组合刷新统一报错的问题。
- 新增真实组合数据适配器：股票价格取已验证且明确非合成的扶摇行情，行业取问财公司数据 Skill；任一字段无法核验即进入复核，不使用原持仓行业冒充刷新结果，也不回退 Fixture。
- 将组合刷新能力从“问财九个 Skill 全部成功”中解耦。扶摇行情可用时，问财市场 Skill 的独立 401 不再关闭组合体检。
- 组合能力改为操作级裁决：仅当扶摇股票报价与问财公司/行业补全共同可用时才标记刷新、优化、调仓可用；问财行业补全的认证、传输或响应失败会立即撤销该操作能力，避免“报价可用”被误报为“完整组合可用”。
- 服务重启或五分钟可信期失效时，后端返回结构化刷新错误；前端清除本地完成标记，使下一次操作重新执行真实刷新。可信期使用单调时钟，避免系统时间回拨延长有效期。
- 新增不加载合成组合模板的确定性组合优化服务；LIVE 仅接受当前提交的 `BASELINE_READY` 持仓，前端直接构造真实持仓目录，不读取 Fixture template。调仓继续由 Python 计算整手、费用、现金与交易后体检。
- 浏览器实测当前五只股票组合：真实刷新后总资产为 `1,468,535 CNY`；组合体检完成；调仓生成 1 个减持步骤，换手率 `4.35%`、费用 `97.13 CNY`，并因交易后 HHI 仍超限而正确返回 `REVIEW_REQUIRED`。
- 完整股票/基金/可转债研究、研究矩阵、预设情景、投顾与固定工作流仍为 Fixture，LIVE 继续拒绝；Copilot 个股行情和基金披露是真实但部分数据，缺项明确保留。
