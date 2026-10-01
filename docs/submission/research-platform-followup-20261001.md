# Prism研究平台续验收与用户操作

## 第1章 已处理事项

### 一、 PostgreSQL及Pages

| 项目 | 实际处理 | 验证 | 当前边界 |
| --- | --- | --- | --- |
| PostgreSQL | 官方Windows x64 17.11，安装于data/private/postgresql | 13项真实迁移、回滚、全文、隔离、CAS及事实原文回归通过 | 单机数据库；未搬迁原SQLite |
| 连接与角色 | 127.0.0.1:55432；prism_test、prism_app独立库与角色 | 健康、停启及重复初始化通过 | 只监听回环；密码由Windows DPAPI保存 |
| 操作助手 | tools.local_postgres；status/start/stop/test/serve | 可用，无需手工复制密码或DSN | 重启Windows后执行start |
| Pages | 删除自动发布工作流，撤销发布验收 | 已推送5d39caa | 保留静态快照作历史数据及回归 |
| 安装及数据适配 | 本地环境与LIVE元数据修复 | 已推送5dd6ffc | 缺少真实元数据仍返回PARTIAL |

需要查看数据库状态或再次验收时，在仓库目录执行：

```powershell
.\.venv\Scripts\python.exe -m tools.local_postgres status
.\.venv\Scripts\python.exe -m tools.local_postgres test
```

完整操作见[运行与复验说明](../research-platform-operations.md)，安装实测见[数据库证据](test-evidence/research-postgres-installed-20261001.json)。原账户与持仓继续使用原SQLite；可选PostgreSQL应用入口为`python -m tools.local_postgres serve --port 8001`，使用独立空应用库，不自动迁移旧业务资料。

## 第2章 上游额度

### 一、 失败位置及操作

