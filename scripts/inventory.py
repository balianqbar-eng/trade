#!/usr/bin/env python3
"""設備管理盤點 — 掃出實際在跑的服務、資料庫、憑證狀態，產生靜態 設備管理.html。

用法：
    python3 scripts/inventory.py            掃描並重新產生 設備管理.html
    python3 scripts/inventory.py --no-net   跳過需要連網的憑證檢查（快，但憑證欄位會標「未檢查」）

營運指揮艙用 file:// 開，抓不到本機 JSON，所以資料直接嵌進 HTML。
要更新就重跑這支腳本。
"""
import html
import json
import plistlib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
OUT = ROOT / "設備管理.html"

sys.path.insert(0, str(ROOT / "scripts"))
import token_check  # noqa: E402


def sh(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- launchd
def scan_services():
    running = {}
    for line in sh("launchctl list").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].startswith("com.balian."):
            running[parts[2]] = (parts[0], parts[1])

    services = []
    for f in sorted((HOME / "Library" / "LaunchAgents").glob("com.balian.*.plist")):
        label = f.stem
        name = label.replace("com.balian.", "")
        pid, exit_code = running.get(label, (None, None))

        program, schedule, plist_ok = "", "", True
        try:
            d = plistlib.load(f.open("rb"))
            args = d.get("ProgramArguments") or [d.get("Program", "")]
            program = " ".join(str(a) for a in args)
            if d.get("StartInterval"):
                schedule = f"每 {int(d['StartInterval']) // 60} 分"
            elif d.get("StartCalendarInterval"):
                schedule = "定時"
            elif d.get("KeepAlive"):
                schedule = "常駐"
        except Exception:
            plist_ok = False
            program = re.sub(r"\s+", " ", f.read_text(errors="replace"))
            m = re.search(r"<string>(cd [^<]+)</string>", program)
            program = m.group(1) if m else "(plist 解析失敗)"

        if pid and pid != "-":
            state, tone = "執行中", "ok"
        elif label in running:
            state, tone = f"已停止 (exit {exit_code})", "bad"
        else:
            state, tone = "未載入", "warn"

        services.append({
            "name": name, "state": state, "tone": tone, "pid": pid if pid and pid != "-" else "",
            "schedule": schedule, "program": program[:110],
            "plist_ok": plist_ok,
            "project": guess_project(program),
        })
    return services


def guess_project(program):
    for pat, proj in [
        (r"video2slides", "video2slides"),
        (r"市場監控家", "市場監控家"),
        (r"雙團隊分析戰情室|war.?room", "雙團隊戰情室"),
        (r"stock_server", "股票儀表板"),
        (r"telegram-bridge", "Telegram bridge"),
        (r"第二大腦|brain_server", "第二大腦"),
        (r"dmr|briefing", "DMR / 上工"),
        (r"http\.server 8123", "家庭財務 UI"),
        (r"it-course", "IT 課程提醒"),
        (r"colima", "Docker/Colima"),
        (r"ttyd", "遠端終端"),
    ]:
        if re.search(pat, program, re.I):
            return proj
    return "—"


# ------------------------------------------------------------------ 埠
def scan_ports():
    out, ports = [], {}
    for line in sh("lsof -nP -iTCP -sTCP:LISTEN").splitlines()[1:]:
        cols = line.split()
        if len(cols) < 9:
            continue
        port = cols[8].rsplit(":", 1)[-1]
        if port.isdigit() and 3000 <= int(port) <= 9999:
            ports.setdefault(port, cols[1])
    for port, proc in sorted(ports.items(), key=lambda x: int(x[0])):
        pid = sh(f"lsof -nP -iTCP:{port} -sTCP:LISTEN -t | head -1")
        cwd = sh(f"lsof -p {pid} -a -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-") if pid else ""
        cmd = sh(f"ps -p {pid} -o command=") if pid else ""
        out.append({"port": port, "proc": proc, "cmd": cmd[:90], "cwd": cwd[:80]})
    return out


