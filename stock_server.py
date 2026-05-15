import os
import json
import uuid
import asyncio
import requests
import pandas as pd
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import strategy_engine
import report_generator

load_dotenv()

PROVIDER_NAME = os.getenv("PROVIDER", "shioaji")

# ── TWSE 歷史 K 棒（各 provider 共用）────────────────────────────────────────

TWSE = "https://openapi.twse.com.tw/v1"

_stock_names: dict[str, str] = {}

def _get_stock_name(ticker: str) -> str:
    global _stock_names
    if not _stock_names:
        try:
            rows = requests.get(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=8, verify=False
            ).json()
            _stock_names = {r["公司代號"]: r["公司簡稱"] for r in rows if "公司代號" in r}
        except Exception:
            pass
    return _stock_names.get(ticker, ticker)

def _twse_kbars(ticker: str, days: int) -> list:
    results = []
    today = datetime.today()
    for delta in range(3):
        d = today - timedelta(days=30 * delta)
        url = f"{TWSE}/exchangeReport/STOCK_DAY?stockNo={ticker}&date={d.strftime('%Y%m%d')}"
        try:
            data = requests.get(url, timeout=8).json()
            if not isinstance(data, list):
                continue
            for row in data:
                results.append({
                    "ts":     row.get("Date", ""),
                    "Open":   float(row.get("OpeningPrice", "0").replace(",", "")),
                    "High":   float(row.get("HighestPrice", "0").replace(",", "")),
                    "Low":    float(row.get("LowestPrice",  "0").replace(",", "")),
                    "Close":  float(row.get("ClosingPrice", "0").replace(",", "")),
                    "Volume": int(row.get("TradeVolume", "0").replace(",", "")),
                })
        except Exception:
            continue
    results.sort(key=lambda x: x["ts"])
    return [r for r in results if r["Close"] > 0][-days:]


import csv as _csv

SIGNAL_LOG       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals.csv")
SMART_LOG        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_orders.csv")
MONITOR_LOG      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_log.csv")
STRATEGIES_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies.json")
HISTORY_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_history.json")
SCREEN_HIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screen_history.json")
REPORTS_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

_TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
_TG_CHAT  = os.getenv("CHAT_ID", "")

def _tg(msg: str):
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": _TG_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception:
        pass

_smart_cfg: dict = {"auto": False, "stop_loss_pct": 5.0, "take_profit_pct": 10.0}

_monitors:        dict = {}   # ticker -> monitor state
_auto_log:        list = []   # combined log (all tickers)
_pending_signals: list = []   # queue of pending signals

def _new_monitor(interval: int, qty: int) -> dict:
    return {
        "interval": interval, "quantity": qty,
        "task": None, "running": False,
        "state": {"position": None, "entry_price": None, "entry_time": None, "qty": 0},
        "log": [],
    }

def _load_monitor_log():
    if not os.path.exists(MONITOR_LOG):
        return
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    try:
        df = pd.read_csv(MONITOR_LOG)
        df = df[df["logged_at"] >= cutoff]
        df.to_csv(MONITOR_LOG, index=False)
        for row in df.tail(200).to_dict(orient="records"):
            _auto_log.append(row)
    except Exception:
        pass

def _save_monitor_entry(entry: dict):
    row = {**entry, "logged_at": datetime.now().isoformat()}
    write_header = not os.path.exists(MONITOR_LOG)
    with open(MONITOR_LOG, "a", newline="") as f:
        w = _csv.writer(f)
        if write_header:
            w.writerow(["logged_at","ticker","sig","price","k","d","j","hist","msg"])
        w.writerow([row["logged_at"], row.get("ticker",""), row.get("sig","FLAT"),
                    row.get("price",0), row.get("k",0), row.get("d",0),
                    row.get("j",0), row.get("hist",0), row.get("msg","")])

_load_monitor_log()


# ── 錢哨：策略 / 分析歷史 持久化 ─────────────────────────────────────────────

def _load_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_json(path: str, data: list):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _place_order_internal(ticker: str, action: str, price: float, qty: int) -> dict:
    p = _providers["shioaji"]
    if not p._api:
        return {"error": "未登入"}
    try:
        import shioaji.constant as const
        contract = p._api.Contracts.Stocks[ticker]
        act = const.Action.Buy if action == "buy" else const.Action.Sell
        order = p._api.Order(
            price=price, quantity=qty, action=act,
            price_type=const.StockPriceType.LMT,
            order_type=const.OrderType.ROD,
            order_cond=const.StockOrderCond.Cash,
        )
        trade = p._api.place_order(contract, order)
        result = {
            "ticker": ticker, "action": action, "price": price, "quantity": qty,
            "trade_id": str(getattr(getattr(trade, "order", trade), "id", "")),
        }
        sl_pct = _smart_cfg.get("stop_loss_pct", 5)
        tp_pct = _smart_cfg.get("take_profit_pct", 10)
        result["stop_loss"]   = round(price * (1 - sl_pct / 100), 2)
        result["take_profit"] = round(price * (1 + tp_pct / 100), 2)
        _log_smart_order(result)
        act_zh = "買進" if action == "buy" else "賣出"
        _tg(f"*下單成功｜{ticker}*\n{act_zh} {qty} 張 @ {price}\n停損 {result['stop_loss']}　停利 {result['take_profit']}")
        return result
    except Exception as e:
        return {"error": str(e)}

async def _check_monitor(ticker: str, mon: dict):
    ts  = datetime.now().strftime("%H:%M:%S")
    qty = mon["quantity"]
    p   = _providers["shioaji"]

    if not p._api:
        _auto_log.insert(0, {"time": ts, "ticker": ticker, "msg": "永豐未登入", "signal": False, "sig": "FLAT"})
        return

    try:
        contract = p._api.Contracts.Stocks[ticker]
        today    = datetime.today().strftime("%Y-%m-%d")
        loop     = asyncio.get_event_loop()
        raw      = await loop.run_in_executor(None, lambda: p._api.kbars(contract, start=today, end=today))
        df       = pd.DataFrame({**raw})
        if df.empty:
            _auto_log.insert(0, {"time": ts, "ticker": ticker, "msg": "無K棒（非交易時間）", "signal": False, "sig": "FLAT"})
            return

        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")
        iv = mon["interval"]
        if iv > 1:
            df = df.resample(f"{iv}min").agg(
                Open=("Open","first"), High=("High","max"),
                Low=("Low","min"), Close=("Close","last"), Volume=("Volume","sum"),
            ).dropna()

        result = _daytrade_signal(df)
        sig    = result["signal"]
        ind    = result.get("indicators", {})
        last_p = ind.get("close", 0)

        entry = {
            "time": ts, "ticker": ticker, "price": last_p, "signal": sig != "FLAT",
            "sig": sig,
            "k":    round(ind.get("k", 0), 1),
            "d":    round(ind.get("d", 0), 1),
            "j":    round(ind.get("j", 0), 1),
            "hist": round(ind.get("hist", 0), 4),
            "msg":  (f"【{sig}】" if sig != "FLAT" else "") +
                    f" K={ind.get('k',0):.1f} J={ind.get('j',0):.1f} hist={ind.get('hist',0):.4f} @{last_p}",
        }

        st = mon["state"]
        cur_pos = st.get("position")

        if cur_pos == "LONG" and sig == "SHORT":
            if _smart_cfg.get("auto"):
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _place_order_internal(ticker, "sell", last_p, st["qty"]))
                st.update({"position": None, "entry_price": None, "entry_time": None, "qty": 0})
                entry["msg"] += "  → 平多"
            else:
                _pending_signals.append({"ticker": ticker, "price": last_p, "action": "sell",
                    "signal": "EXIT_LONG→SHORT", "quantity": st["qty"],
                    "k": round(ind.get("k",0),2), "j": round(ind.get("j",0),2)})
                entry["msg"] += "  → 等待平多確認"
                _tg(f"*訊號｜{ticker}*\n平多訊號 @ {last_p}\nK={ind.get('k',0):.1f} J={ind.get('j',0):.1f}\n請至儀表板確認下單")
        elif cur_pos == "SHORT" and sig == "LONG":
            if _smart_cfg.get("auto"):
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _place_order_internal(ticker, "buy", last_p, st["qty"]))
                st.update({"position": None, "entry_price": None, "entry_time": None, "qty": 0})
                entry["msg"] += "  → 平空"
            else:
                _pending_signals.append({"ticker": ticker, "price": last_p, "action": "buy",
                    "signal": "EXIT_SHORT→LONG", "quantity": st["qty"],
                    "k": round(ind.get("k",0),2), "j": round(ind.get("j",0),2)})
                entry["msg"] += "  → 等待平空確認"
                _tg(f"*訊號｜{ticker}*\n平空訊號 @ {last_p}\nK={ind.get('k',0):.1f} J={ind.get('j',0):.1f}\n請至儀表板確認下單")
        elif cur_pos is None and sig in ("LONG", "SHORT"):
            action = "buy" if sig == "LONG" else "sell"
            sig_zh = "做多" if sig == "LONG" else "做空"
            if _smart_cfg.get("auto"):
                res = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _place_order_internal(ticker, action, last_p, qty))
                st.update({"position": sig, "entry_price": last_p, "entry_time": ts, "qty": qty})
                entry["msg"] += f"  → 已自動{action} 停損{res.get('stop_loss','')} 停利{res.get('take_profit','')}"
            else:
                _pending_signals.append({"ticker": ticker, "price": last_p, "action": action,
                    "signal": sig, "quantity": qty,
                    "k": round(ind.get("k",0),2), "j": round(ind.get("j",0),2)})
                entry["msg"] += f"  → 等待確認下單 {qty}張"
                _tg(f"*訊號｜{ticker}*\n{sig_zh} {qty}張 @ {last_p}\nK={ind.get('k',0):.1f} J={ind.get('j',0):.1f}\n請至儀表板確認下單")

        _save_monitor_entry(entry)
        mon["log"].insert(0, entry)
        if len(mon["log"]) > 50:
            mon["log"].pop()
        _auto_log.insert(0, entry)
        if len(_auto_log) > 500:
            _auto_log.pop()
    except Exception as e:
        _auto_log.insert(0, {"time": ts, "ticker": ticker, "msg": f"錯誤：{e}", "signal": False, "sig": "FLAT"})

