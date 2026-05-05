#!/bin/bash
cd /Users/balianwang/Downloads/balian
source .env 2>/dev/null || true

# 等 XQ bridge 就緒再啟動（最多等 30 秒）
for i in $(seq 1 6); do
  if curl -s http://100.107.36.65:8000/health > /dev/null 2>&1; then
    break
  fi
  sleep 5
done

python stock_server.py
