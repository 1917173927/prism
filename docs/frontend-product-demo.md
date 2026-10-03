# Prism 前端主题与产品 Demo

## 第1章 入口与使用方式

1. 在项目根目录双击 `start-product-demo.cmd`，或运行 `.venv\Scripts\python.exe -m tools.product_demo`。
2. 打开 `http://127.0.0.1:8860/demos/product-demo/#overview`，通过左侧导航切换页面。
3. 点击“截图模式”，或使用 `http://127.0.0.1:8860/demos/product-demo/?capture=1#overview`。演示工具栏隐藏，DEMO 标记持续显示。
4. 未打开引用时按 `Esc` 退出截图模式；引用打开时先关闭引用。点击“重置演示”恢复预设状态。
   手机通过顶部小图标退出截图模式，再点击“重置演示”。
5. 本入口只需 Python 标准库，绑定本机地址；不启动业务 API，不要求账户、数据库或 Provider 凭据。

## 第2章 页面与演示交互

| 页面 | 主要展示 | 演示操作 | 地址片段 |
| --- | --- | --- | --- |
| 研究对话 | 固定研究说明、声明及关联资料 | 示例问题、文字提交、引用查看 | `#copilot` |
| 持仓分析 | 资产、收益、配置、持仓及风险 | 组合图表、跨页研究入口 | `#overview` |
| 市场观察 | 指数日线、基础指标及观察板块 | 指数、日／月周期切换 | `#market` |
| 交易风格 | 行为指标、近期记录、研究习惯 | 查看固定行为样例 | `#trading-style` |
| 个人中心 | 画像、评级、问卷摘要及解释偏好 | 三个子标签、解释详细度 | `#profile` |
| 技能商店 | 固定九项能力及版本状态 | 搜索、分类、演示选择 | `#skill-store` |
| 研究知识库 | 演示资料、主体、期间及片段 | 文本匹配、引用抽屉 | `#research-knowledge` |
| LIVE 研究 | 研究目标、阶段进度及资料缺口 | 运行固定演示、取消 | `#live-research` |
| 论文算法 | 状态概率、收缩矩阵、五因子缺口 | 查看合成输入的冻结算法结果 | `#research-algorithms` |

LIVE 页的运行是本地步骤演示；技能选择只影响演示状态。知识检索为固定文档文本匹配，未调用模型或实际混合检索。未覆盖的自由问题明确返回演示未覆盖，引用的存在不冒充真实论文、公告或财报支持。

## 第3章 样式与数值边界

| 领域 | 统一约定 | 实际实现 | 保留约束 |
| --- | --- | --- | --- |
| 主色 | 白／浅灰面板、橙色强调 | 共享 `design-tokens.css` | 深浅主题保持独立色值 |
| 字体 | 中文无衬线，金额和状态等宽 | 标题 28／24／18 px | 字体使用本机资源 |
| 组件 | 卡片 16 px、按钮 38 px、间距以 4 px 为单位 | `product-theme.css` 与 Demo 样式 | 正式导航及子页显隐保留 |
| 图表 | 现有 Lightweight Charts 5.2.1 | 本地打包资源 | 隐藏、重显、缩放释放旧资源 |
| 数值 | 固定合成样例 | Python Decimal、NumPy、既有论文算法 | 浏览器不计算风险、调仓或金融指标 |
| 数据边界 | DEMO 持续标注 | 固定快照、本地状态、零 Provider／模型调用 | 不读取或写入真实用户资料 |

`tools/build_product_demo_data.py` 可重建冻结快照；HMM 和协方差采用现有确定性算法计算合成输入，五因子缺完整输入时保持 `UNAVAILABLE`。产品截图用于展示界面，不作为真实行情、上游配额、研究质量或投资建议的验收材料。

## 第4章 交付与归档

`tools/package_product_demo.py` 生成 `output/product-demo/prism-product-demo.zip`，仅打包声明的 Demo 文件、共享主题、品牌图标、Lightweight Charts 及授权文件，附带本机预览入口。已验证的[便携包](showcase/product-demo-20261003/prism-product-demo.zip)与截图一并归档。截图与最终浏览器验证分别留存在 `docs/showcase/product-demo-20261003/` 和 `docs/submission/test-evidence/product-demo-20261003/`。

正式主题阶段已提交推送 `81b133f`，相关 62 项测试与三视口 27 次导航通过。独立 Demo、截图及便携包已提交推送 `3c0b369`；最终验证记录于 `LOG.md`。Pages 发布保持停用。

独立 Demo 完成三视口 27 次页面检查及 18 项实际交互，11 项专项回归通过；含本机 PostgreSQL 的全量回归为 `1110 passed, 1 skipped`。截图合集为 [产品截图](showcase/product-demo-20261003/index.html)，包含 9 页桌面版及平板、手机总览。便携包的 12 个资源均已校验，运行需 Python 3，无其他后端依赖。
