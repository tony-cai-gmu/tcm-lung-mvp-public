#!/bin/bash
# 自动加载 .env 并写入 ~/.bashrc，确保持久化生效

ENV_FILE="$(pwd)/.env"

if [ -f "$ENV_FILE" ]; then
  echo "🔑 从 $ENV_FILE 加载环境变量..."
  export $(grep -v '^#' $ENV_FILE | xargs)

  # 持久化到 ~/.bashrc
  grep -qxF "export \$(grep -v '^#' $ENV_FILE | xargs)" ~/.bashrc || \
  echo "export \$(grep -v '^#' $ENV_FILE | xargs)" >> ~/.bashrc
  echo "✅ 已写入 ~/.bashrc，下次启动自动生效。"
else
  echo "⚠️ 未找到 $ENV_FILE"
fi