async def _monitor_loop(ticker: str, mon: dict):
    while mon["running"]:
        await _check_monitor(ticker, mon)
        await asyncio.sleep(mon["interval"] * 60)

def _log_smart_order(data: dict):
    write_header = not os.path.exists(SMART_LOG)
    with open(SMART_LOG, "a", newline="") as f:
        w = _csv.writer(f)
        if write_header:
            w.writerow(["logged_at","ticker","action","price","quantity","stop_loss","take_profit","trade_id"])
        w.writerow([datetime.now().isoformat(), data["ticker"], data["action"],
                    data["price"], data["quantity"],
                    data.get("stop_loss",""), data.get("take_profit",""), data.get("trade_id","")])

def _kd(df: pd.DataFrame, n: int = 9, m: int = 3):
    lo = df["Low"].rolling(n, min_periods=1).min()
    hi = df["High"].rolling(n, min_periods=1).max()
    span = (hi - lo).replace(0, 1)
    rsv = (df["Close"] - lo) / span * 100
    K = rsv.ewm(alpha=1/m, adjust=False).mean()
    D = K.ewm(alpha=1/m, adjust=False).mean()
    return K.round(2), D.round(2), (3*K - 2*D).round(2)

def _macd_ind(df: pd.DataFrame, fast=12, slow=26, sig=9):
    ef = df["Close"].ewm(span=fast, adjust=False).mean()
    es = df["Close"].ewm(span=slow, adjust=False).mean()
    m = ef - es
    s = m.ewm(span=sig, adjust=False).mean()
    return m.round(4), s.round(4), (m - s).round(4)

def _daytrade_signal(df: pd.DataFrame) -> dict:
    if len(df) < 14:
        return {"signal": "FLAT", "reason": "資料不足", "conditions": {}, "indicators": {}}
    close = df["Close"]
    ma5   = close.rolling(5,  min_periods=1).mean()
    ma13  = close.rolling(13, min_periods=1).mean()
    ma50  = close.rolling(50, min_periods=1).mean()
    K, D, J   = _kd(df, n=9, m=3)
    ml, _, hl = _macd_ind(df, fast=6, slow=13, sig=5)

    c      = float(close.iloc[-1])
    k0, k1 = float(K.iloc[-1]), float(K.iloc[-2])
    d0, d1 = float(D.iloc[-1]), float(D.iloc[-2])
    j0, j1 = float(J.iloc[-1]), float(J.iloc[-2])
    m0     = float(ml.iloc[-1])
    h0, h1 = float(hl.iloc[-1]), float(hl.iloc[-2])
    ma5v   = float(ma5.iloc[-1])
    ma13v  = float(ma13.iloc[-1])
    ma50v  = float(ma50.iloc[-1])

    golden = k1 < d1 and k0 >= d0
    death  = k1 > d1 and k0 <= d0

    cl = {
        "long_kd":       golden and k0 < 30,
        "long_macd":     m0 < 0,
        "long_hist":     (h0 < 0 and h0 > h1) or (h1 < 0 and h0 >= 0),
        "long_ma50":     c >= ma50v,
        "short_kd":      death and k0 > 70,
        "short_macd":    m0 > 0,
        "short_hist":    (h0 > 0 and h0 < h1) or (h1 >= 0 and h0 < 0),
        "short_ma50":    c <= ma50v,
        "exit_long_ma":  c < ma5v or c < ma13v,
        "exit_long_j":   j0 >= 100 and j0 < j1 and abs(h0) < abs(h1),
        "exit_short_ma": c > ma5v or c > ma13v,
        "exit_short_j":  j0 <= -100 and j0 > j1 and abs(h0) < abs(h1),
    }

    if all(cl[k] for k in ("long_kd", "long_macd", "long_hist", "long_ma50")):
        sig = "LONG"
    elif all(cl[k] for k in ("short_kd", "short_macd", "short_hist", "short_ma50")):
        sig = "SHORT"
    else:
        sig = "FLAT"

    return {
        "signal": sig,
        "indicators": {
            "close": c,
            "ma5": round(ma5v,2), "ma13": round(ma13v,2), "ma50": round(ma50v,2),
            "k": round(k0,2), "d": round(d0,2), "j": round(j0,2),
            "macd": round(m0,4), "hist": round(h0,4), "hist_prev": round(h1,4),
        },
        "conditions": cl,
    }

def _log_signal(ticker: str, interval: int, row: dict):
    write_header = not os.path.exists(SIGNAL_LOG)
    with open(SIGNAL_LOG, "a", newline="") as f:
        w = _csv.writer(f)
        if write_header:
            w.writerow(["logged_at","ticker","interval","bar_time","close","k","d","j","macd","hist"])
        w.writerow([datetime.now().isoformat(), ticker, f"{interval}m",
                    row["time"], row["close"], row["k"], row["d"], row["j"], row["macd"], row["hist"]])

def _calc_cdp(h: float, l: float, c: float) -> dict:
    cdp = (h + l + 2 * c) / 4
    return {
        "cdp": round(cdp, 2),
        "ah":  round(cdp + (h - l), 2),
        "nh":  round(2 * cdp - l, 2),
        "nl":  round(2 * cdp - h, 2),
        "al":  round(cdp - (h - l), 2),
    }

def _cdp_judgment(op: float, cdp: float, nh: float, nl: float, ah: float, al: float) -> dict:
    if op >= ah:
        return {"direction": "多", "strength": "極強",
                "scenario": "開盤直接突破 AH",
                "strategy": "強勢突破，順勢追多，注意量能配合避免假突破。",
                "stop_loss": f"跌回 NH ({nh:.2f}) 以下止損",
                "target": "無明顯壓力，持倉觀察"}
    elif op >= nh:
        return {"direction": "多", "strength": "強",
                "scenario": "開盤站上 NH",
                "strategy": f"站穩 NH 可追多，目標 AH ({ah:.2f})；若未站穩 NH 考慮減碼。",
                "stop_loss": f"跌破 CDP ({cdp:.2f}) 止損",
                "target": f"AH {ah:.2f}"}
    elif op > cdp:
        return {"direction": "多", "strength": "偏",
                "scenario": "開盤在 CDP 上方",
                "strategy": f"回踩 CDP ({cdp:.2f}) 不破可布局多單，目標 NH ({nh:.2f})。",
                "stop_loss": f"跌破 CDP ({cdp:.2f}) 立即止損",
                "target": f"NH {nh:.2f}"}
    elif op <= al:
        return {"direction": "空", "strength": "極弱",
                "scenario": "開盤貫破 AL",
                "strategy": f"超級弱勢，空方完全掌控；反彈無力站回 AL ({al:.2f}) 可續空。",
                "stop_loss": f"站回 AL ({al:.2f}) 以上止損",
                "target": "無明顯支撐，容易加速殺盤"}
    elif op <= nl:
        return {"direction": "空", "strength": "偏",
                "scenario": "開盤跌破 NL",
                "strategy": f"確認 NL ({nl:.2f}) 反彈無力可做空，目標 AL ({al:.2f})。",
                "stop_loss": f"站回 CDP ({cdp:.2f}) 以上止損",
                "target": f"AL {al:.2f}"}
    else:
        return {"direction": "空", "strength": "偏",
                "scenario": "開盤在 CDP 下方",
                "strategy": f"反彈至 CDP ({cdp:.2f}) 遇壓可做空，跌破 NL ({nl:.2f}) 追空。",
                "stop_loss": f"站回 CDP ({cdp:.2f}) 以上止損",
                "target": f"NL {nl:.2f} → AL {al:.2f}"}

def _safe_float(v) -> float | None:
    import math
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return None

