---
title: 用 SSH config + rsync 实现远程 AI 对话文件同步
type: implementation
tags: [ssh, rsync, python, subprocess]
source_tool: cursor
source_id: 345ghi-678jkl
created: 2026-03-16
---

## 需求概述

从远程开发机同步 AI 编程工具（Cursor/Claude Code）的对话文件到本地，要求增量同步、自动发现远程主机。

## 技术方案

1. 读取 `~/.ssh/config` 获取已配置的远程主机列表
2. 通过 SSH 执行 `find` 命令扫描远程主机上的对话文件
3. 使用 `rsync -avz` 增量同步到本地归档目录

## 关键实现细节

### 解析 SSH config

```python
def load_ssh_hosts() -> list[str]:
    ssh_config = Path.home() / ".ssh" / "config"
    hosts = []
    for line in ssh_config.read_text().splitlines():
        line = line.strip()
        if line.lower().startswith("host ") and "*" not in line:
            for h in line.split()[1:]:
                if h and not h.startswith("#"):
                    hosts.append(h)
    return sorted(set(hosts))
```

### rsync 的 include/exclude 技巧

只同步 `.jsonl` 文件，但保留目录结构：

```bash
rsync -avz \
  --include='*/' \
  --include='*.jsonl' \
  --exclude='*' \
  --exclude='subagents/' \
  remote:~/.cursor/projects/ \
  local/archive/cursor/
```

`--include='*/'` 必须在前面，否则目录本身会被 `--exclude='*'` 排除。

## 踩坑与注意事项

- **SSH BatchMode** — 必须设置 `BatchMode=yes`，否则密码提示会导致 subprocess 挂起
- **ConnectTimeout** — 设置合理的超时（5s），避免不可达的主机阻塞整个流程
- **rsync 返回码** — 返回码 0 表示成功，23 表示部分传输错误（通常是权限问题），24 表示源文件消失（可忽略）
- **路径末尾的斜杠** — `rsync` 对尾部 `/` 敏感，`remote:path/` 同步目录内容，`remote:path` 同步目录本身
