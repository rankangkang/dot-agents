---
title: Vite 启动报 PostCSS 配置加载失败——依赖的 PostCSS 插件未安装
type: debug
category: Frontend
tags: [Vite, PostCSS, 工程化]
source_tool: codebuddy
source_id: example-debug-001
created: 2026-03-10
---

Vite 项目启动时报 `Error: Loading PostCSS Plugin failed`，项目里明明有 `postcss.config.js` 且之前一直正常。问题出在新拉的分支缺少了 PostCSS 插件的依赖。

## 问题

报错信息指向 PostCSS 配置文件，但实际上配置本身没问题——是配置中引用的某个插件（如 `postcss-pxtorem`）没装。Vite 的报错信息会让人以为是配置语法问题，容易往错误方向排查。

## 为什么容易误判

Vite 的错误信息是 `Loading PostCSS Plugin failed: ... Cannot find module 'postcss-pxtorem'`，但如果终端窗口不够宽或者被截断，只看到前半句 `Loading PostCSS Plugin failed`，很容易以为是 postcss.config.js 写错了。

## 解决

```bash
npm install  # 重新安装依赖即可
```

切分支后如果 `package.json` 有变动，先跑一遍 `npm install`。如果是 monorepo，注意是否需要在子包目录下单独安装。

## 延伸

Vite 的 PostCSS 集成不需要单独安装 `postcss` 本身（Vite 内置了），但 postcss.config.js 中引用的**插件**需要作为项目依赖安装。这一点和 Webpack + postcss-loader 的行为一致。
