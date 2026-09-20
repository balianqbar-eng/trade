#!/usr/bin/env python3
"""遺失物歸檔 — 把過了保留期的遺失物連照片匯出到本機，成功後才清空伺服器上的照片。

用法：
    python3 scripts/export_lost_items.py              看有哪些該歸檔（不動任何東西）
    python3 scripts/export_lost_items.py --run        真的匯出並清空 KV 照片
    python3 scripts/export_lost_items.py --days 60    臨時改用 60 天當保留期
    python3 scripts/export_lost_items.py --all        不看保留期，匯出全部還沒歸檔的

順序是硬規定：**先把照片下載到本機、驗證檔案存在且大小 > 0，才呼叫伺服器清空。**
反過來做一旦中斷就永久失去照片。

歸檔位置：~/Downloads/balian/遺失物歸檔/YYYY-MM/
  ├─ 索引.csv          這批的完整欄位
  └─ <日期>_<描述>.jpg  照片，檔名帶日期方便肉眼找
"""
import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://xiaoji-checkin.balianqbar.workers.dev"
ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "遺失物歸檔"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/120", "Content-Type": "application/json"}
TPE = timezone(timedelta(hours=8))


def api(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, method=method, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def safe_name(text, limit=28):
    cleaned = re.sub(r'[/\\:*?"<>|\n\r\t]', "", (text or "無描述")).strip()
    return (cleaned or "無描述")[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="真的執行（預設只預覽）")
    ap.add_argument("--days", type=int, help="覆寫保留天數")
    ap.add_argument("--all", action="store_true", help="不看保留期，匯出全部未歸檔的")
    args = ap.parse_args()

    settings = api("/settings")
    days = args.days if args.days is not None else int(settings.get("lost_item_retention_days", 30))
    cutoff = datetime.now(TPE) - timedelta(days=days)

    items = api("/lost-items")
    pending = []
    for it in items:
        if it.get("photo_purged_at"):
            continue  # 已歸檔過
        if not args.all:
            reported = datetime.strptime(it["reported_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if reported.astimezone(TPE) > cutoff:
                continue
        pending.append(it)

    print(f"保留天數 {days} 天｜伺服器上共 {len(items)} 筆遺失物｜該歸檔 {len(pending)} 筆")
    if not pending:
        print("沒有需要歸檔的項目。")
        return 0

    for it in pending:
        status = {"pending": "待認領", "claimed": "已認領", "discarded": "已丟棄"}.get(it["status"], it["status"])
        print(f"  {it['reported_at'][:10]}  {status:<6} {it.get('venue_name') or '未指定'}  {it['description'][:30]}"
              f"  {'有照片' if it.get('photo_url') else '無照片'}")

    if not args.run:
        print("\n這是預覽。確認無誤後加 --run 真的匯出並清空伺服器照片。")
        return 0

    # ---- 先下載，全部成功才清空 ----
    month = datetime.now(TPE).strftime("%Y-%m")
    outdir = ARCHIVE / month
    outdir.mkdir(parents=True, exist_ok=True)

    downloaded, failed = [], []
    for it in pending:
        url = it.get("photo_url")
        if not url:
            downloaded.append((it, None))
            continue
        fname = f"{it['reported_at'][:10]}_{safe_name(it['description'])}_{it['id'][:6]}.jpg"
        dest = outdir / fname
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
            if not dest.exists() or dest.stat().st_size == 0:
                raise RuntimeError("檔案是空的")
            downloaded.append((it, fname))
        except Exception as e:
            failed.append((it, str(e)))

    if failed:
        print(f"\n✗ {len(failed)} 張照片下載失敗，這批全部不清空（避免永久遺失）：")
        for it, err in failed:
            print(f"   {it['id'][:8]} {it['description'][:24]} — {err}")
        print("修好問題後再跑一次。")
        return 1

    # ---- 寫索引 ----
    index = outdir / "索引.csv"
    is_new = not index.exists()
    cols = ["id", "reported_at", "venue_name", "reporter_name", "description",
            "status", "resolved_at", "note", "photo_file"]
    with index.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if is_new:
            w.writeheader()
        for it, fname in downloaded:
            w.writerow({c: (fname if c == "photo_file" else (it.get(c) or "")) for c in cols})

    print(f"\n✓ 已匯出 {len(downloaded)} 筆到 {outdir}")
    print(f"  索引：{index}")

    # ---- 確認落地後才清伺服器 ----
    result = api("/lost-items/purge-photos", "POST", {"ids": [it["id"] for it, _ in downloaded]})
    print(f"✓ 伺服器已清空 {result['purged']} 張照片，{result['marked']} 筆標記為已歸檔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
