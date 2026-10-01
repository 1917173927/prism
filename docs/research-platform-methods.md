# Prism 研究平台计算及资料契约

## 第1章 输入与时点

### 一、 通用约束

所有计算输入必须声明来源及带时区的 `as_of`。金融收益使用小数比例，基础行情图表使用百分数，两者不得混用。算法返回输入摘要、方法版本和失败原因；自行上传的来源标签仅表示用户声明，不证明来源独立性。

| 输入领域 | 字段 | 固定口径 | 阻断条件 |
| --- | --- | --- | --- |
| 收益序列 | time、value | 已复权且按日期升序、唯一 | 非有限值、未来日期、重复日期 |
| 状态模型 | returns、training_size | 首个训练窗口至少252日 | 短样本、退化方差、不收敛 |
| 协方差 | series | 2—100资产，共同有效日期至少60日 | 缺共同日期、零方差；不补缺失收益 |
| 因子 | fundamentals、months、universe_id | 原始财务、公告时点、历史成分、月初市值及无风险收益 | 缺字段、未来公告、空组合 |

## 第2章 状态模型

### 一、 两状态高斯模型

采用 `hmmlearn==0.3.3` 的两状态高斯HMM，固定种子0、1、2，最多500迭代，收敛容差 `1e-6`，按训练似然选取收敛解。状态按方差排序。模型参数仅使用声明训练窗口；从训练结束日开始输出前向过滤概率，历史信号不使用平滑概率或未来收益。概率和误差须不超过 `1e-10`。

这是A股日频适配，不将高低波动状态解释为牛熊或买卖指令。原理依据：[Ang–Bekaert论文](https://drupalgsb-dev.cc.columbia.edu/sites/default/files-efs/pubfiles/1971/1137.pdf)。

## 第3章 五因子

### 一、 结构化导入

| 字段组 | 必需字段 | 单位与期间 | 使用时点 |
| --- | --- | --- | --- |
| 标的与历史集合 | security_id、formation_year、universe_id | 明确输入集合 | 每年7月重组 |
| 财务与披露 | fiscal_year、published_at、book_equity、revenue、cost_of_goods_sold、selling_general_administrative、interest_expense | 同一币种；前一财年 | 6月末之前已公告 |
| 规模与资产 | market_cap_december、market_cap_june、total_assets、prior_total_assets | 同一币种；规模值大于0 | 12月、6月和对应财年 |
| 月收益 | month、risk_free_return、securities | 小数收益；证券含total_return与beginning_market_cap | 不晚于as_of |

规模以50%分位划分，B/M、盈利能力和资产增长以30%与70%分位划分；三组各六组合均采用月初市值权重。SMB为三组规模差均值；HML为高减低B/M，RMW为高减低盈利，CMA为低减高投资，MKT−RF为输入集合的市值加权收益减无风险收益。负账面权益明确排除；必要数据缺失时不缩小集合冒充完整结果。来源依据：[French五因子构建说明](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html)。

## 第4章 常相关协方差收缩

### 一、 固定估计量

收益去均值后使用 `S=XᵀX/T`，目标对角保留样本方差，非对角采用平均相关系数乘两资产标准差。按论文附录估计第四阶矩、目标协方差的误差协方差与目标距离，收缩强度截断至 `[0,1]`。独立逐项标量基准验证强度和矩阵；对称性、最小特征值及共同样本量单列输出。来源依据：[Ledoit–Wolf常相关目标论文](https://bse.eu/sites/default/files/working_paper_pdfs/92.pdf)。

## 第5章 资料与检索

### 一、 原文与输出边界

文档保存原文、页码、段落、版本、哈希、主体、期间、公开时点和权限。PDF扫描页没有可靠文本时返回待复核。中文以确定性双字词索引；SQLite使用FTS5，PostgreSQL使用服务端全文索引。更正及删除立即失效旧文段及引用。

本地模型为 `intfloat/multilingual-e5-small`，修订 `614241f622f53c4eeff9890bdc4f31cfecc418b3`；查询加 `query: `，文段加 `passage: `，缓存放在私有目录。关键词、向量各召回50项，以RRF `k=60`合并前10项。可见权限与时点先过滤；输入集合截断必须明确报告。默认使用关键词；全部金融质量门槛未完成时不开放默认混合模式。

聊天工具只接受查询、主体、期间和历史时点；owner来自服务端。输出前再次核验原文版本，确定性转述原文，不把引用存在认定为支持金融声明。模型说明：[multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small)；采集约束：[arXiv官方API说明](https://info.arxiv.org/help/api/user-manual.html)。
