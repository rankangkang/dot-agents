---
title: orjson 遇到连续反引号会截断 JSON 输出
type: debug
tags: [python, fastapi, orjson, json]
source_tool: cursor
source_id: abc123-def456
created: 2026-03-15
---

## 症状

FastAPI 接口返回的 JSON 被截断——前端只收到一半。DevTools 里看到响应 body 在某个 ``` 标记处断掉，`Content-Length` 比实际 body 小。

## 弯路

第一反应是怀疑传输层（中间件、nginx），花了 20 分钟逐个排除。实际上 `Content-Length` 不匹配这个线索已经指向了**序列化环节**——响应还没发出去就已经错了，根本不用查传输。

## 根因

项目把 FastAPI 的 JSON 引擎换成了 `orjson`。`orjson==3.9.2` 在处理包含连续反引号（` ``` `）的字符串时有边界 bug，会提前截断输出。升级到 `3.9.7` 修复。

## 下次怎么查

看到 `Content-Length` 与 body 长度不一致 → **先查序列化**，不查传输。用 `json.dumps()` 手动序列化对比，10 秒就能定位到是不是 JSON 引擎的锅。

## 教训

替换 JSON 引擎（orjson、ujson 等）后，测试用例里要包含特殊字符：连续反引号、Unicode emoji、嵌套引号、超长字符串。这些是序列化引擎最容易出 bug 的地方。
