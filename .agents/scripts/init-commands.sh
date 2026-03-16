#!/bin/bash

# 兼容入口 — 请使用 init.sh commands
exec "$(dirname "${BASH_SOURCE[0]}")/init.sh" commands "$@"