# ------------------------------------------------------------- 資料庫
def scan_databases():
    dbs = []
    raw = sh("cd xiaoji-checkin && npx wrangler d1 list 2>/dev/null", timeout=90)
    for line in raw.splitlines():
        m = re.match(r"│\s*([0-9a-f-]{36})\s*│\s*([\w-]+)\s*│", line)
        if m:
            dbs.append({"kind": "Cloudflare D1", "name": m.group(2), "detail": f"uuid {m.group(1)[:8]}…",
                        "project": "小雞打工出勤系統"})
    env = token_check.read_env(HOME / ".config" / "family-finance" / "credentials.env")
    if env.get("SUPABASE_PROJECT_REF"):
        dbs.append({"kind": "Supabase Postgres", "name": env["SUPABASE_PROJECT_REF"],
                    "detail": "單一專案 + RLS 多租戶", "project": "家庭財務 UI"})
    for p, proj in [("工作記錄.csv", "DMR 工作紀錄"), ("projects.json", "Benjamin")]:
        f = ROOT / p
        if f.exists():
            n = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            dbs.append({"kind": "本機檔案", "name": p, "detail": f"{n} 列", "project": proj})
    return dbs


# ------------------------------------------------------------ 憑證
def scan_credentials(skip_net):
    rows = []
    for key, (label, fn) in token_check.CHECKS.items():
        if key == "dmrcsv":
            continue
        if skip_net:
            rows.append({"key": key, "label": label, "status": "SKIP", "detail": "--no-net 跳過"})
            continue
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = "FAIL", f"{type(e).__name__}: {e}"
        rows.append({"key": key, "label": label, "status": status, "detail": detail})
    return rows


# --------------------------------------------------------------- API
def scan_apis():
    apis = []
    wj = ROOT / "xiaoji-checkin" / "wrangler.jsonc"
    if wj.exists():
        name = re.search(r'"name"\s*:\s*"([^"]+)"', wj.read_text(encoding="utf-8"))
        if name:
            apis.append({"name": f"{name.group(1)} (Cloudflare Worker)",
                         "url": f"https://{name.group(1)}.balianqbar.workers.dev",
                         "project": "小雞打工出勤系統", "note": "LIFF 頁面 + 打卡/排班/換班 API"})
    env = token_check.read_env(HOME / ".config" / "line-checkin-system" / "credentials.env")
    if env.get("WORKER_URL"):
        apis.append({"name": "LINE Messaging API", "url": "https://api.line.me/v2/bot",
                     "project": "小雞打工出勤系統", "note": f"OA {env.get('LINE_OA_BASIC_ID', '')}"})
    fenv = token_check.read_env(HOME / ".config" / "family-finance" / "credentials.env")
    if fenv.get("SUPABASE_PROJECT_URL"):
        apis.append({"name": "Supabase REST", "url": fenv["SUPABASE_PROJECT_URL"],
                     "project": "家庭財務 UI", "note": "RLS 多租戶"})
    for port, name, proj in [("8000", "股票儀表板", "股票儀表板"), ("8001", "video2slides", "video2slides"),
                             ("8002", "雙團隊戰情室", "雙團隊戰情室"), ("8003", "市場監控家", "市場監控家"),
                             ("8123", "家庭財務 UI 靜態站", "家庭財務 UI")]:
        apis.append({"name": name, "url": f"http://localhost:{port}", "project": proj, "note": "本機服務"})
    return apis


# --------------------------------------------------------------- HTML
TONE = {"ok": ("#0f9d92", "#e3f6f2"), "warn": ("#b8730f", "#fdf4e3"),
        "bad": ("#b5503c", "#fdeeea"), "mute": ("#6a7183", "#eef1f0")}
STATUS_TONE = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "SKIP": "mute"}


def pill(text, tone):
    fg, bg = TONE[tone]
    return f'<span class="pill" style="color:{fg};background:{bg};">{html.escape(text)}</span>'