def _calc_technical(ticker: str, kbars: list) -> dict:
    df = pd.DataFrame(kbars)
    if "Close" not in df.columns or len(df) < 14:
        raise HTTPException(status_code=503, detail="K 棒資料不足，無法計算技術指標")
    closes = df["Close"]
    ma5   = float(closes.tail(5).mean())
    ma20  = float(closes.tail(20).mean())
    ma60  = float(closes.tail(60).mean())
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = float(100 - (100 / (1 + gain / loss)).iloc[-1])
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd  = float((ema12 - ema26).iloc[-1])
    signal = float((ema12 - ema26).ewm(span=9).mean().iloc[-1])
    return {
        "ticker": ticker,
        "last":      _safe_float(closes.iloc[-1]),
        "prev":      _safe_float(closes.iloc[-2]),
        "ma5":       _safe_float(ma5),
        "ma20":      _safe_float(ma20),
        "ma60":      _safe_float(ma60),
        "rsi":       _safe_float(rsi),
        "macd":      _safe_float(macd),
        "signal":    _safe_float(signal),
        "histogram": _safe_float(macd - signal),
    }


# ── 抽象基底 ──────────────────────────────────────────────────────────────────

class DataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_healthy(self) -> bool: ...

    @abstractmethod
    def get_quote(self, ticker: str) -> dict: ...

    def get_kbars(self, ticker: str, days: int = 60) -> list:
        return _twse_kbars(ticker, days)

    def get_technical(self, ticker: str) -> dict:
        return _calc_technical(ticker, self.get_kbars(ticker, 120))


# ── XQ Provider ───────────────────────────────────────────────────────────────

class XQProvider(DataProvider):
    name = "xq"

    def __init__(self):
        self.base = os.getenv("XQ_SERVER", "http://localhost:8089")

    def is_healthy(self) -> bool:
        try:
            return requests.get(f"{self.base}/health", timeout=3).json().get("status") == "ok"
        except Exception:
            return False

    def get_quote(self, ticker: str) -> dict:
        try:
            data = requests.get(f"{self.base}/realtime/{ticker}", timeout=5)
            if data.status_code == 404:
                raise HTTPException(status_code=404, detail=f"無此股票代碼：{ticker}")
            data.raise_for_status()
            d = data.json()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"XQ 連線失敗：{e}")

        price = d.get("price") or 0
        return {
            "ticker":    ticker,
            "name":      _get_stock_name(ticker),
            "close":     price,
            "open":      price,
            "high":      price,
            "low":       price,
            "change":    0,
            "changePct": 0,
            "volume":    d.get("volume", 0),
            "timestamp": d.get("time", datetime.now().isoformat()),
        }

    def get_kbars(self, ticker: str, days: int = 60) -> list:
        try:
            data = requests.get(f"{self.base}/kbar/{ticker}?period=D&bars={days}", timeout=10)
            data.raise_for_status()
            rows = data.json()
            return [{"ts": r.get("date",""), "Open": r.get("open",0), "High": r.get("high",0),
                     "Low": r.get("low",0), "Close": r.get("close",0), "Volume": r.get("volume",0)}
                    for r in rows]
        except Exception:
            return _twse_kbars(ticker, days)


# ── Shioaji Provider ──────────────────────────────────────────────────────────

class ShioajiProvider(DataProvider):
    name = "shioaji"

    def __init__(self):
        self._api = None

    def is_healthy(self) -> bool:
        return self._api is not None

    def login(self, api_key: str, secret_key: str, simulation: bool):
        import shioaji as sj
        self._api = sj.Shioaji(simulation=simulation)
        return self._api.login(api_key, secret_key)

    def logout(self):
        if self._api:
            self._api.logout()
            self._api = None

    def get_quote(self, ticker: str) -> dict:
        if not self._api:
            raise HTTPException(status_code=503, detail="尚未登入永豐 API")
        contract = self._api.Contracts.Stocks[ticker]
        if contract is None:
            raise HTTPException(status_code=404, detail=f"無此股票代碼：{ticker}")
        snap = self._api.snapshots([contract])[0]
        return {
            "ticker": ticker, "name": contract.name,
            "close": snap.close, "open": snap.open,
            "high":  snap.high,  "low":  snap.low,
            "change": snap.change_price, "changePct": snap.change_rate,
            "volume": snap.volume, "timestamp": snap.ts,
        }

    def get_kbars(self, ticker: str, days: int = 60) -> list:
        if not self._api:
            return _twse_kbars(ticker, days)
        contract = self._api.Contracts.Stocks[ticker]
        end   = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        kbars = self._api.kbars(contract, start=start, end=end)
        return pd.DataFrame({**kbars}).to_dict(orient="records")


# ── Provider Registry ─────────────────────────────────────────────────────────

_providers: dict[str, DataProvider] = {
    "xq":      XQProvider(),
    "shioaji": ShioajiProvider(),
}

active: DataProvider = _providers.get(PROVIDER_NAME, _providers["xq"])


# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI(title="股票儀表板 API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def dashboard():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html"))


@app.get("/qianshao.html")
def qianshao_page():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "qianshao.html"))


@app.get("/qianshao")
def qianshao():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_manager_preview.html"))


FINMIND = "https://api.finmindtrade.com/api/v4/data"
TAIFEX = "https://openapi.taifex.com.tw/v1"

_finmind_cache: dict = {}

def _finmind(dataset: str, data_id: str = "", days: int = 90) -> list:
    key = f"{dataset}:{data_id}:{days}"
    cached = _finmind_cache.get(key)
    now = datetime.now()
    if cached and (now - cached["ts"]).total_seconds() < 600:
        return cached["data"]
    start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {"dataset": dataset, "start_date": start}
    if data_id: params["data_id"] = data_id
    try:
        r = requests.get(FINMIND, params=params, timeout=10).json()
        data = r.get("data", []) if r.get("status") == 200 else []
        _finmind_cache[key] = {"ts": now, "data": data}
        return data
    except Exception:
        return []


