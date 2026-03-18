---
title: Python 任务队列选型：Celery vs Dramatiq vs arq
type: research
tags: [python, task-queue, celery, dramatiq, arq]
source_tool: claude
source_id: 789abc-012def
created: 2026-03-12
---

## 背景

项目需要异步处理邮件发送和报表生成，日均任务量约 5 万，需选择合适的任务队列方案。

## 候选方案

### Celery
- **优点：** 生态最成熟，支持多种 broker（Redis/RabbitMQ），文档丰富，社区活跃
- **缺点：** 依赖重（`kombu`, `vine`, `billiard` 等），配置复杂，冷启动慢，内存占用高
- **适用场景：** 大型项目、需要复杂路由/优先级/canvas 工作流

### Dramatiq
- **优点：** API 简洁（装饰器风格），性能优于 Celery，支持 RabbitMQ/Redis，内置重试/限速
- **缺点：** 生态不如 Celery 丰富，不支持 canvas 式工作流组合，社区较小
- **适用场景：** 中型项目、追求简洁 API 和更好性能

### arq
- **优点：** 极轻量（纯 asyncio），与 FastAPI/aiohttp 天然契合，类型提示完善
- **缺点：** 只支持 Redis 作为 broker，功能最少（无优先级队列），社区最小
- **适用场景：** asyncio 技术栈的小中型项目

## 对比结论

| 维度 | Celery | Dramatiq | arq |
|------|--------|----------|-----|
| 依赖数 | 10+ | 3 | 2 |
| asyncio 原生 | ✗ | ✗ | ✔ |
| Broker 选择 | Redis/RabbitMQ/SQS | Redis/RabbitMQ | Redis |
| 学习成本 | 高 | 低 | 低 |
| 5 万任务/天 | 绰绰有余 | 绰绰有余 | 足够 |

## 最终选择

选择 **arq**。理由：项目已是 FastAPI + asyncio 技术栈，任务逻辑简单（不需要复杂工作流），Redis 已在用，arq 的轻量和原生 asyncio 支持是最佳匹配。如果未来任务复杂度增长，可迁移到 Dramatiq（API 风格相近，迁移成本低）。
