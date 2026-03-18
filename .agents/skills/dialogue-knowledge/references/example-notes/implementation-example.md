---
title: rsync include/exclude 顺序陷阱：目录必须先 include
type: implementation
tags: [rsync, ssh, python]
source_tool: cursor
source_id: 345ghi-678jkl
created: 2026-03-16
---

## 要做的事

用 rsync 从远程开发机同步 `.jsonl` 文件到本地，只要 `.jsonl`，不要其他文件，但要保留目录结构。

## 不查就写不出来的部分

### rsync 的 include/exclude 顺序

```bash
rsync -avz \
  --include='*/' \          # 1. 先放行所有目录
  --include='*.jsonl' \     # 2. 再放行目标文件
  --exclude='*' \           # 3. 最后排除其余一切
  remote:~/.cursor/projects/ \
  local/archive/
```

**`--include='*/'` 必须在 `--exclude='*'` 前面。** 否则目录本身会被排除，rsync 根本不会进入子目录去找 `.jsonl` 文件。这个顺序每次都会忘。

### SSH subprocess 防挂起

用 `subprocess` 调 SSH 时，如果远程主机要求密码，进程会静默挂起。两个必加参数：

```python
["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, cmd]
```

`BatchMode=yes` 禁止交互式密码提示（直接报错退出），`ConnectTimeout=5` 防止不可达主机阻塞整个流程。

## 踩坑

- **rsync 尾部斜杠**：`remote:path/` 同步目录内容，`remote:path` 同步目录本身（连目录名一起带过来）。每次都搞混，记住：**想要内容就加斜杠**
- **rsync 返回码 23**：部分文件传输失败（通常是权限），不是致命错误，可以 `returncode in (0, 23)` 都视为成功
