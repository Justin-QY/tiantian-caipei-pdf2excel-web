#!/usr/bin/env bash
# 生成 .env 和一串随机访问口令（用于 Docker 部署）
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo ".env 已存在，保持原样。当前口令：$(grep '^ACCESS_CODE=' .env | cut -d= -f2-)"
  exit 0
fi

CODE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
printf 'ACCESS_CODE=%s\n' "$CODE" > .env
chmod 600 .env

printf '\n已生成 .env\n访问口令：%s\n请保存好。忘记口令可查看 .env，或删除 .env 后重新运行本脚本。\n' "$CODE"