@app.get("/fundamental/{ticker}")
def get_fundamental(ticker: str):
    try:
        rows = requests.get(f"{TWSE}/exchangeReport/BWIBBU_d", timeout=8).json()
        row = next((r for r in rows if r.get("Code") == ticker), None)
        def to_float(k):
            try: return float(row[k].replace(",", ""))
            except: return None
        pe = to_float("PEratio") if row else None
        pb = to_float("PBratio") if row else None
        dy = to_float("DividendYield") if row else None
        twse_close = to_float("ClosePrice") if row else None
        annual_div = round(twse_close * dy / 100, 2) if (twse_close and dy) else None

        eps_4q = None
        revenue_yoy = None
        net_margin = None
        op_margin = None

        fs = _finmind("TaiwanStockFinancialStatements", ticker, days=540)
        if fs:
            by_date: dict = {}
            for r in fs:
                d = r.get("date"); t = r.get("type"); v = r.get("value")
                if not d or v is None: continue
                by_date.setdefault(d, {})[t] = v
            quarters = sorted(by_date.keys(), reverse=True)
            eps_vals = [by_date[d].get("EPS") for d in quarters if by_date[d].get("EPS") is not None][:4]
            if eps_vals: eps_4q = round(sum(eps_vals), 2)
            latest = by_date.get(quarters[0], {}) if quarters else {}
            rev = latest.get("Revenue")
            op_inc = latest.get("OperatingIncome")
            net_inc = latest.get("IncomeFromContinuingOperations") or latest.get("TotalConsolidatedProfitForThePeriod")
            if rev and op_inc: op_margin = round(op_inc / rev * 100, 2)
            if rev and net_inc: net_margin = round(net_inc / rev * 100, 2)

        rev = _finmind("TaiwanStockMonthRevenue", ticker, days=400)
        if rev and len(rev) >= 13:
            rev_sorted = sorted(rev, key=lambda x: x.get("date", ""), reverse=True)
            this_m = rev_sorted[0].get("revenue")
            yoy_m = next((r.get("revenue") for r in rev_sorted if r.get("revenue_year") == rev_sorted[0].get("revenue_year") - 1 and r.get("revenue_month") == rev_sorted[0].get("revenue_month")), None)
            if this_m and yoy_m and yoy_m > 0:
                revenue_yoy = round((this_m - yoy_m) / yoy_m * 100, 2)

        return {
            "pe": pe, "pb": pb, "dividendYield": dy,
            "eps4q": eps_4q,
            "revenueYoY": revenue_yoy,
            "netMargin": net_margin,
            "opMargin": op_margin,
            "twseClose": twse_close,
            "annualDivPerShare": annual_div,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/chip/{ticker}")
def get_chip(ticker: str, history_days: int = 0):
    try:
        f, tr, d = 0.0, 0.0, 0.0
        try:
            r = requests.get(f"{TWSE}/fund/T86", timeout=10)
            rows = r.json()
            row = next((rr for rr in rows if rr.get("Code") == ticker), None)
            def parse(k):
                try: return float(row[k].replace(",", ""))
                except: return 0.0
            if row:
                f = parse("外陸資買賣超股數(千股)")
                tr = parse("投信買賣超股數(千股)")
                d = parse("自營商買賣超股數(千股)")
        except Exception:
            pass
        result = {"foreignNet": f, "investTrustNet": tr, "dealerNet": d, "total": f + tr + d}

        if history_days > 0:
            hist = _finmind("TaiwanStockInstitutionalInvestorsBuySell", ticker, days=history_days * 2)
            by_date: dict = {}
            for r in hist:
                d_ = r.get("date"); name = r.get("name"); buy = r.get("buy", 0) or 0; sell = r.get("sell", 0) or 0
                if not d_: continue
                by_date.setdefault(d_, {})[name] = buy - sell
            dates = sorted(by_date.keys(), reverse=True)[:history_days]
            def streak(key_match):
                cnt = 0; sign = 0
                for dt in dates:
                    rec = by_date.get(dt, {})
                    val = sum(v for k, v in rec.items() if any(m in k for m in key_match))
                    if val == 0: break
                    s = 1 if val > 0 else -1
                    if sign == 0: sign = s
                    elif sign != s: break
                    cnt += 1
                return cnt * sign
            result["foreignStreak"] = streak(["Foreign"])
            result["trustStreak"] = streak(["Investment_Trust"])
            result["dealerStreak"] = streak(["Dealer"])
            result["history"] = [{"date": dt, **by_date[dt]} for dt in dates]

        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/events/{ticker}")
def get_events(ticker: str):
    try:
        events = []

        def _twroc_to_iso(s: str):
            if not s or len(s) != 7: return ""
            try:
                yr = int(s[:3]) + 1911
                return f"{yr}-{s[3:5]}-{s[5:]}"
            except Exception: return ""

        def _minus_workdays(iso: str, n: int) -> str:
            try:
                cur = datetime.strptime(iso, "%Y-%m-%d").date()
                cnt = 0
                while cnt < n:
                    cur = cur - timedelta(days=1)
                    if cur.weekday() < 5: cnt += 1
                return cur.isoformat()
            except Exception: return ""

        try:
            rows = requests.get(f"{TWSE}/opendata/t187ap45_L", timeout=10).json()
            for r in rows:
                if r.get("公司代號") != ticker: continue
                sh_iso = _twroc_to_iso(r.get("股東會日期", ""))
                ex_iso = _twroc_to_iso(r.get("董事會（擬議）股利分派日") or r.get("董事會擬議股利分派日") or "")
                cash = r.get("股東配發-盈餘分配之現金股利(元/股)") or r.get("董事會擬議分派之盈餘現金股利(元/股)") or ""
                try: cash = f"{float(cash):.2f}" if cash else ""
                except Exception: pass
                if sh_iso:
                    events.append({"type": "shareholder_meeting", "date": sh_iso, "label": "股東會", "extra": ""})
                    repay_iso = _minus_workdays(sh_iso, 6)
                    if repay_iso: events.append({"type": "short_force_repay", "date": repay_iso, "label": "融券強制回補日", "extra": "股東會前 6 個營業日"})
                if ex_iso:
                    events.append({"type": "ex_dividend", "date": ex_iso, "label": "除權息", "extra": f"現金股利 ${cash}" if cash else ""})
                break
        except Exception: pass

        try:
            margin_rows = requests.get(f"{TWSE}/exchangeReport/MI_MARGN", timeout=10).json()
            mr = next((r for r in margin_rows if r.get("股票代號") == ticker), None)
            if mr:
                short_bal = mr.get("融券今日餘額", "0").replace(",", "")
                events.append({"type": "short_balance", "date": "", "label": "融券餘額", "extra": f"{short_bal} 張"})
        except Exception: pass

        today = datetime.today().date()
        for e in events:
            if e.get("date"):
                try:
                    ed = datetime.strptime(e["date"], "%Y-%m-%d").date()
                    e["daysLeft"] = (ed - today).days
                except Exception: pass
        events.sort(key=lambda x: x.get("daysLeft", 9999))
        return {"ticker": ticker, "events": events}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/macro/dashboard")
def get_macro_dashboard():
    try:
        result = {}

        try:
            pcr = requests.get(f"{TAIFEX}/PutCallRatio", timeout=10).json()
            if pcr:
                latest = pcr[0]
                result["pcr"] = float(latest.get("PutCallVolumeRatio%", 0)) / 100 if latest.get("PutCallVolumeRatio%") else None
                result["pcrOI"] = float(latest.get("PutCallOIRatio%", 0)) / 100 if latest.get("PutCallOIRatio%") else None
                result["pcrDate"] = latest.get("Date")
        except Exception: pass

        spot_close, spot_chg = None, None
        try:
            taiex = requests.get(f"{TWSE}/exchangeReport/MI_INDEX", params={"type": "IND"}, timeout=10).json()
            for r in taiex:
                if r.get("指數") == "發行量加權股價指數":
                    cp = r.get("收盤指數")
                    chg = r.get("漲跌點數")
                    direction = r.get("漲跌")
                    spot_close = float(str(cp).replace(",", "")) if cp else None
                    if chg and direction:
                        spot_chg = float(str(chg).replace(",", ""))
                        if direction == "-": spot_chg = -spot_chg
                    break
        except Exception: pass
        result["spot"] = spot_close
        result["spotChange"] = spot_chg

        try:
            fut = requests.get(f"{TAIFEX}/DailyMarketReportFut", timeout=10).json()
            tx_near = [r for r in fut if r.get("Contract") == "TX" and r.get("TradingSession") == "一般"]
            if tx_near:
                tx_near.sort(key=lambda x: x.get("ContractMonth(Week)", ""))
                near = tx_near[0]
                result["futClose"] = float(str(near.get("Last", "0")).replace(",", "")) if near.get("Last") not in ("-", "", None) else None
                result["futChange"] = float(str(near.get("Change", "0")).replace(",", "")) if near.get("Change") not in ("-", "", None) else None
                result["futOI"] = int(str(near.get("OpenInterest", "0")).replace(",", "")) if near.get("OpenInterest") not in ("-", "", None) else None
                result["futVolume"] = int(str(near.get("Volume", "0")).replace(",", "")) if near.get("Volume") not in ("-", "", None) else None
                if result.get("futClose") and spot_close:
                    result["basis"] = round((result["futClose"] - spot_close) / spot_close * 100, 3)
        except Exception: pass

        try:
            opt = requests.get(f"{TAIFEX}/DailyMarketReportOpt", timeout=15).json()
            txo = [r for r in opt if r.get("Contract") == "TXO" and r.get("TradingSession") == "一般"]
            if txo and spot_close:
                today_str = (opt[0].get("Date") or "") if opt else ""
                contracts = sorted({r.get("ContractMonth(Week)", "") for r in txo if r.get("ContractMonth(Week)", "") >= today_str[:6]})
                near_month = contracts[0] if contracts else sorted({r.get("ContractMonth(Week)", "") for r in txo})[0]
                near_opts = [r for r in txo if r.get("ContractMonth(Week)") == near_month]
                calls = [r for r in near_opts if r.get("CallPut") == "買權"]
                puts = [r for r in near_opts if r.get("CallPut") == "賣權"]
                def to_int(v):
                    try: return int(str(v).replace(",", ""))
                    except: return 0
                def to_f(v):
                    try: return float(str(v).replace(",", ""))
                    except: return None
                near_band = lambda r: abs((to_f(r.get("StrikePrice")) or 0) - spot_close) <= spot_close * 0.1
                near_calls = [r for r in calls if near_band(r)]
                near_puts = [r for r in puts if near_band(r)]
                if near_calls:
                    call_max = max(near_calls, key=lambda x: to_int(x.get("OpenInterest")))
                    result["callMaxOIStrike"] = to_f(call_max.get("StrikePrice"))
                    result["callMaxOI"] = to_int(call_max.get("OpenInterest"))
                if near_puts:
                    put_max = max(near_puts, key=lambda x: to_int(x.get("OpenInterest")))
                    result["putMaxOIStrike"] = to_f(put_max.get("StrikePrice"))
                    result["putMaxOI"] = to_int(put_max.get("OpenInterest"))
                atm = min(calls + puts, key=lambda x: abs((to_f(x.get("StrikePrice")) or 0) - spot_close)) if (calls + puts) else None
                if atm:
                    atm_strike = to_f(atm.get("StrikePrice"))
                    atm_call = next((r for r in calls if to_f(r.get("StrikePrice")) == atm_strike), None)
                    atm_put = next((r for r in puts if to_f(r.get("StrikePrice")) == atm_strike), None)
                    cp = to_f(atm_call.get("Close")) if atm_call else None
                    pp = to_f(atm_put.get("Close")) if atm_put else None
                    if cp is not None and pp is not None and cp > 0:
                        result["skew"] = round((pp - cp) / cp * 100, 2)
                        result["atmStrike"] = atm_strike
                        result["atmCallPremium"] = cp
                        result["atmPutPremium"] = pp
        except Exception: pass

        ai_parts = []
        if result.get("futClose") and result.get("spot"):
            diff = (result["futClose"] - result["spot"]) / result["spot"] * 100
            if diff > 0.3: ai_parts.append(f"期貨領先現貨 +{diff:.2f}%，指數部位有領先表態跡象。")
            elif diff < -0.3: ai_parts.append(f"期貨弱於現貨 {diff:.2f}%，期貨部位偏空表態。")
        if result.get("pcr") is not None:
            p = result["pcr"]
            if p < 0.85: ai_parts.append(f"PCR {p:.2f} 偏多結構，選擇權市場看多情緒高亢，留意過熱追價風險。")
            elif p > 1.15: ai_parts.append(f"PCR {p:.2f} 偏空保護，市場大量買進 Put 下檔防護。")
            else: ai_parts.append(f"PCR {p:.2f} 中性結構。")
        if result.get("basis") is not None:
            b = result["basis"]
            if b > 0.1: ai_parts.append(f"基差 +{b:.2f}% 短線資金強勢追價。")
            elif b < -0.1: ai_parts.append(f"基差 {b:.2f}% 貼水避險偏重。")
        result["aiText"] = "".join(ai_parts) or "市場狀態平穩，無特殊訊號。"

        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/branch/{ticker}")
def get_branch(ticker: str):
    """分點進出 — FinMind 免費版不提供，用替代資料：外資持股比 + 三大法人歷史"""
    try:
        result = {"ticker": ticker, "available": False, "note": "分點進出資料需付費資料源 (FinMind Pro / TEJ)，目前以三大法人歷史替代"}

        hist = _finmind("TaiwanStockInstitutionalInvestorsBuySell", ticker, days=30)
        if hist:
            by_date: dict = {}
            for r in hist:
                d = r.get("date"); name = r.get("name"); buy = r.get("buy", 0) or 0; sell = r.get("sell", 0) or 0
                if not d: continue
                by_date.setdefault(d, {})[name] = (buy - sell) / 1000
            dates = sorted(by_date.keys())
            series = []
            for dt in dates:
                rec = by_date[dt]
                f = sum(v for k, v in rec.items() if "Foreign" in k)
                t = sum(v for k, v in rec.items() if "Trust" in k)
                dl = sum(v for k, v in rec.items() if "Dealer" in k)
                series.append({"date": dt, "foreign": round(f, 1), "trust": round(t, 1), "dealer": round(dl, 1), "total": round(f + t + dl, 1)})
            result["series"] = series
            result["available"] = True

            cum = {"foreign": 0.0, "trust": 0.0, "dealer": 0.0}
            for s in series:
                cum["foreign"] += s["foreign"]; cum["trust"] += s["trust"]; cum["dealer"] += s["dealer"]
            ranking = sorted([
                {"name": "外資及陸資", "type": "外資系", "net": round(cum["foreign"], 0)},
                {"name": "投信", "type": "本土系", "net": round(cum["trust"], 0)},
                {"name": "自營商", "type": "本土系", "net": round(cum["dealer"], 0)},
            ], key=lambda x: -abs(x["net"]))
            result["ranking"] = ranking

        sh = _finmind("TaiwanStockShareholding", ticker, days=14)
        if sh:
            sh_sorted = sorted(sh, key=lambda x: x.get("date", ""), reverse=True)
            result["foreignRatio"] = sh_sorted[0].get("ForeignInvestmentSharesRatio")

        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/health")
def health():
    return {
        "status":    "ok",
        "provider":  active.name,
        "connected": active.is_healthy(),
        "available": list(_providers.keys()),
    }


@app.post("/provider/{name}")
def switch_provider(name: str):
    global active
    if name not in _providers:
        raise HTTPException(status_code=400, detail=f"不支援的來源：{name}，可用：{list(_providers.keys())}")
    active = _providers[name]
    return {"provider": active.name, "connected": active.is_healthy()}


@app.post("/login")
def login():
    p: ShioajiProvider = _providers["shioaji"]
    api_key    = os.getenv("SINOPAC_API_KEY", "")
    secret_key = os.getenv("SINOPAC_SECRET_KEY", "")
    simulation = os.getenv("SIMULATION", "true").lower() == "true"
    if not api_key or not secret_key:
        raise HTTPException(status_code=400, detail="請在 .env 設定金鑰")
    try:
        accounts = p.login(api_key, secret_key, simulation)
        result = {"status": "ok", "accounts": [str(a) for a in accounts], "ca": False}
        ca_path   = os.getenv("CA_PATH", "")
        ca_passwd = os.getenv("CA_PASSWD", "")
        person_id = os.getenv("PERSON_ID", "")
        if ca_path and ca_passwd and person_id and os.path.exists(ca_path):
            p._api.activate_ca(ca_path=ca_path, ca_passwd=ca_passwd, person_id=person_id)
            result["ca"] = True
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"登入失敗：{e}")


