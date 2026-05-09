"""錢哨分析報告產生器：將 analysis_history 紀錄轉為獨立 HTML 報告。"""

import html
import os
from datetime import datetime


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _trend_class(trend: str) -> str:
    if trend in ("bull", "多頭"): return "bull"
    if trend in ("bear", "空頭"): return "bear"
    return "neutral"


_LEVEL_LABEL = {"safe": "安全", "watch": "觀望", "danger": "危險"}
_PATTERN_LABEL = {"formed": "已形成", "forming": "形成中", "none": "未形成", "insufficient": "資料不足"}


def _level_class(level: str) -> str:
    if level in ("safe", "安全"):  return "safe"
    if level in ("danger", "危險"): return "danger"
    return "warn"


def _level_label(level: str) -> str:
    return _LEVEL_LABEL.get(level, level or "—")


def _pattern_label(v: str) -> str:
    return _PATTERN_LABEL.get(v, v or "—")


_TREND_LABEL = {"bull": "多頭", "bear": "空頭", "neutral": "中性"}


def _trend_label(t: str) -> str:
    return _TREND_LABEL.get(t, t or "—")


def _chip_row_html(c: dict) -> str:
    def cell(v: int) -> str:
        if v > 0:
            return f'<td class="td-num pos">+{v}</td>'
        if v < 0:
            return f'<td class="td-num neg">{v}</td>'
        return f'<td class="td-num">{v}</td>'
    trust = c.get("trust", c.get("investment_trust", 0))
    return (
        f'<tr><td class="td-date">{_esc(c.get("date"))}</td>'
        + cell(int(c.get("foreign", 0)))
        + cell(int(trust))
        + cell(int(c.get("dealer", 0)))
        + cell(int(c.get("total", 0)))
        + "</tr>"
    )


def _indicator_row_html(row: dict) -> str:
    trend = row.get("trend", "")
    cls = _trend_class(trend)
    desc = row.get("desc", row.get("description", ""))
    return (
        f'<tr><td>{_esc(row.get("name"))}</td>'
        f'<td class="td-center"><span class="badge badge-{cls}">{_esc(_trend_label(trend))}</span></td>'
        f'<td class="td-desc">{_esc(desc)}</td></tr>'
    )


def _ksig_html(sig) -> str:
    """支援 V1 字串陣列與舊物件陣列"""
    if isinstance(sig, dict):
        name = sig.get("name", "")
        cls = _trend_class("bull" if sig.get("type") == "bull"
                           else "bear" if sig.get("type") == "bear" else "neutral")
    else:
        name = str(sig)
        # 字串型態根據關鍵字推測 bull/bear
        bear_kw = ("烏鴉", "夜星", "M頭", "M 頭")
        bull_kw = ("紅三兵", "晨星", "長下影")
        if any(k in name for k in bear_kw):
            cls = "bear"
        elif any(k in name for k in bull_kw):
            cls = "bull"
        else:
            cls = "neutral"
    return f'<span class="badge badge-{cls}">{_esc(name)}</span>'


def render(record: dict) -> str:
    r = record.get("result", {})
    summary = r.get("technical_summary", {})
    chips   = r.get("chips_analysis", []) or []
    chips_concl = r.get("chips_conclusion", "")
    key_prices  = r.get("key_prices", {})
    main_force  = r.get("main_force_signal", {})
    pattern     = r.get("pattern_analysis", {})
    indicators_table = r.get("indicators_table", []) or []
    win_rate    = r.get("win_rate", 0)
    suggestion  = r.get("suggestion", {})
    conclusion  = r.get("conclusion", "")

    chips_table = "\n".join(_chip_row_html(c) for c in chips)
    indicators_html = "\n".join(_indicator_row_html(row) for row in indicators_table)
    k_signals_html = "".join(_ksig_html(s) for s in (pattern.get("k_signals") or []))

    ring_offset = 264 - (264 * win_rate / 100)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>策略分析報告 — {_esc(record.get("ticker"))} {_esc(record.get("stock_name"))}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ background: #0f172a; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; padding: 24px; margin: 0; }}
