#!/usr/bin/env bash
# RAG V1 健康检查脚本 (M0 P1-7 修复版：5 service 状态一行一查)
set -euo pipefail

COMPOSE="docker compose -f $(dirname "$0")/docker-compose.yml"

services=("postgres" "opensearch" "tei" "langfuse" "minio")
printf "%-15s %-12s\n" "SERVICE" "STATUS"
printf "%-15s %-12s\n" "-------" "------"

fail=0
for svc in "${services[@]}"; do
  cid=$($COMPOSE ps -q "$svc" 2>/dev/null)
  if [ -z "$cid" ]; then
    printf "%-15s %-12s\n" "$svc" "NOT_RUNNING"
    fail=1
    continue
  fi
  status=$(docker inspect --format='{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "no-healthcheck")
  printf "%-15s %-12s\n" "$svc" "$status"
  if [ "$status" != "healthy" ]; then
    fail=1
  fi
done

if [ $fail -eq 0 ]; then
  echo ""
  echo "✅ ALL SERVICES HEALTHY"
  exit 0
else
  echo ""
  echo "❌ SOME SERVICES UNHEALTHY"
  exit 1
fi
