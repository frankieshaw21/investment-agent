#!/bin/sh

cd "$(dirname "$0")" || exit 1

python=.venv/bin/python
if [ ! -x "$python" ]; then
    printf '%s\n' '请先在项目目录按 README 的 macOS 安装步骤创建 .venv。' >&2
    exit 1
fi

exec "$python" desktop.py