.wrap {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #60a5fa; margin: 0 0 8px; font-size: 24px; }}
.meta {{ color: #94a3b8; font-size: 13px; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; }}
.card-title {{ color: #60a5fa; font-size: 13px; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid #334155; margin-bottom: 10px; }}
.col-4 {{ grid-column: span 4; }} .col-6 {{ grid-column: span 6; }} .col-12 {{ grid-column: span 12; }}
.kv {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }}
.kv .label {{ color: #64748b; }} .kv .value {{ color: #e2e8f0; font-weight: 500; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ color: #64748b; font-weight: normal; text-align: left; padding: 4px 6px; font-size: 11px; }}
td {{ padding: 5px 6px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
.td-num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.td-center {{ text-align: center; }} .td-date {{ color: #94a3b8; }} .td-desc {{ color: #94a3b8; font-size: 12px; }}
.pos {{ color: #ef4444; }} .neg {{ color: #22c55e; }}
.badge {{ display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 500; }}
.badge-bull {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
.badge-bear {{ background: rgba(34,197,94,0.15); color: #22c55e; }}
.badge-neutral {{ background: rgba(148,163,184,0.15); color: #94a3b8; }}
.badge-safe {{ background: rgba(34,197,94,0.15); color: #22c55e; }}
.badge-warn {{ background: rgba(251,191,36,0.15); color: #fbbf24; }}
.badge-danger {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
.win-wrap {{ display: flex; align-items: center; gap: 16px; }}
.gauge {{ position: relative; width: 90px; height: 90px; flex-shrink: 0; }}
.gauge svg {{ transform: rotate(-90deg); width: 100%; height: 100%; }}
.gauge .val {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: bold; color: #3b82f6; }}
.suggest .row {{ display: flex; gap: 8px; padding: 4px 0; font-size: 13px; }}
.suggest .row .lbl {{ width: 60px; color: #64748b; flex-shrink: 0; }}
.suggest .yel {{ color: #fbbf24; }} .suggest .red {{ color: #ef4444; }} .suggest .grn {{ color: #22c55e; }}
.k-signals {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }}
.conclusion {{ color: #fbbf24; font-weight: 600; margin-right: 8px; }}
@media print {{
  body {{ background: #fff; color: #1e293b; }}
  .card {{ background: #f8fafc; border-color: #e2e8f0; }}
  .card-title {{ color: #2563eb; border-color: #e2e8f0; }}
  .kv .label {{ color: #64748b; }} .kv .value {{ color: #1e293b; }}
  th {{ color: #64748b; }} td {{ border-color: #e2e8f0; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <h1>策略分析報告 — {_esc(record.get("ticker"))} {_esc(record.get("stock_name"))}</h1>
  <div class="meta">
    策略：{_esc(record.get("strategy_name"))} ｜
    分析時間：{_esc(record.get("analyzed_at"))} ｜
    產出時間：{_esc(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}
  </div>

  <div class="grid">
    <!-- 技術分析總覽 -->
    <div class="card col-4">
      <div class="card-title">技術分析總覽</div>
      <div class="kv"><span class="label">趨勢方向</span><span class="value"><span class="badge badge-{_trend_class(summary.get("trend"))}">{_esc(summary.get("trend"))}</span> {_esc(summary.get("trend_desc"))}</span></div>
      <div class="kv"><span class="label">價格位置</span><span class="value">{_esc(summary.get("price_position"))}</span></div>
      <div class="kv"><span class="label">均線排列</span><span class="value">{_esc(summary.get("ma_alignment"))}</span></div>
      <div class="kv"><span class="label">量價關係</span><span class="value">{_esc(summary.get("volume_price"))}</span></div>
      <div class="kv"><span class="label">布林位置</span><span class="value">{_esc(summary.get("bollinger_position"))}</span></div>
      <div class="kv"><span class="label">布林通道</span><span class="value">{_esc(summary.get("bollinger_state"))}</span></div>
      <div class="kv" style="border-top:1px solid #334155;padding-top:6px;margin-top:6px;"><span class="label">綜合評估</span><span class="value" style="color:#fbbf24;">{_esc(summary.get("overall"))}</span></div>
    </div>

    <!-- 籌碼分析 -->
    <div class="card col-4">
      <div class="card-title">籌碼分析（三大法人，單位：張）</div>
      <table>
        <thead>
          <tr><th>日期</th><th class="td-num">外資</th><th class="td-num">投信</th><th class="td-num">自營商</th><th class="td-num">合計</th></tr>
        </thead>
        <tbody>
          {chips_table or '<tr><td colspan="5" style="color:#64748b;text-align:center;padding:8px;">無籌碼資料</td></tr>'}
        </tbody>
      </table>
      <div style="border-top:1px solid #334155;padding-top:8px;margin-top:8px;color:#fbbf24;font-size:13px;font-weight:500;">結論：{_esc(chips_concl)}</div>
    </div>

    <!-- 關鍵價位 + 主力燈號 -->
    <div class="col-4" style="display:flex;flex-direction:column;gap:12px;">
      <div class="card">
        <div class="card-title">關鍵價位</div>
        <div class="kv"><span class="label">壓力區</span><span class="value" style="color:#ef4444;">{_esc(key_prices.get("pressure"))}</span></div>
        <div class="kv"><span class="label">回檔區</span><span class="value" style="color:#fbbf24;">{_esc(key_prices.get("pullback"))}</span></div>
        <div class="kv"><span class="label">支撐區</span><span class="value" style="color:#22c55e;">{_esc(key_prices.get("support"))}</span></div>
        <div class="kv"><span class="label">跌破防守</span><span class="value">{_esc(key_prices.get("stop_loss"))}</span></div>
        <div class="kv"><span class="label">強勢關鍵</span><span class="value">{_esc(key_prices.get("breakout"))}</span></div>
      </div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <div class="card-title" style="margin-bottom:4px;border:none;padding:0;">主力燈號</div>
            <div style="font-size:22px;font-weight:bold;" class="badge badge-{_level_class(main_force.get('level'))}">{_esc(_level_label(main_force.get("level")))}</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#94a3b8;max-width:50%;">
            <div style="margin-bottom:2px;">理由：</div>
            <div style="color:#cbd5e1;">{_esc(main_force.get("reason"))}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 型態分析 -->
    <div class="card col-4">
      <div class="card-title">型態分析</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
        <div style="text-align:center;padding:8px;background:#0f172a;border-radius:6px;">
          <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">W 底</div>
          <span class="badge badge-{('safe' if pattern.get('w_bottom') in ('formed','已形成') else 'warn' if pattern.get('w_bottom') in ('forming','形成中') else 'neutral')}">{_esc(_pattern_label(pattern.get("w_bottom")))}</span>
        </div>
        <div style="text-align:center;padding:8px;background:#0f172a;border-radius:6px;">
          <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">M 頭</div>
          <span class="badge badge-{('danger' if pattern.get('m_top') in ('formed','已形成') else 'warn' if pattern.get('m_top') in ('forming','形成中') else 'neutral')}">{_esc(_pattern_label(pattern.get("m_top")))}</span>
        </div>
      </div>
      <div style="border-top:1px solid #334155;margin-top:10px;padding-top:8px;">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">近期 K 線訊號</div>
        <div class="k-signals">{k_signals_html or '<span style="color:#64748b;font-size:11px;">無訊號</span>'}</div>
      </div>
    </div>

    <!-- 技術指標 -->
    <div class="card col-4">
      <div class="card-title">技術指標總覽</div>
      <table>
        <thead>
          <tr><th>指標</th><th class="td-center">趨勢</th><th>說明</th></tr>
        </thead>
        <tbody>{indicators_html}</tbody>
      </table>
    </div>

    <!-- 勝率 + 操作建議 -->
    <div class="col-4" style="display:flex;flex-direction:column;gap:12px;">
      <div class="card">
        <div class="card-title">綜合勝率</div>
        <div class="win-wrap">
          <div class="gauge">
            <svg viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#1e293b" stroke-width="8"/>
              <circle cx="50" cy="50" r="42" fill="none" stroke="#3b82f6" stroke-width="8"
                stroke-dasharray="264" stroke-dashoffset="{ring_offset:.1f}" stroke-linecap="round"/>
            </svg>
            <div class="val">{int(win_rate)}%</div>
          </div>
          <div style="font-size:12px;color:#94a3b8;">
            <div>條件命中率</div>
            <div>{_esc(r.get("win_rate_detail", {}).get("hit", 0))} / {_esc(r.get("win_rate_detail", {}).get("total", 0))}</div>
          </div>
        </div>
      </div>
      <div class="card suggest">
        <div class="card-title">操作建議</div>
        <div class="row"><span class="lbl">策略</span><span style="font-weight:500;">{_esc(suggestion.get("strategy"))}</span></div>
        <div class="row"><span class="lbl">進場點</span><span class="yel">{_esc(suggestion.get("entry"))}</span></div>
        <div class="row"><span class="lbl">加碼點</span><span class="red">{_esc(suggestion.get("add"))}</span></div>
        <div class="row"><span class="lbl">停損點</span><span class="grn">{_esc(suggestion.get("stop_loss"))}</span></div>
        <div class="row"><span class="lbl">防守點</span><span>{_esc(suggestion.get("defense"))}</span></div>
      </div>
    </div>

    <!-- 整體結論 -->
    <div class="card col-12">
      <span class="conclusion">整體結論</span>
      <span style="font-size:13px;color:#cbd5e1;">{_esc(conclusion)}</span>
    </div>
  </div>
</div>
</body>
</html>"""


def save_report(record: dict, reports_dir: str) -> str:
    """產生報告 HTML 並寫檔，回傳檔案路徑"""
    os.makedirs(reports_dir, exist_ok=True)
    ticker = record.get("ticker", "unknown")
    strat  = (record.get("strategy_name") or "strategy").replace("/", "-")
    date_str = (record.get("analyzed_at") or datetime.now().isoformat())[:10]
    fname = f"{ticker}_{strat}_{date_str}.html"
    path = os.path.join(reports_dir, fname)
    html_str = render(record)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_str)
    return path
