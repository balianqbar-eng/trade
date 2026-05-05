import os
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

SIGNAL_LOG  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals.csv")
SMART_LOG   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_orders.csv")
MONITOR_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_log.csv")

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
        elif cur_pos is None and sig in ("LONG", "SHORT"):
            action = "buy" if sig == "LONG" else "sell"
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


@app.get("/fundamental/{ticker}")
def get_fundamental(ticker: str):
    try:
        rows = requests.get(f"{TWSE}/exchangeReport/BWIBBU_d", timeout=8).json()
        row = next((r for r in rows if r.get("Code") == ticker), None)
        if not row:
            return {"pe": None, "pb": None, "dividendYield": None}
        def to_float(k):
            try: return float(row[k].replace(",", ""))
            except: return None
        return {"pe": to_float("PEratio"), "pb": to_float("PBratio"), "dividendYield": to_float("DividendYield")}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/chip/{ticker}")
def get_chip(ticker: str):
    try:
        rows = requests.get(f"{TWSE}/fund/T86", timeout=10).json()
        row = next((r for r in rows if r.get("Code") == ticker), None)
        if not row:
            return {"foreignNet": 0, "investTrustNet": 0, "dealerNet": 0, "total": 0}
        def parse(k):
            try: return float(row[k].replace(",", ""))
            except: return 0.0
        f = parse("外陸資買賣超股數(千股)")
        tr = parse("投信買賣超股數(千股)")
        d = parse("自營商買賣超股數(千股)")
        return {"foreignNet": f, "investTrustNet": tr, "dealerNet": d, "total": f + tr + d}
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
            return {"total_lots": 0, "big_trades": 0, "last_ts": None}
        df["lots"] = df["volume"] // 1000
        big = df[df["lots"] >= lot_min]
        return {
            "total_lots": int(big["lots"].sum()),
            "big_trades": int(len(big)),
            "last_ts": str(big["ts"].iloc[-1]) if len(big) else None,
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
        return requests.get(f"{xq.base}/watchlists", timeout=8).json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/xq/watchlist")
def xq_watchlist(group: str):
    xq = _providers["xq"]
    if not xq.is_healthy():
        raise HTTPException(status_code=503, detail="XQ 未連線")
    try:
        return requests.get(f"{xq.base}/watchlist", params={"group": group}, timeout=8).json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    print(f"  資料來源：{active.name}  ({active.base if hasattr(active, 'base') else '—'})")
    print(f"  XQ 連線：{'OK' if _providers['xq'].is_healthy() else '離線'}")
    uvicorn.run("stock_server:app", host="0.0.0.0", port=8000, reload=True)
