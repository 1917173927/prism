# Prism 技术机制拆分动画

## 第1章 演示文稿

[Prism技术机制拆分动画.pptx](Prism技术机制拆分动画.pptx)包含五页16:9幻灯片，采用蓝白渐变背景、简短中文标题及中心技术示意图。

| 页码 | 内容 | 独立图片部分 | 主要呈现顺序 | 来源 |
|---|---|---|---|---|
| 1 | 受约束的研究定义生成 | 7 | 描述、解析、目录、定义、确认、计算、结果 | 01-constrained-method-definition.png |
| 2 | 内容指纹驱动的变化记录 | 6 | 上排从左至右，再呈现下排复核与变化记录 | 02-content-fingerprint-events.png |
| 3 | 公告主体与持仓敞口关联 | 9 | 上排主体与直接关联，下排穿透，最后残余 | 03-announcement-exposure-paths.png |
| 4 | 风险检查后的虚拟账本更新 | 14 | 共同数据、同一基线、策略A、策略B | 04-gated-virtual-ledger.png |
| 5 | 按日期分配同一资金池 | 6 | 现金、分配、需求、时间约束、收入、日期轴 | 05-dated-funding-pool.png |

源图片及技术说明位于[五张技术配图](../../figures/innovation-details-20261007/README.md)。

## 第2章 播放与编辑

1. 在PowerPoint中打开文件，按F5从第一页放映，或按Shift+F5从当前页放映。
2. 每页进入后，标题与图片部分按上排至下排、各排从左至右的阅读顺序自动淡入。单项淡入0.4秒，后续项目等待上一项完成并间隔0.06秒。
3. 页面之间采用0.5秒淡化，点击进入下一页。
4. 在选择窗格中可独立选中命名的图片部分，调整位置、裁切和动画。图内标签保留于源图片，标题为可编辑文本。
5. 五张源图内的金额及比例均为示意数据，适用边界保留于演讲者备注。

## 第3章 生成入口

生成脚本保留原始图片字节，用PowerPoint原生裁切将图形区域拆为独立对象，整体拼合关系保持一致。图形对象的轮廓属于原有技术示意图，不额外添加页面外框。

| 步骤 | 工具 | 输入 | 输出 |
|---|---|---|---|
| 构建 | [build_innovation_animation.mjs](../../../../tools/build_innovation_animation.mjs) | 五张PNG及区域配置 | 私有草稿及部分清单 |
| 精确裁切 | [fix_innovation_picture_crops.py](../../../../tools/fix_innovation_picture_crops.py) | 草稿及源区域坐标 | 原生裁切草稿 |
| 动画 | [animate_innovation_parts.ps1](../../../../tools/animate_innovation_parts.ps1) | 精确裁切草稿 | PowerPoint原生淡入动画 |
| 导出 | [finalize_innovation_animation.mjs](../../../../tools/finalize_innovation_animation.mjs) | 动画草稿 | 独立正式PPTX |

构建使用已配置的内置JavaScript运行时及artifact-tool，构建模块需在私有构建目录运行并链接运行时node_modules。动画工具依赖本机PowerPoint。工具中默认路径适用于当前工作环境，可通过环境变量或参数指定相应路径。中间文件位于项目忽略目录output/innovation-animation-20261007，正式交付文件位于本目录。
