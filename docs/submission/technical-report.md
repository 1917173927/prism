# Prism 技术设计文档

> 文档阶段：第一轮骨架与大纲
>
> 结构基线：基于 arc42-lite，并结合 Prism 的工程实现与比赛展示要求组织。
>
> 叙事主线：Personalization → Evidence → Deterministic Risk / Decision
>
> 写作重点：系统能力、架构结构、接口契约、运行流程、确定性计算和验证证据。

## 1. 项目概述与赛题理解

### 1.1 项目背景与赛题理解

### 1.2 核心问题

### 1.3 Prism 的解决方案

### 1.4 核心设计原则

### 1.5 目标与非目标

## 2. 需求与系统约束

### 2.1 功能需求

### 2.2 个性化投顾需求

### 2.3 金融数据真实性要求

### 2.4 风险与合规约束

### 2.5 性能与工程约束

## 3. 系统总体架构

### 3.1 Architecture Overview

### 3.2 系统分层

### 3.3 模块职责

### 3.4 外部系统与数据源

## 4. Agent 协作与任务执行

### 4.1 Central Orchestrator

### 4.2 Specialist Agents

### 4.3 Task DAG

### 4.4 运行时流程

### 4.5 异常与降级

## 5. Evidence Architecture

### 5.1 Evidence First 原则

### 5.2 Evidence / Fact / Finding / Recommendation

### 5.3 数据血缘与可追溯性

### 5.4 交叉验证

### 5.5 数据冲突与缺失处理

## 6. 用户画像与个性化机制

### 6.1 风险测评

### 6.2 Investor Profile

### 6.3 Portfolio Context

### 6.4 个性化约束生成

### 6.5 画像如何影响最终建议

## 7. 确定性金融计算与组合分析

### 7.1 Portfolio Exposure

### 7.2 基金 / ETF 穿透

### 7.3 Concentration Risk

### 7.4 Risk Budget

### 7.5 Allocation Envelope

### 7.6 目标结构与组合优化

### 7.7 Scenario Simulation

### 7.8 Rebalancing

### 7.9 精度、守恒、舍入和计算边界

## 8. 风险控制与合规

### 8.1 Suitability Gate

### 8.2 Risk Gate

### 8.3 Compliance Gate

### 8.4 Recommendation Eligibility

### 8.5 安全边界

## 9. 数据与外部能力

### 9.1 同花顺问财 / SkillHub

### 9.2 行情与其他 Provider

### 9.3 Provider Protocol

### 9.4 数据状态模型

### 9.5 Graceful Degradation

## 10. 工程实现与部署

### 10.1 技术栈

### 10.2 Backend

### 10.3 Frontend

### 10.4 Persistence

### 10.5 Deployment

### 10.6 Security

## 11. 测试与评估

### 11.1 Unit Tests

### 11.2 Contract Tests

### 11.3 Integration Tests

### 11.4 Browser / E2E Tests

### 11.5 Deterministic Replay

### 11.6 Evaluation Cases

### 11.7 Local Load Test

### 11.8 质量场景与验收证据

## 12. 架构决策、系统边界与未来工作

### 12.1 关键架构决策

### 12.2 系统边界与适用条件

### 12.3 已知技术问题

### 12.4 技术债务

### 12.5 后续工作

### 12.6 术语表与代码索引