def build_html(data):
    e = html.escape
    svc_rows = "".join(
        f"<tr><td><b>{e(s['name'])}</b>{'' if s['plist_ok'] else ' ' + pill('plist XML 有誤', 'warn')}</td>"
        f"<td>{pill(s['state'], s['tone'])}</td><td class='num'>{e(s['pid'])}</td>"
        f"<td>{e(s['schedule'])}</td><td>{e(s['project'])}</td>"
        f"<td class='mono small'>{e(s['program'])}</td></tr>"
        for s in data["services"])
    cred_rows = "".join(
        f"<tr><td><b>{e(c['label'])}</b></td><td>{pill(c['status'], STATUS_TONE.get(c['status'], 'mute'))}</td>"
        f"<td>{e(c['detail'])}</td></tr>" for c in data["credentials"])
    db_rows = "".join(
        f"<tr><td><b>{e(d['name'])}</b></td><td>{e(d['kind'])}</td><td>{e(d['detail'])}</td>"
        f"<td>{e(d['project'])}</td></tr>" for d in data["databases"])
    port_rows = "".join(
        f"<tr><td class='num'>{e(p['port'])}</td><td>{e(p['proc'])}</td>"
        f"<td class='mono small'>{e(p['cmd'])}</td><td class='mono small'>{e(p['cwd'])}</td></tr>"
        for p in data["ports"])
    api_rows = "".join(
        f"<tr><td><b>{e(a['name'])}</b></td>"
        f"<td class='mono small'><a href='{e(a['url'])}' target='_blank' rel='noopener'>{e(a['url'])}</a></td>"
        f"<td>{e(a['project'])}</td><td>{e(a['note'])}</td></tr>" for a in data["apis"])

    bad = sum(1 for c in data["credentials"] if c["status"] == "FAIL")
    down = sum(1 for s in data["services"] if s["tone"] == "bad")

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<title>設備管理</title>
<style>
  :root {{ color-scheme: light; --bg:#eef7f4; --panel:#fff; --panel-2:#f4faf8; --ink:#1c3a36;
           --ink-soft:#5a7d78; --border:#dcece7; --accent:#0f9d92; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,"PingFang TC",sans-serif; background:var(--bg);
          color:var(--ink); padding:24px; font-size:14px; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  .sub {{ font-size:12.5px; color:var(--ink-soft); margin-bottom:18px; }}
  .summary {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:22px; }}
  .card {{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
           padding:10px 16px; min-width:130px; }}
  .card .k {{ font-size:11.5px; color:var(--ink-soft); }}
  .card .v {{ font-size:22px; font-weight:700; font-variant-numeric:tabular-nums; }}
  h2 {{ font-size:14.5px; margin:26px 0 8px; padding-bottom:6px; border-bottom:1px solid var(--border); }}
  .scroll {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); border-radius:10px;
           overflow:hidden; font-size:13px; min-width:640px; }}
  th {{ background:var(--panel-2); color:var(--ink-soft); font-size:11.5px; font-weight:600;
        text-align:left; padding:9px 12px; white-space:nowrap; }}
  td {{ padding:9px 12px; border-top:1px solid var(--border); vertical-align:top; }}
  .mono {{ font-family:ui-monospace,Menlo,monospace; }}
  .small {{ font-size:11.5px; color:var(--ink-soft); word-break:break-all; }}
  .num {{ font-variant-numeric:tabular-nums; }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11.5px;
           font-weight:600; white-space:nowrap; }}
  a {{ color:var(--accent); }}
  .head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px;
           flex-wrap:wrap; margin-bottom:18px; }}
  .refresh {{ display:flex; align-items:center; gap:10px; }}
  .stamp {{ font-size:12px; color:var(--ink-soft); font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .stamp.stale {{ color:#b8730f; font-weight:600; }}
  #refreshBtn {{ background:var(--accent); color:#fff; border:none; border-radius:8px;
                 padding:7px 16px; font-size:13px; font-weight:600; cursor:pointer;
                 font-family:inherit; }}
  #refreshBtn:hover {{ opacity:.88; }}
  .toast {{ position:fixed; left:50%; bottom:22px; transform:translateX(-50%); background:var(--ink);
            color:#fff; padding:9px 18px; border-radius:999px; font-size:13px; opacity:0;
            transition:opacity .25s; pointer-events:none; z-index:50; max-width:90vw; }}
  .toast.show {{ opacity:1; }}
  footer {{ margin-top:28px; font-size:11.5px; color:var(--ink-soft); }}
</style>
</head>
<body>
  <div class="head">
    <div>
      <h1>設備管理</h1>
      <div class="sub">實際掃描結果，不是手寫清單</div>
    </div>
    <div class="refresh">
      <span class="stamp" id="stamp" data-scanned="{data['scanned_at']}"></span>
      <button id="refreshBtn" title="複製重掃指令；或直接跟 Claude 說「更新設備管理」">更新</button>
    </div>
  </div>
  <div class="toast" id="toast"></div>

  <div class="summary">
    <div class="card"><div class="k">背景服務</div><div class="v">{len(data['services'])}</div></div>
    <div class="card"><div class="k">未在執行</div><div class="v" style="color:{'#b5503c' if down else '#0f9d92'}">{down}</div></div>
    <div class="card"><div class="k">憑證異常</div><div class="v" style="color:{'#b5503c' if bad else '#0f9d92'}">{bad}</div></div>
    <div class="card"><div class="k">資料庫</div><div class="v">{len(data['databases'])}</div></div>
    <div class="card"><div class="k">對外接口</div><div class="v">{len(data['apis'])}</div></div>
  </div>

  <h2>授權認證</h2>
  <div class="scroll"><table>
    <thead><tr><th>服務</th><th>狀態</th><th>說明</th></tr></thead><tbody>{cred_rows}</tbody></table></div>

  <h2>背景服務（launchd）</h2>
  <div class="scroll"><table>
    <thead><tr><th>服務</th><th>狀態</th><th>PID</th><th>排程</th><th>所屬專案</th><th>執行內容</th></tr></thead>
    <tbody>{svc_rows}</tbody></table></div>

  <h2>資料庫</h2>
  <div class="scroll"><table>
    <thead><tr><th>名稱</th><th>類型</th><th>說明</th><th>所屬專案</th></tr></thead><tbody>{db_rows}</tbody></table></div>

  <h2>API / 連結</h2>
  <div class="scroll"><table>
    <thead><tr><th>名稱</th><th>位址</th><th>所屬專案</th><th>用途</th></tr></thead><tbody>{api_rows}</tbody></table></div>

  <h2>本機在聽的埠</h2>
  <div class="scroll"><table>
    <thead><tr><th>埠</th><th>行程</th><th>指令</th><th>工作目錄</th></tr></thead><tbody>{port_rows}</tbody></table></div>

  <footer>掃描時間：{data['scanned_at']}　·　資料由 <span class="mono">scripts/inventory.py</span> 實際掃描產生</footer>

<script>
const CMD = 'python3 scripts/inventory.py';
const stampEl = document.getElementById('stamp');
const scanned = new Date(stampEl.dataset.scanned.replace(' ', 'T'));
const hours = (Date.now() - scanned.getTime()) / 3600000;

function ago() {{
  if (hours < 1) return Math.max(1, Math.round(hours * 60)) + ' 分鐘前';
  if (hours < 24) return Math.round(hours) + ' 小時前';
  return Math.round(hours / 24) + ' 天前';
}}
stampEl.textContent = '最後更新：' + stampEl.dataset.scanned + '（' + ago() + '）';
if (hours >= 24) {{
  stampEl.classList.add('stale');
  stampEl.textContent += ' · 資料可能已過期';
}}

const toastEl = document.getElementById('toast');
let toastTimer;
function toast(msg) {{
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 4000);
}}

document.getElementById('refreshBtn').onclick = async () => {{
  // 靜態頁沒辦法自己執行本機腳本,所以複製指令讓使用者貼到終端機
  try {{
    await navigator.clipboard.writeText(CMD);
    toast('已複製「' + CMD + '」，貼到終端機執行後重新整理本頁');
  }} catch (e) {{
    toast('請在終端機執行：' + CMD);
  }}
}};
</script>
</body>
</html>
"""


def main():
    skip_net = "--no-net" in sys.argv
    print("掃描中…")
    data = {
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "services": scan_services(),
        "ports": scan_ports(),
        "databases": scan_databases(),
        "credentials": scan_credentials(skip_net),
        "apis": scan_apis(),
    }
    OUT.write_text(build_html(data), encoding="utf-8")
    bad = [c["label"] for c in data["credentials"] if c["status"] == "FAIL"]
    down = [s["name"] for s in data["services"] if s["tone"] == "bad"]
    print(f"已產生 {OUT}")
    print(f"  服務 {len(data['services'])}｜資料庫 {len(data['databases'])}｜接口 {len(data['apis'])}｜埠 {len(data['ports'])}")
    if down:
        print(f"  ⚠ 未在執行：{'、'.join(down)}")
    if bad:
        print(f"  ✗ 憑證異常：{'、'.join(bad)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
