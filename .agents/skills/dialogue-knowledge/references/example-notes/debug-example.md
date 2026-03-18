---
title: FastAPI 路由中嵌套代码块导致 JSON 解析截断
type: debug
tags: [python, fastapi, json, markdown]
source_tool: cursor
source_id: abc123-def456
created: 2026-03-15
---

## 问题现象

在 FastAPI 接口中返回包含 Markdown 代码块的 JSON 响应时，前端只收到一半内容。浏览器 DevTools 显示响应 body 在某个 ``` 标记处被截断。

## 排查过程

1. **初步怀疑 Content-Length 不匹配** — 检查响应头，发现 `Content-Length` 确实小于实际 body 长度
2. **排除中间件问题** — 移除所有中间件后问题依旧
3. **定位到序列化环节** — 用 `json.dumps()` 手动序列化对比，发现 FastAPI 默认的 `jsonable_encoder` 对包含反引号的字符串处理异常
4. **根因确认** — 当 Markdown 内容包含 ```` ``` ```` 时，`orjson`（项目替换了默认 JSON 引擎）的某个版本存在 bug，将三个反引号误判为字符串结束符

## 根因

`orjson==3.9.2` 在处理包含连续反引号的字符串时存在边界 bug，导致 JSON 输出提前截断。

## 解决方案

```bash
pip install orjson==3.9.7  # 升级到修复版本
```

## 教训

- 替换 JSON 引擎后要用包含特殊字符（反引号、Unicode、嵌套引号）的测试数据做回归
- 当 `Content-Length` 与实际 body 不一致时，优先检查序列化环节而非传输环节