@app.post("/logout")
def logout():
    _providers["shioaji"].logout()
    return {"status": "logged_out"}


@app.get("/intraday/{ticker}")
def get_intraday(ticker: str, interval: int = 1):
    p = _providers["shioaji"]
    if not p._api:
        raise HTTPException(status_code=503, detail="需要永豐登入")
    try:
        contract = p._api.Contracts.Stocks[ticker]
        today = datetime.today().strftime("%Y-%m-%d")
        raw = p._api.kbars(contract, start=today, end=today)
        df = pd.DataFrame({**raw})
        if df.empty:
            return []
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")
        if interval > 1:
            df = df.resample(f"{interval}min").agg(
                Open=("Open", "first"), High=("High", "max"),
                Low=("Low", "min"), Close=("Close", "last"),
                Volume=("Volume", "sum"),
            ).dropna()
        K, D, J = _kd(df)
        macd, sig, hist = _macd_ind(df)
        df = df.reset_index()
        df["time"] = df["ts"].astype("int64") // 10**9
        df["k"] = K.values
        df["d"] = D.values
        df["j"] = J.values
        df["macd"] = macd.values
        df["sig"]  = sig.values
        df["hist"] = hist.values
        df["signal"] = ((K < 20) & (J < 0)).values
        result = (
            df[["time","Open","High","Low","Close","k","d","j","macd","sig","hist","signal"]]
            .rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})
            .to_dict(orient="records")
        )
        for row in result:
            if row["signal"]:
                _log_signal(ticker, interval, row)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/bigvol/{ticker}")