| 项目 | 已确认事实 | 用户操作 | 未知信息 |
| --- | --- | --- | --- |
| 服务 | 问财SkillHub，hithink-market-query | 登录[问财SkillHub](https://www.iwencai.com/skillhub)对应Key的账户，查看当日查询用量和权益 | 具体套餐总次数及重置时刻未留存 |
| 端点 | POST /v1/query2data；查询“贵州茅台最新价” | 核实此技能的调用次数，恢复额度后再测 | 不把行情技能次数当作全部服务额度 |
| 负载结果 | 25成功、50成功，100任务24成功／76额度拒绝 | 额度不足时等待平台重置或按实际需求调整权益 | 不能据此推断套餐总额度为100 |
| 识别依据 | 上游401／403含“今天的次数已用完”或“今日额度已用完”映射QUOTA_EXHAUSTED | 此情况无需重新填写相同Key | 旧原始响应正文未归档，只有错误码与状态 |
| 其他容量 | 该轮没有调用模型或扶摇；本地活动峰值100 | 本次失败先处理问财日次数 | 不证明其他服务权益充足 |

未再次消耗上游额度。剩余真实压力验收要求25、50、100各三轮，即至少525个研究任务；实际调用数还取决于每任务节点数、探测和重试。原测试每任务只有一个quote节点，不能用该次数估算两节点完整LIVE模板的同等成本。重测时使用受支持Python并保留完整结果与原始事实。

### 二、 当前行情元数据

先前成功结果还缺单位或真实观察时间。已修复读取响应明确提供的`columns[].key/unit`、中文观察时间别名和报告期；没有字段则仍为PARTIAL，不能填默认人民币或拿抓取时间代替行情时间。旧真实原始响应已丢失，不能证明当时响应中实际上具有这些字段。

问财查询的历史as_of当前用于结果资格过滤，不会自动把“最新价”查询变成历史行情请求。历史研究需要明确日期的供应商查询或历史数据接口。

## 第3章 真实输入清单及获取渠道

### 一、 通用及状态／协方差

所有JSON须包含来源说明`source`和带时区`as_of`。收益用小数比例，例如0.01表示1%，日期唯一升序。数值使用JSON number，不能为字符串、布尔值或NaN。页面入口为工作台“论文算法”，接口为`/api/v1/research/algorithms/*`。

| 算法 | 必需输入 | 当前缺口 | 可准备的数据 |
| --- | --- | --- | --- |
| HMM | returns[{time,value}]；默认训练252日 | 留存485收益已计算通过；当前行情历史需另取得 | 授权指数或证券历史收盘价／收益；明确价格指数或总收益口径 |
| 协方差 | series{证券ID:[{time,value}]}；2资产、60共同有效日，方差非零 | 留存只有一个资产 | 至少两资产同日期、同口径复权或总收益历史；不补缺失为零 |
| 共同元数据 | 来源、证券／观察集、单位、时点、方法与数据版本 | 最新行情不等于历史完整数据 | 供应商导出说明及公司行动／停牌／退市处理口径 |

已接入的历史行情接口或授权行情导出均可作为输入来源；实际可下载范围取决于供应商权益。现有历史HMM证据不代表当前行情、全市场或供应商容量。

### 二、 五因子

五因子需要一套完整历史截面，而非增加一项“最新财务”字段。形成年度记为t，按每年7月重组；财年为t−1，使用t年6月底前已公告资料。金额统一人民币与倍率，顶层声明`monetary_unit:"CNY"`、`universe_id`及`universe_complete`。

| 数据组 | JSON字段 | 时点与最低口径 | 获取渠道及核查 |
| --- | --- | --- | --- |
| 历史集合 | 各年度fundamentals和各月securities；universe_id | 当时入样、上市退市及覆盖；不得用今天成分回填 | 授权历史成分／证券主表，或指数机构历史调整公告 |
| 年度标识 | security_id、formation_year、fiscal_year、published_at | t、t−1及带时区首次／修订公告时点 | [巨潮资讯](https://www.cninfo.com.cn/)及交易所原始年报、披露记录 |
| 历史市值 | market_cap_december、market_cap_june | t−1年12月底及t年6月底总市值 | 授权历史总市值，或历史价乘当日股本；不能使用今天股本 |
| 财务 | book_equity、revenue、cost_of_goods_sold、selling_general_administrative、interest_expense | t−1年账面权益、收入、营业成本、销售及管理费用合计、利息支出 | 问财按年度／报告期结构化导出并对照年报；财务费用不能直接代利息支出 |
| 资产 | total_assets、prior_total_assets | t−1及t−2年总资产 | 两期年报；公告时点及修订版本保留 |
| 月收益及权重 | months[{month,risk_free_return,securities:[{security_id,total_return,beginning_market_cap}]}] | 月含股息总收益、月初市值；包含形成集合所需成员 | 授权总收益／复权行情与分红送转拆股记录；最新价不可替代 |
| 无风险月收益 | risk_free_return | 与月份匹配的小数持有期收益 | [中债](https://yield.chinabond.com.cn/)或[中国货币网](https://www.chinamoney.com.cn/chinese/bkcurvclosedy/)等明确的人民币代理；期限、日计数和折算公式需确定性记录 |

年化收益率不能直接填入月收益。资料使用与下载权益须按各来源授权范围处理。三组2×3组合都必须非空，至少6个合格证券仅是结构下限，不是全市场数据证明；负账面权益依方法剔除。缺少收益成员或必要财务会阻断，不缩小样本伪装完整结果。

## 第4章 人工质量评测操作

### 一、 入口及所需操作

打开本地[人工标注页](http://127.0.0.1:8023/static/research-quality-review.html)。这是只读静态工具，不调用模型或金融Provider；也可在正常应用中访问`/static/research-quality-review.html`。页面提供非金融示例和真实资料空模板，不预填人工标签。

1. 下载示例并导入，熟悉标注及导出；示例结果始终不能通过真实金融门槛。
2. 准备真实评测包：至少100个冻结问题，覆盖正常、缺失、过期、冲突、隔离、注入，保存实际回答、原文、引用、检索顺序及完整原子声明。
3. 逐题标注“原文是否支持声明”“引用是否支持”“关键数值及独立来源是否一致”“资料是否充分”“拒答是否合理”“是否发生隔离或时点错误”，填写依据。关键数值必须核对字段、单位、期间、容差及独立参考值。
4. 导出标注JSON；刷新前务必导出。然后执行汇总：

```powershell
.\.venv\Scripts\python.exe tools/summarize_research_quality_review.py --input 标注文件.json --output output/research-quality-summary.json
```

完整字段、样例和统计说明见[人工评测操作指南](../research-quality-review-guide.md)。标签由用户或具备领域能力的复核人员填写，不能让模型自评后充当人工验收。没有标注、真实原文、100题完整场景或关键金融数值分母时，金融门槛不通过；零分母为N/A。当前已交付入口与统计，人工金融质量验收仍待操作完成，生产混合检索继续默认关闭。

### 二、 验收记录

最终全量回归为**1068 passed、1 skipped、0 failed**，132.03秒，使用Python3.12.12和锁定的psycopg3.3.5；原12项数据库跳过已解决，并追加1项事实原文回归。剩余跳过仅为默认未开启的本地模型专项；此前固定模型已专项通过。人工标注13项单测及三视口导入／标注／导出／汇总浏览器回归通过，页面脚本错误和API调用均为0，空真实模板为UNVERIFIED。原始记录及截图见[续验收证据](test-evidence/research-followup-verification-20261001.json)。

2026年10月1日前次[验收报告](research-platform-acceptance-20261001.md)为历史基线；其中PostgreSQL环境缺失现已解决，Pages发布现已撤销，其余真实数据、上游额度和人工质量条件按本文件继续跟踪。真实人工标注尚未完成，测试标签不算实际质量验收；默认混合检索继续关闭。
