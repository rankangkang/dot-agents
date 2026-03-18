---
title: Python 任务队列：asyncio 技术栈选 arq，复杂工作流才上 Celery
type: research
tags: [python, task-queue, celery, dramatiq, arq]
source_tool: claude
source_id: 789abc-012def
created: 2026-03-12
---

## 核心约束

项目是 FastAPI + asyncio 技术栈，Redis 已在用，任务逻辑简单（发邮件、生报表），日均 5 万，不需要复杂工作流（优先级队列、canvas 组合、定时调度等）。

## 决策分叉点

```
你的技术栈是 asyncio 吗？
  ├─ 是 → 任务逻辑需要复杂工作流（canvas/优先级/多 broker）吗？
  │    ├─ 是 → Celery（生态最全，但和 asyncio 不是原生集成）
  │    └─ 否 → arq（纯 asyncio，2 个依赖，5 分钟上手）
  └─ 否 → 追求简洁 API → Dramatiq；需要全家桶 → Celery
```

关键对比：arq 只支持 Redis 做 broker，没有优先级队列，社区最小。但如果你已经用 Redis 且任务简单，这些都不是问题。

## 什么时候该换

如果后续出现以下任一需求，从 arq 迁移到 Dramatiq（API 风格相近，迁移成本低）：
- 需要 RabbitMQ 做 broker（消息可靠性要求高）
- 需要优先级队列
- 需要限速/限流控制
- Worker 数量超过 20 台
