#!/bin/bash
# 小雞打工 D1 資料庫備份。含員工個資，只存本機，不進 repo。
# 用法：bash scripts/xiaoji_backup.sh
set -e
DIR=~/Downloads/xiaoji-db-backup
mkdir -p "$DIR"
OUT="$DIR/xiaoji-$(date +%Y%m%d_%H%M).sql"
cd "$(dirname "$0")/../xiaoji-checkin"
NODE_OPTIONS= npx wrangler d1 export xiaoji-checkin-db --remote --output "$OUT"
echo "✓ $OUT  ($(du -h "$OUT" | cut -f1))"
# 只留最近 10 份，避免塞爆磁碟
ls -t "$DIR"/xiaoji-*.sql 2>/dev/null | tail -n +11 | xargs -r rm -f
echo "  現有備份 $(ls "$DIR"/xiaoji-*.sql 2>/dev/null | wc -l | tr -d ' ') 份"
