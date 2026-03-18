---
title: Electron 视频导出方案：ffmpeg-static vs @ffmpeg/ffmpeg WASM
type: research
category: Frontend
tags: [Electron, ffmpeg, WASM, 视频处理]
source_tool: codebuddy-ide
source_id: example-research-001
created: 2026-03-12
---

Electron 桌面端做模板化视频处理（单视频 + 边框/水印/模糊背景），导出环节需要用 ffmpeg。两条路线：原生二进制（ffmpeg-static）和 WASM（@ffmpeg/ffmpeg），核心取舍是**性能 vs 分发便利性**。

## 两条路线

### ffmpeg-static（原生）

主进程通过 `child_process` 调用打包好的 ffmpeg 二进制。性能最好，支持硬件编码（NVENC/VideoToolbox），长视频和 4K 无压力。缺点是每个平台需要打包对应的二进制，应用体积增加 ~70MB。

### @ffmpeg/ffmpeg（WASM）

在渲染进程或 Worker 中运行 ffmpeg 的 WASM 编译版本。跨平台零配置，不需要额外打包二进制。但没有硬件编码，长视频处理明显慢，大文件受 MEMFS 内存限制（浏览器环境通常 2-4GB 上限）。

## 怎么选

模板化工具处理的通常是短视频（< 5 分钟），分辨率不超过 1080p → **WASM 够用**，分发简单。

如果需要处理长视频、4K、或者对导出速度有要求 → 必须用 **原生 ffmpeg-static**。

折中方案：默认用 WASM，检测到本机有 ffmpeg 时自动切换到原生路径。

## 补充：预览不需要 ffmpeg

预览阶段用 `<video>` 标签播放 + Konva/DOM 叠层做边框和水印，解码和音视频同步交给浏览器，不需要 ffmpeg 参与。只有最终导出时才需要 ffmpeg 合成滤镜。
