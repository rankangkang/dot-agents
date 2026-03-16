#!/bin/bash

# 兼容入口 — 请使用 init.sh skills
exec "$(dirname "${BASH_SOURCE[0]}")/init.sh" skills "$@"
