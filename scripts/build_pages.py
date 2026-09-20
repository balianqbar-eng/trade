#!/usr/bin/env python3
"""把營運指揮艙及其嵌入的頁面打包成可部署到 Cloudflare Pages 的靜態站。

中文檔名在 URL 上會被 percent-encode，部署端容易出錯，所以一律改成英文檔名，
並把指揮艙裡的絕對路徑 file:/// 引用換成相對路徑。

用法：python3 scripts/build_pages.py  然後 npx wrangler pages deploy _pages_deploy
"""
import os, re, shutil

BALIAN = "/Users/balianwang/Downloads/balian"
DL = "/Users/balianwang/Downloads"
OUT = os.path.join(BALIAN, "_pages_deploy")

# 來源路徑 → 部署後檔名
FILES = {
    f"{BALIAN}/營運指揮艙.html": "index.html",
    f"{BALIAN}/營運看板.html": "kanban.html",
    f"{BALIAN}/daily-reflection.html": "daily-reflection.html",
    f"{BALIAN}/記帳整合UI_原型.html": "finance.html",
    f"{BALIAN}/CFP_貨幣時間價值計算機_v01.html": "tvm.html",
    f"{BALIAN}/設備管理.html": "inventory.html",
    f"{BALIAN}/xiaoji-checkin/人員個人資料.html": "people.html",
    f"{BALIAN}/xiaoji-checkin/小雞打卡出勤紀錄.html": "checkin.html",
    f"{BALIAN}/dmr/清帳看板.html": "dmr-board.html",
    f"{DL}/零霉大師_專案/00_企劃/零霉大師_企劃_事業路線圖_v02.html": "molds-roadmap.html",
    f"{DL}/零霉大師_專案/00_企劃/一九姨管婆_企劃_商業模式九宮格_v01.html": "molds-bmc.html",
    f"{DL}/零霉大師_專案/00_企劃/一九姨管婆_分析_競品四家與突破口_v01.html": "molds-rivals.html",
    f"{DL}/零霉大師_專案/00_企劃/一九姨管婆_試算_家戶LTV_v01.html": "molds-ltv.html",
    f"{DL}/零霉大師_專案/00_企劃/一九姨管婆_作業_QR管理與現場SOP_v01.html": "molds-sop.html",
    f"{DL}/零霉大師_專案/20_對外/一九姨管婆_對外_服務範圍聲明_v01.html": "molds-scope.html",
    f"{DL}/單店財務模型.html": "molds-finance.html",
    f"{DL}/競爭定位圖.html": "molds-competition.html",
    f"{DL}/師傅DB/產品階梯_清潔到代管.html": "molds-ladder.html",
    f"{DL}/師傅DB/設備清潔MVP_師傅端與後台端.html": "molds-mvp.html",
    f"{DL}/師傅DB/資料價值路線圖.html": "molds-data.html",
}

# 指揮艙 HTML 裡要替換的引用字串（原字串 → 新檔名）
REWRITE = {
    "/Users/balianwang/Downloads/零霉大師_專案/00_企劃/零霉大師_企劃_事業路線圖_v02.html": "molds-roadmap.html",
    "/Users/balianwang/Downloads/零霉大師_專案/00_企劃/一九姨管婆_企劃_商業模式九宮格_v01.html": "molds-bmc.html",
    "/Users/balianwang/Downloads/零霉大師_專案/00_企劃/一九姨管婆_分析_競品四家與突破口_v01.html": "molds-rivals.html",
    "/Users/balianwang/Downloads/零霉大師_專案/00_企劃/一九姨管婆_試算_家戶LTV_v01.html": "molds-ltv.html",
    "/Users/balianwang/Downloads/零霉大師_專案/00_企劃/一九姨管婆_作業_QR管理與現場SOP_v01.html": "molds-sop.html",
    "/Users/balianwang/Downloads/零霉大師_專案/20_對外/一九姨管婆_對外_服務範圍聲明_v01.html": "molds-scope.html",
    "/Users/balianwang/Downloads/單店財務模型.html": "molds-finance.html",
    "/Users/balianwang/Downloads/競爭定位圖.html": "molds-competition.html",
    "/Users/balianwang/Downloads/師傅DB/產品階梯_清潔到代管.html": "molds-ladder.html",
    "/Users/balianwang/Downloads/師傅DB/設備清潔MVP_師傅端與後台端.html": "molds-mvp.html",
    "/Users/balianwang/Downloads/師傅DB/資料價值路線圖.html": "molds-data.html",
    "營運看板.html": "kanban.html",
    "記帳整合UI_原型.html": "finance.html",
    "CFP_貨幣時間價值計算機_v01.html": "tvm.html",
    "設備管理.html": "inventory.html",
    "人員個人資料.html": "people.html",
    "小雞打卡出勤紀錄.html": "checkin.html",
    "dmr/清帳看板.html": "dmr-board.html",
}

