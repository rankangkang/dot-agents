# AI Assets

本目录存放所有 AI 相关资产，统一管理 Agent 的技能、规则、脚本等配置。

## 目录结构

```
.agents/
├── skills/      # Agent 技能定义（SKILL.md）
├── rules/       # Agent 行为规则（RULE.md / AGENTS.md）
├── scripts/     # Agent 配置与自动化脚本
├── commands/    # 自定义 Agent 命令
├── prompts/     # 可复用的 Prompt 模板
└── templates/   # 项目/文件模板
```

## 各目录说明

### skills/
存放 Agent 技能文件。每个技能为一个独立目录，包含 `SKILL.md` 作为技能入口文件，定义技能的触发条件、执行步骤和所需工具。

### rules/
存放 Agent 行为规则。规则用于约束 Agent 的行为模式、编码风格、响应格式等，可以是全局规则或针对特定文件类型的规则。

### scripts/
存放 Agent 相关的自动化脚本。核心脚本 `init.sh` 负责将资产通过符号链接分发到各 AI 工具目录，支持项目内链接（默认）、全局链接（`--global`）和指定目录链接（`--target`）。

### commands/
存放自定义 Agent 命令，供用户在对话中快速调用特定工作流。

### prompts/
存放可复用的 Prompt 片段和模板，用于标准化常见任务的提示词。

### templates/
存放项目和文件模板，用于快速生成标准化的项目结构或文件。