def get_bigvol(ticker: str, lot_min: int = 50):
    p = _providers["shioaji"]
    if not p._api:
        raise HTTPException(status_code=503, detail="需要永豐登入")
    try:
        contract = p._api.Contracts.Stocks[ticker]
        today = datetime.today().strftime("%Y-%m-%d")
        ticks = p._api.ticks(contract, date=today)
        df = pd.DataFrame({**ticks})
        if df.empty:
            return {"total_lots": 0, "big_trades": 0, "net_lots": 0, "signal": "neutral", "bars": []}
        df["lots"] = df["volume"] // 1000
        big = df[df["lots"] >= lot_min].copy()
        if big.empty:
            return {"total_lots": 0, "big_trades": 0, "net_lots": 0, "signal": "neutral", "bars": []}

        big["minute"] = pd.to_datetime(big["ts"]).dt.strftime("%H:%M")
        buy_m = big[big["tick_type"] == 1].groupby("minute")["lots"].sum()
        sell_m = big[big["tick_type"] == 2].groupby("minute")["lots"].sum()
        all_mins = sorted(set(buy_m.index) | set(sell_m.index))
        bars = [{"t": m, "b": int(buy_m.get(m, 0)), "s": int(sell_m.get(m, 0))} for m in all_mins]

        buy_total  = int(buy_m.sum())
        sell_total = int(sell_m.sum())
        net = buy_total - sell_total
        threshold = max(100, int((buy_total + sell_total) * 0.2))
        signal = "buy" if net >= threshold else "sell" if net <= -threshold else "neutral"

        return {
            "total_lots": int(big["lots"].sum()),
            "big_trades": int(len(big)),
            "net_lots": net,
            "signal": signal,
            "bars": bars,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/auto_trade/start")
async def start_auto_trade(body: dict):
    ticker   = str(body.get("ticker", "")).upper()
    interval = int(body.get("interval", 3))
    quantity = int(body.get("quantity", 1))
    if not ticker:
        raise HTTPException(status_code=400, detail="缺少 ticker")
    if ticker in _monitors and _monitors[ticker]["running"]:
        return {"status": "already_running", "ticker": ticker}
    mon = _new_monitor(interval, quantity)
    mon["running"] = True
    mon["task"]    = asyncio.create_task(_monitor_loop(ticker, mon))
    _monitors[ticker] = mon
    return {"status": "started", "ticker": ticker}

@app.post("/auto_trade/stop")
async def stop_auto_trade(body: dict = {}):
    ticker = str(body.get("ticker", "")).upper() if body else ""
    targets = [ticker] if ticker and ticker in _monitors else list(_monitors.keys())
    for t in targets:
        mon = _monitors.get(t)
        if mon:
            mon["running"] = False
            if mon["task"]:
                mon["task"].cancel()
                mon["task"] = None
    if ticker:
        _monitors.pop(ticker, None)
    else:
        _monitors.clear()
    return {"status": "stopped", "tickers": targets}

@app.get("/auto_trade/status")
def get_auto_status():
    monitors_info = {
        t: {
            "running":  mon["running"],
            "interval": mon["interval"],
            "quantity": mon["quantity"],
            "position": mon["state"].get("position"),
            "latest":   mon["log"][0] if mon["log"] else None,
        }
        for t, mon in _monitors.items()
    }
    pending = _pending_signals[0] if _pending_signals else None
    return {
        "running":        any(m["running"] for m in _monitors.values()),
        "monitors":       monitors_info,
        "log":            _auto_log[:50],
        "pending_signal": pending,
    }

@app.post("/auto_trade/clear_pending")
def clear_pending():
    if _pending_signals:
        _pending_signals.pop(0)
    return {"ok": True, "remaining": len(_pending_signals)}


@app.get("/positions")
def get_positions():
    if not os.path.exists(SMART_LOG):
        return []
    try:
        df = pd.read_csv(SMART_LOG)
        if df.empty:
            return []
        pos_map: dict = {}
        for _, row in df.iterrows():
            t      = str(row["ticker"])
            action = str(row["action"])
            qty    = int(row["quantity"])
            price  = float(row["price"])
            sl     = _safe_float(row.get("stop_loss", ""))
            tp     = _safe_float(row.get("take_profit", ""))
            sim    = str(row.get("trade_id", "")).startswith("SIM-")
            if t not in pos_map:
                pos_map[t] = {"ticker": t, "qty": 0, "total_cost": 0.0,
                               "stop_loss": None, "take_profit": None, "simulated": sim}
            p = pos_map[t]
            if action == "buy":
                p["total_cost"] += price * qty
                p["qty"]        += qty
                if sl: p["stop_loss"]   = sl
                if tp: p["take_profit"] = tp
            elif action == "sell" and p["qty"] > 0:
                ratio = min(qty, p["qty"]) / p["qty"]
                p["total_cost"] *= (1 - ratio)
                p["qty"] = max(0, p["qty"] - qty)

        result = []
        for t, p in pos_map.items():
            if p["qty"] <= 0:
                continue
            avg = round(p["total_cost"] / p["qty"], 2)
            entry = {"ticker": t, "qty": p["qty"], "avg_cost": avg,
                     "stop_loss": p["stop_loss"], "take_profit": p["take_profit"],
                     "simulated": p["simulated"],
                     "current_price": None, "pnl": None, "pnl_pct": None,
                     "sl_dist_pct": None, "tp_dist_pct": None}
            try:
                q   = active.get_quote(t)
                cur = q["close"]
                entry["current_price"] = cur
                entry["pnl"]     = round((cur - avg) * p["qty"] * 1000, 0)
                entry["pnl_pct"] = round((cur - avg) / avg * 100, 2)
                if p["stop_loss"]:
                    entry["sl_dist_pct"] = round((cur - p["stop_loss"]) / cur * 100, 2)
                if p["take_profit"]:
                    entry["tp_dist_pct"] = round((p["take_profit"] - cur) / cur * 100, 2)
            except Exception:
                pass
            result.append(entry)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/smart_order/config")
def get_smart_config():
    return _smart_cfg

@app.post("/smart_order/config")
def set_smart_config(body: dict):
    for k in ("auto", "stop_loss_pct", "take_profit_pct"):
        if k in body:
            _smart_cfg[k] = body[k]
    return _smart_cfg

@app.post("/order")
def place_order_endpoint(body: dict):
    ticker     = body.get("ticker", "")
    action     = body.get("action", "buy")
    price      = float(body.get("price", 0))
    qty        = int(body.get("quantity", 1))
    smart      = bool(body.get("smart", False))
    simulation = bool(body.get("simulation", True))
    if not ticker or price <= 0 or qty < 1:
        raise HTTPException(status_code=400, detail="缺少必要參數")

    result = {
        "ticker": ticker, "action": action, "price": price, "quantity": qty,
        "simulation": simulation,
    }
    if smart:
        sl_pct = float(body.get("stop_loss_pct",  _smart_cfg["stop_loss_pct"]))
        tp_pct = float(body.get("take_profit_pct", _smart_cfg["take_profit_pct"]))
        result["stop_loss"]   = round(price * (1 - sl_pct / 100), 2)
        result["take_profit"] = round(price * (1 + tp_pct / 100), 2)

    if simulation:
        result["status"]   = "simulated"
        result["trade_id"] = f"SIM-{datetime.now().strftime('%H%M%S%f')[:12]}"
        _log_smart_order(result)
        return result

    p = _providers["shioaji"]
    if not p._api:
        raise HTTPException(status_code=503, detail="需要永豐登入")
    try:
        import shioaji.constant as const
        contract = p._api.Contracts.Stocks[ticker]
        act = const.Action.Buy if action == "buy" else const.Action.Sell
        order = p._api.Order(
            price=price, quantity=qty, action=act,
            price_type=const.StockPriceType.LMT,
            order_type=const.OrderType.ROD,
            order_cond=const.StockOrderCond.Cash,
        )
        trade = p._api.place_order(contract, order)
        result["status"]   = "ok"
        result["trade_id"] = str(getattr(getattr(trade, "order", trade), "id", ""))
        _log_smart_order(result)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/signals/{ticker}")
def get_signals(ticker: str, limit: int = 50):
    if not os.path.exists(SIGNAL_LOG):
        return []
    try:
        df = pd.read_csv(SIGNAL_LOG)
        df = df[df["ticker"] == ticker].tail(limit)
        return df.to_dict(orient="records")
    except Exception:
        return []

@app.get("/monitor_log/{ticker}")
def get_monitor_log(ticker: str):
    if not os.path.exists(MONITOR_LOG):
        return []
    try:
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        df = pd.read_csv(MONITOR_LOG)
        df = df[(df["ticker"] == ticker) & (df["logged_at"] >= cutoff)]
        return df.sort_values("logged_at", ascending=False).to_dict(orient="records")
    except Exception:
        return []


@app.get("/cdp/{ticker}")
def get_cdp(ticker: str):
    kbars = _twse_kbars(ticker, 5)
    if len(kbars) < 1:
        raise HTTPException(status_code=503, detail="K 棒資料不足")
    prev = kbars[-1]
    levels = _calc_cdp(prev["High"], prev["Low"], prev["Close"])
    open_price = None
    try:
        q = active.get_quote(ticker)
        open_price = q.get("open") or q.get("close")
    except Exception:
        pass
    result = {
        "ticker":    ticker,
        "ref_date":  prev["ts"],
        "ref_high":  prev["High"],
        "ref_low":   prev["Low"],
        "ref_close": prev["Close"],
        **levels,
        "open_price": open_price,
    }
    if open_price:
        result["judgment"] = _cdp_judgment(
            open_price, levels["cdp"], levels["nh"], levels["nl"], levels["ah"], levels["al"]
        )
    return result


@app.get("/strategy/signal/{ticker}")
def get_strategy_signal(ticker: str, interval: int = 3):
    p = _providers["shioaji"]
    if not p._api:
        raise HTTPException(status_code=503, detail="需要永豐登入")
    try:
        contract = p._api.Contracts.Stocks[ticker]
        today = datetime.today().strftime("%Y-%m-%d")
        raw = p._api.kbars(contract, start=today, end=today)
        df  = pd.DataFrame({**raw})
        if df.empty:
            return {"signal": "FLAT", "reason": "無盤中資料", "conditions": {}, "indicators": {}}
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")
        if interval > 1:
            df = df.resample(f"{interval}min").agg(
                Open=("Open","first"), High=("High","max"),
                Low=("Low","min"), Close=("Close","last"), Volume=("Volume","sum"),
            ).dropna()
        return _daytrade_signal(df)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 錢哨：策略管理 / 分析 ────────────────────────────────────────────────────

def _empty_conditions() -> dict:
    return {"fundamental": [], "technical": [], "chips": [], "pattern": [], "volume": []}


def _empty_logic_notes() -> dict:
    return {"summary": "", "entry_logic": "", "exit_logic": "", "remarks": ""}


@app.get("/qianshao/strategies")
def list_strategies():
    return _load_json(STRATEGIES_FILE)


@app.post("/qianshao/strategies")
def create_strategy(body: dict):
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="缺少 name")
    now = _now_iso()
    strat = {
        "id":          body.get("id") or str(uuid.uuid4()),
        "name":        body["name"],
        "created_at":  now,
        "updated_at":  now,
        "conditions":  body.get("conditions") or _empty_conditions(),
        "logic_notes": body.get("logic_notes") or _empty_logic_notes(),
    }
    strategies = _load_json(STRATEGIES_FILE)
    strategies.append(strat)
    _save_json(STRATEGIES_FILE, strategies)
    return strat


@app.put("/qianshao/strategies/{strategy_id}")
def update_strategy(strategy_id: str, body: dict):
    strategies = _load_json(STRATEGIES_FILE)
    for s in strategies:
        if s.get("id") == strategy_id:
            for k in ("name", "conditions", "logic_notes"):
                if k in body:
                    s[k] = body[k]
            s["updated_at"] = _now_iso()
            _save_json(STRATEGIES_FILE, strategies)
            return s
    raise HTTPException(status_code=404, detail="策略不存在")