def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    missing = []
    for src, name in FILES.items():
        if not os.path.isfile(src):
            missing.append(src)
            continue
        with open(src, encoding="utf-8") as f:
            html = f.read()
        if name == "index.html":
            for old, new in REWRITE.items():
                html = html.replace(old, new)
            html = html.replace("</head>", BANNER + "</head>") if "</head>" in html else BANNER + html
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  {name:28s} ← {os.path.basename(src)}")

    if missing:
        print("\n缺檔（分頁會 404）：")
        for m in missing:
            print("  " + m)

    # 部署設定與密碼保護：rmtree 會清掉，所以每次一併重建
    with open(os.path.join(OUT, "_worker.js"), "w", encoding="utf-8") as f:
        f.write(WORKER_JS)
    with open(os.path.join(OUT, "wrangler.jsonc"), "w", encoding="utf-8") as f:
        f.write(WRANGLER)
    with open(os.path.join(OUT, ".assetsignore"), "w", encoding="utf-8") as f:
        f.write("wrangler.jsonc\n.assetsignore\n_worker.js\n")

    left = []
    with open(os.path.join(OUT, "index.html"), encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if "/Users/balianwang" in line:
                left.append(n)
    print(f"\n共 {len(FILES) - len(missing)} 檔 → {OUT}")
    if left:
        print(f"⚠ index.html 仍有 {len(left)} 行含本機絕對路徑，行號：{left[:10]}")
    else:
        print("✓ index.html 已無本機絕對路徑")

# 雲端版標記：提醒資料不同步
BANNER = """<style>
#cloudNote{position:fixed;bottom:10px;right:10px;z-index:9999;background:#1a332b;color:#8fb0a7;
border:1px solid #223d35;border-radius:8px;padding:7px 12px;font-size:11.5px;
font-family:-apple-system,"PingFang TC",system-ui,sans-serif;max-width:260px;line-height:1.5}
#cloudNote b{color:#3cc4b4}
#cloudNote button{background:none;border:none;color:#5a7b72;cursor:pointer;font-size:13px;float:right;padding:0 0 0 8px}
</style>
<script>
window.addEventListener("DOMContentLoaded",function(){
  var d=document.createElement("div");d.id="cloudNote";
  d.innerHTML='<button onclick="this.parentNode.remove()">✕</button><b>雲端版</b> · 看板卡片存在各裝置本機，與電腦上的不同步';
  document.body.appendChild(d);
});
</script>
"""

WORKER_JS = """export default {
  async fetch(request, env) {
    const expected = "Basic " + btoa("balian:" + env.SITE_PASSWORD);
    if ((request.headers.get("Authorization") || "") !== expected) {
      return new Response("需要登入", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="營運指揮艙", charset="UTF-8"' },
      });
    }
    return env.ASSETS.fetch(request);
  },
};
"""

WRANGLER = """{
  "name": "balian-cockpit",
  "compatibility_date": "2026-09-11",
  "main": "_worker.js",
  "observability": { "enabled": true },
  "assets": { "directory": ".", "binding": "ASSETS" }
}
"""

if __name__ == "__main__":
    main()
