---
title: init.sh 中通过符号链接分发 rules 文件到各 AI 工具目录
type: implementation
category: Tools
tags: [dot-agents, shell, 符号链接, 工程化]
source_tool: cursor
source_id: example-impl-001
created: 2026-03-14
---

dot-agents 的 `init.sh` 需要把 `.agents/rules/` 下的规则文件通过符号链接分发到各 AI 工具的配置目录（`.cursor/rules/`、`.claude/` 等）。难点在于 rules 目录可能有嵌套子文件夹，链接需要保留目录结构。

## 实现思路

遍历 `.agents/rules/` 下所有 `.md` 文件（包括子目录中的），在目标目录中创建对应的目录结构，然后建符号链接。关键是用 `find` + 相对路径计算：

```bash
find "$rules_dir" -name "*.md" -type f | while read -r rule_file; do
  rel_path="${rule_file#$rules_dir/}"           # 相对路径，如 "frontend/react.md"
  target_dir="$cursor_rules_dir/$(dirname "$rel_path")"
  mkdir -p "$target_dir"
  ln -sf "$rule_file" "$target_dir/$(basename "$rel_path")"
done
```

## 注意事项

**符号链接用绝对路径**。如果用相对路径，当工具从不同的工作目录读取链接时会找不到源文件。`ln -sf` 的源路径应该是 `$rule_file` 的绝对路径（`find` 传入绝对路径的 `$rules_dir` 即可保证）。

**幂等性**。`ln -sf` 的 `-f` 会覆盖已存在的链接，所以重复执行 `init.sh` 不会报错。但如果用户手动在目标目录放了同名的普通文件（不是链接），`-f` 也会覆盖掉，需要在文档中说明。

**跨工具差异**。`.cursor/rules/` 目录支持嵌套结构，但 `.claude/` 只读根目录下的 `CLAUDE.md`，不支持子目录——对 Claude 只需要链接单个文件，不需要递归。