@app.delete("/qianshao/strategies/{strategy_id}")
def delete_strategy(strategy_id: str):
    strategies = _load_json(STRATEGIES_FILE)
    new_list = [s for s in strategies if s.get("id") != strategy_id]
    if len(new_list) == len(strategies):
        raise HTTPException(status_code=404, detail="策略不存在")
    _save_json(STRATEGIES_FILE, new_list)
    return {"status": "deleted", "id": strategy_id}


def _build_chip_data_from_existing(ticker: str) -> dict:
    """先嘗試直接呼叫 strategy_engine.calc_chips（爬 5 個交易日），
    若失敗則 fallback 至既有 /chip 單日資料。"""
    try:
        return strategy_engine.calc_chips(ticker)
    except Exception:
        pass
    try:
        rows = requests.get(f"{TWSE}/fund/T86", timeout=10).json()
        row = next((r for r in rows if r.get("Code") == ticker), None)
        if row:
            def parse(k):
                try: return float(row[k].replace(",", ""))
                except: return 0.0
            f  = parse("外陸資買賣超股數(千股)")
            tr = parse("投信買賣超股數(千股)")
            d  = parse("自營商買賣超股數(千股)")
            today = datetime.today().strftime("%m/%d")
            chips = [{
                "date":    today,
                "foreign": round(f),
                "trust":   round(tr),
                "dealer":  round(d),
                "total":   round(f + tr + d),
            }]
            level = "safe" if (f + tr) > 0 else ("danger" if (f + tr) < 0 else "watch")
            reason = "法人單日買超" if level == "safe" else ("法人單日賣超" if level == "danger" else "法人持平")
            return {
                "chips":      chips,
                "conclusion": f"當日外資 {round(f)}張、投信 {round(tr)}張",
                "main_force": {"level": level, "reason": reason},
                "stats": {
                    "foreign_buy_days":  1 if f  > 0 else 0,
                    "foreign_sell_days": 1 if f  < 0 else 0,
                    "trust_buy_days":    1 if tr > 0 else 0,
                    "trust_sell_days":   1 if tr < 0 else 0,
                },
            }
    except Exception:
        pass
    return {
        "chips": [],
        "conclusion": "無籌碼資料",
        "main_force": {"level": "watch", "reason": "無資料"},
        "stats": {"foreign_buy_days": 0, "foreign_sell_days": 0,
                  "trust_buy_days": 0, "trust_sell_days": 0},
    }


def _get_fundamental_for_ticker(ticker: str, last_price: Optional[float] = None) -> dict:
    try:
        rows = requests.get(f"{TWSE}/exchangeReport/BWIBBU_d", timeout=8).json()
        row = next((r for r in rows if r.get("Code") == ticker), None)
        if not row:
            return {}
        def to_float(k):
            try: return float(row[k].replace(",", ""))
            except: return None
        pe = to_float("PEratio")
        eps = round(last_price / pe, 2) if (pe and pe > 0 and last_price) else None
        return {
            "pe":            pe,
            "pb":            to_float("PBratio"),
            "dividendYield": to_float("DividendYield"),
            "eps":           eps,
            "revenue_yoy":   None,
        }
    except Exception:
        return {}


