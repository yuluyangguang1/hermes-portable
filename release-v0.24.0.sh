#!/usr/bin/env bash
# Hermes Portable v0.24.0 发版脚本
# 前提：当前 gh 登录的 token 需带 workflow scope（否则 push 含 workflow 文件的提交会被拒）
# 用法：bash release-v0.24.0.sh
set -e
cd "$(dirname "$0")"

echo "=== 1. 推送 main ==="
git push origin main

echo "=== 2. 打 tag v0.24.0 并推送（触发三平台构建 + GitHub Release）==="
git tag -f v0.24.0
git push -f origin v0.24.0

echo ""
echo "✓ 已触发远程构建。查看进度："
echo "  https://github.com/yuluyangguang1/hermes-portable/actions"
echo "  Release 产物：https://github.com/yuluyangguang1/hermes-portable/releases/tag/v0.24.0"