@app.post("/qianshao/analyse")
def analyse_strategy(body: dict):
    strategy_id = body.get("strategy_id")
    ticker      = str(body.get("ticker", "")).strip().upper()
    if not strategy_id or not ticker:
        raise HTTPException(status_code=400, detail="缺少 strategy_id 或 ticker")

    strategies = _load_json(STRATEGIES_FILE)
    strategy   = next((s for s in strategies if s.get("id") == strategy_id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    kbars = active.get_kbars(ticker, days=120)
    if not kbars or len(kbars) < 20:
        kbars = _twse_kbars(ticker, 120)
    if not kbars or len(kbars) < 20:
        raise HTTPException(status_code=503, detail="K 棒資料不足，至少需 20 根日K")

    last_price  = float(kbars[-1].get("Close") or 0) or None
    fundamental = _get_fundamental_for_ticker(ticker, last_price=last_price)
    chips_data  = _build_chip_data_from_existing(ticker)

    try:
        result = strategy_engine.analyse(strategy, ticker, kbars,
                                         fundamental=fundamental, chips_data=chips_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失敗：{e}")

    record = {
        "id":            str(uuid.uuid4()),
        "strategy_id":   strategy_id,
        "strategy_name": strategy.get("name"),
        "ticker":        ticker,
        "stock_name":    _get_stock_name(ticker),
        "analyzed_at":   _now_iso(),
        "result":        result,
    }
    history = _load_json(HISTORY_FILE)
    history.append(record)
    if len(history) > 500:
        history = history[-500:]
    _save_json(HISTORY_FILE, history)
    return record


@app.get("/qianshao/backtest")
def qianshao_backtest(ticker: str, strategy_id: str, hold_days: int = 5):
    strategies = _load_json(STRATEGIES_FILE)
    strategy   = next((s for s in strategies if s.get("id") == strategy_id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    kbars = _twse_kbars(ticker.upper(), 90)
    if len(kbars) < 30:
        raise HTTPException(status_code=400, detail="歷史資料不足（需 30 根日K）")

    tech_conds = [
        c for c in ((strategy.get("conditions") or {}).get("technical") or [])
        if c.get("enabled", True)
    ]
    if not tech_conds:
        raise HTTPException(status_code=400, detail="此策略沒有啟用的技術面條件")

    signal_indices: list[int] = []
    trades: list[dict] = []

    for i in range(26, len(kbars)):
        try:
            tech = strategy_engine.calc_technical(kbars[: i + 1])
        except Exception:
            continue
        ind = tech["indicators"]
        ctx = {
            "ma5": ind["ma5"], "ma10": ind["ma10"],
            "ma20": ind["ma20"], "ma60": ind["ma60"],
            "k": ind["k"], "d": ind["d"], "j": ind["j"],
            "rsi": ind["rsi"],
            "ma_alignment": ind["ma_align_code"],
            "trend":        ind["trend_code"],
            "kd_cross":     ind["kd_cross"],
            "macd_status":  ind["macd_status"],
            "dif": ind["dif"], "dea": ind["dea"], "hist": ind["hist"],
        }
        if not all(strategy_engine._eval_condition(c, ctx) is True for c in tech_conds):
            continue

        exit_idx   = min(i + hold_days, len(kbars) - 1)
        entry_px   = kbars[i]["Close"]
        exit_px    = kbars[exit_idx]["Close"]
        ret        = round((exit_px - entry_px) / entry_px * 100, 2) if entry_px else 0
        signal_indices.append(i)
        trades.append({
            "date":       kbars[i]["ts"],
            "entry":      entry_px,
            "exit_date":  kbars[exit_idx]["ts"],
            "exit":       exit_px,
            "return_pct": ret,
            "win":        ret > 0,
        })

    total = len(trades)
    wins  = sum(1 for t in trades if t["win"])
    return {
        "kbars":          kbars,
        "signal_indices": signal_indices,
        "trades":         trades,
        "stats": {
            "total":      total,
            "wins":       wins,
            "win_rate":   round(wins / total * 100) if total > 0 else 0,
            "avg_return": round(sum(t["return_pct"] for t in trades) / total, 2) if total > 0 else 0,
        },
    }


@app.get("/qianshao/analysis/history")
def list_analysis_history(ticker: str = "", strategy_id: str = "", days: int = 30):
    history = _load_json(HISTORY_FILE)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    out = []
    for r in history:
        if r.get("analyzed_at", "") < cutoff:
            continue
        if ticker and r.get("ticker") != ticker.upper():
            continue
        if strategy_id and r.get("strategy_id") != strategy_id:
            continue
        result = r.get("result", {}) or {}
        out.append({
            "id":            r.get("id"),
            "strategy_id":   r.get("strategy_id"),
            "strategy_name": r.get("strategy_name"),
            "ticker":        r.get("ticker"),
            "stock_name":    r.get("stock_name"),
            "analyzed_at":   r.get("analyzed_at"),
            "win_rate":      result.get("win_rate"),
            "trend":         result.get("indicators", {}).get("trend_code"),
            "main_force":    result.get("main_force_signal", {}).get("level"),
            "suggestion":    result.get("suggestion", {}).get("strategy"),
        })
    out.sort(key=lambda x: x.get("analyzed_at", ""), reverse=True)
    return out


@app.get("/qianshao/analysis/{record_id}")
def get_analysis_record(record_id: str):
    history = _load_json(HISTORY_FILE)
    record = next((r for r in history if r.get("id") == record_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="紀錄不存在")
    return record


@app.delete("/qianshao/analysis/{record_id}")
def delete_analysis_record(record_id: str):
    history = _load_json(HISTORY_FILE)
    new_list = [r for r in history if r.get("id") != record_id]
    if len(new_list) == len(history):
        raise HTTPException(status_code=404, detail="紀錄不存在")
    _save_json(HISTORY_FILE, new_list)
    return {"status": "deleted", "id": record_id}


def _build_market_candidates(limit: int = 0) -> list:
    """取得全市場 (ticker, name) 清單 — 用 _stock_names 快取"""
    _get_stock_name("0000")  # 觸發 _stock_names 載入
    items = [(t, n) for t, n in _stock_names.items() if t.isdigit() and len(t) == 4]
    items.sort()
    return items[:limit] if limit > 0 else items


def _build_fundamental_map() -> dict:
    """一次取所有股票 PE/PB/殖利率（BWIBBU_d）"""
    try:
        rows = requests.get(f"{TWSE}/exchangeReport/BWIBBU_d", timeout=10).json()
    except Exception:
        return {}
    fmap = {}
    for r in rows:
        code = r.get("Code")
        if not code:
            continue
        def to_float(k):
            try: return float(r[k].replace(",", ""))
            except: return None
        fmap[code] = {
            "pe":            to_float("PEratio"),
            "pb":            to_float("PBratio"),
            "dividendYield": to_float("DividendYield"),
        }
    return fmap


@app.post("/qianshao/screen")
def run_screen(body: dict):
    strategy_id = body.get("strategy_id")
    max_scan    = int(body.get("max_full_scan", 60))
    if not strategy_id:
        raise HTTPException(status_code=400, detail="缺少 strategy_id")
    strategies = _load_json(STRATEGIES_FILE)
    strategy = next((s for s in strategies if s.get("id") == strategy_id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    candidates       = _build_market_candidates()
    fundamental_map  = _build_fundamental_map()

    def kbars_fn(t):
        return active.get_kbars(t, days=120) or _twse_kbars(t, 120)

    result = strategy_engine.screen(
        strategy, candidates, kbars_fn, fundamental_map,
        chips_fn=None,  # 全市場不爬 5 日籌碼，提速；命中股可在 /qianshao/analyse 補
        max_full_scan=max_scan,
    )

    record = {
        "id":            str(uuid.uuid4()),
        "strategy_id":   strategy_id,
        "strategy_name": strategy.get("name"),
        "screened_at":   _now_iso(),
        **result,
    }
    history = _load_json(SCREEN_HIST_FILE)
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    history = [h for h in history if h.get("screened_at", "") >= cutoff]
    history.append(record)
    _save_json(SCREEN_HIST_FILE, history)
    return record


@app.get("/qianshao/screen/history")
def list_screen_history(strategy_id: str = "", days: int = 7):
    history = _load_json(SCREEN_HIST_FILE)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    out = []
    for r in history:
        if r.get("screened_at", "") < cutoff:
            continue
        if strategy_id and r.get("strategy_id") != strategy_id:
            continue
        out.append({
            "id":            r.get("id"),
            "strategy_id":   r.get("strategy_id"),
            "strategy_name": r.get("strategy_name"),
            "screened_at":   r.get("screened_at"),
            "scan_count":    r.get("scan_count"),
            "match_count":   r.get("match_count"),
            "elapsed_sec":   r.get("elapsed_sec"),
        })
    out.sort(key=lambda x: x.get("screened_at", ""), reverse=True)
    return out


@app.get("/qianshao/screen/{record_id}")
def get_screen_record(record_id: str):
    history = _load_json(SCREEN_HIST_FILE)
    record = next((r for r in history if r.get("id") == record_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="紀錄不存在")
    return record


@app.delete("/qianshao/screen/{record_id}")
def delete_screen_record(record_id: str):
    history = _load_json(SCREEN_HIST_FILE)
    new_list = [r for r in history if r.get("id") != record_id]
    if len(new_list) == len(history):
        raise HTTPException(status_code=404, detail="紀錄不存在")
    _save_json(SCREEN_HIST_FILE, new_list)
    return {"status": "deleted", "id": record_id}


@app.get("/qianshao/screen/{record_id}/export.csv")
def export_screen_csv(record_id: str):
    from fastapi.responses import Response
    from urllib.parse import quote
    import io
    history = _load_json(SCREEN_HIST_FILE)
    record = next((r for r in history if r.get("id") == record_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="紀錄不存在")
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["代碼","名稱","收盤價","漲跌%","成交量","均線","KD K","MACD","外資","投信","勝率%","燈號"])
    for s in record.get("stocks", []):
        w.writerow([
            s.get("ticker",""), s.get("name",""), s.get("close",""), s.get("change_pct",""),
            s.get("volume",""), s.get("ma_status",""), s.get("kd_k",""), s.get("macd_status",""),
            s.get("foreign_net",""), s.get("trust_net",""), s.get("win_rate",""), s.get("signal",""),
        ])
    csv_bytes = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM for Excel
    fname = f"選股_{record.get('strategy_name','strategy')}_{(record.get('screened_at') or '')[:10]}.csv"
    fname_ascii = fname.encode("ascii", "ignore").decode() or "screen.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{fname_ascii}"; filename*=UTF-8\'\'{quote(fname)}',
    }
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8", headers=headers)


@app.get("/qianshao/analysis/{record_id}/report.html")
def get_analysis_report(record_id: str):
    from fastapi.responses import HTMLResponse
    from urllib.parse import quote
    history = _load_json(HISTORY_FILE)
    record = next((r for r in history if r.get("id") == record_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="紀錄不存在")
    html_str = report_generator.render(record)
    fname = f"{record.get('ticker')}_{record.get('strategy_name','strategy')}_{(record.get('analyzed_at') or '')[:10]}.html"
    fname_ascii = fname.encode("ascii", "ignore").decode() or "report.html"
    headers = {
        "Content-Disposition": f'attachment; filename="{fname_ascii}"; filename*=UTF-8\'\'{quote(fname)}'
    }
    return HTMLResponse(content=html_str, headers=headers)


@app.get("/quote/{ticker}")
def get_quote(ticker: str):
    return active.get_quote(ticker)


@app.get("/kbars/{ticker}")
def get_kbars(ticker: str, days: int = 60):
    return active.get_kbars(ticker, days)


@app.get("/technical/{ticker}")
def get_technical(ticker: str):
    return active.get_technical(ticker)


@app.get("/xq/watchlists")
def xq_watchlists():
    xq = _providers["xq"]
    if not xq.is_healthy():
        raise HTTPException(status_code=503, detail="XQ 未連線")
    try:
        r = requests.get(f"{xq.base}/watchlists", timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="XQ 未連線（COM 未就緒，請在 Windows 桌面手動開啟 XQ 軟體）")


@app.get("/xq/watchlist")
def xq_watchlist(group: str):
    xq = _providers["xq"]
    if not xq.is_healthy():
        raise HTTPException(status_code=503, detail="XQ 未連線")
    try:
        return requests.get(f"{xq.base}/watchlist", params={"group": group}, timeout=8).json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/start-xq")
def start_xq():
    import subprocess, threading
    PRLCTL = "/usr/local/bin/prlctl"
    vm = "dcf8c674-794d-426f-95d9-8d397f211a64"

    status_r = subprocess.run([PRLCTL, "status", vm], capture_output=True, text=True, timeout=10)
    vm_stopped = "stopped" in status_r.stdout.lower()

    if not vm_stopped:
        check = subprocess.run(
            [PRLCTL, "exec", vm, "powershell", "-Command",
             "(Get-Process daqxqlite -ErrorAction SilentlyContinue) -ne $null"],
            capture_output=True, text=True, timeout=10,
        )
        if "True" in check.stdout:
            return {"status": "already_running"}
        subprocess.Popen([PRLCTL, "exec", vm, "cmd", "/c", "schtasks /Run /TN StartXQ"])
        return {"status": "starting"}

    def _boot_and_start():
        subprocess.run([PRLCTL, "start", vm], timeout=120)
        import time; time.sleep(20)
        subprocess.Popen([PRLCTL, "exec", vm, "cmd", "/c", "schtasks /Run /TN StartXQ"])
        time.sleep(10)
        subprocess.Popen([
            PRLCTL, "exec", vm, "cmd", "/c",
            r"cd /d C:\Balian\xq_bridge && start /B C:\Users\balianwang\miniconda3\python.exe server.py",
        ])

    threading.Thread(target=_boot_and_start, daemon=True).start()
    return {"status": "starting_vm"}


@app.post("/restart-xq")
def restart_xq():
    import subprocess
    PRLCTL = "/usr/local/bin/prlctl"
    vm = "dcf8c674-794d-426f-95d9-8d397f211a64"
    kill_cmd = (
        "for /f \"tokens=5\" %p in "
        "('netstat -ano ^| findstr :8000.*LISTENING') "
        "do taskkill /F /PID %p"
    )
    subprocess.run([PRLCTL, "exec", vm, "cmd", "/c", kill_cmd], capture_output=True, timeout=10)
    subprocess.Popen([
        PRLCTL, "exec", vm, "cmd", "/c",
        r"cd /d C:\Balian\xq_bridge && start /B C:\Users\balianwang\miniconda3\python.exe server.py",
    ])
    return {"status": "restarting"}


if __name__ == "__main__":
    import uvicorn
    print(f"  資料來源：{active.name}  ({active.base if hasattr(active, 'base') else '—'})")
    print(f"  XQ 連線：{'OK' if _providers['xq'].is_healthy() else '離線'}")
    uvicorn.run("stock_server:app", host="0.0.0.0", port=8000, reload=True)
