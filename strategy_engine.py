"""錢哨策略分析引擎

提供：
- 技術面計算（MA / KD / MACD / RSI / 布林）
- 籌碼面計算（三大法人連買連賣、主力燈號）
- 關鍵價位（壓力 / 支撐 / 回檔 / 停損）
- 勝率計算（根據策略條件命中率）
- 操作建議產生
"""

import math
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests


# ── 共用 ──────────────────────────────────────────────────────────────────────

def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return None


# ── 技術面計算 ────────────────────────────────────────────────────────────────

def _kd_series(df: pd.DataFrame, n: int = 9, m: int = 3):
    lo = df["Low"].rolling(n, min_periods=1).min()
    hi = df["High"].rolling(n, min_periods=1).max()
    span = (hi - lo).replace(0, 1)
    rsv = (df["Close"] - lo) / span * 100
    K = rsv.ewm(alpha=1 / m, adjust=False).mean()
    D = K.ewm(alpha=1 / m, adjust=False).mean()
    J = 3 * K - 2 * D
    return K, D, J


def _macd_series(df: pd.DataFrame, fast: int = 12, slow: int = 26, sig: int = 9):
    ef = df["Close"].ewm(span=fast, adjust=False).mean()
    es = df["Close"].ewm(span=slow, adjust=False).mean()
    dif = ef - es
    dea = dif.ewm(span=sig, adjust=False).mean()
    return dif, dea, dif - dea


def _rsi(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, 1e-9)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _bbands(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    return mid, mid + k * std, mid - k * std


def calc_technical(kbars: list) -> dict:
    """完整技術面計算，回傳分析摘要 + 指標數值 + 表格列"""
    df = pd.DataFrame(kbars)
    if len(df) < 20:
        raise ValueError("K 棒資料不足，需 >= 20 根")

    close = df["Close"]
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    # MA
    ma5  = float(close.tail(5).mean())
    ma10 = float(close.tail(10).mean())
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean()) if len(close) >= 60 else ma20

    bull_ma  = ma5 > ma10 > ma20
    bear_ma  = ma5 < ma10 < ma20
    ma_align = "多頭排列 (5>10>20)" if bull_ma else ("空頭排列 (5<10<20)" if bear_ma else "糾結整理")

    # KD
    K, D, J = _kd_series(df)
    k0, k1 = float(K.iloc[-1]), float(K.iloc[-2])
    d0, d1 = float(D.iloc[-1]), float(D.iloc[-2])
    j0     = float(J.iloc[-1])
    kd_golden = k1 < d1 and k0 >= d0
    kd_death  = k1 > d1 and k0 <= d0
    kd_state  = "金叉" if kd_golden else ("死叉" if kd_death else ("多頭" if k0 > d0 else "空頭"))

    # MACD
    dif, dea, hist = _macd_series(df)
    dif0, dea0     = float(dif.iloc[-1]), float(dea.iloc[-1])
    hist0, hist1   = float(hist.iloc[-1]), float(hist.iloc[-2])
    macd_bull = dif0 > dea0
    if hist0 > 0 and hist0 > hist1:
        macd_state = "紅柱擴大"
    elif hist0 > 0:
        macd_state = "紅柱縮小"
    elif hist0 < 0 and hist0 > hist1:
        macd_state = "綠柱縮小"
    else:
        macd_state = "綠柱擴大"

    # RSI
    rsi = _rsi(close)

    # 布林
    mid, up, lo = _bbands(close)
    mid0, up0, lo0 = float(mid.iloc[-1]), float(up.iloc[-1]), float(lo.iloc[-1])
    if last >= up0 * 0.98:
        bb_pos = "接近上軌"
    elif last > mid0:
        bb_pos = "站上中軌"
    elif last <= lo0 * 1.02:
        bb_pos = "下軌附近"
    else:
        bb_pos = "中軌下方"
    bb_width_now  = float(up.iloc[-1] - lo.iloc[-1])
    bb_width_prev = float(up.iloc[-5] - lo.iloc[-5]) if len(up) >= 5 else bb_width_now
    bb_state = "開口擴大" if bb_width_now > bb_width_prev else "開口縮小"

    # 趨勢
    if bull_ma and macd_bull and k0 > d0:
        trend = "多頭"
        trend_desc = "多頭向上"
    elif bear_ma and not macd_bull and k0 < d0:
        trend = "空頭"
        trend_desc = "空頭向下"
    else:
        trend = "盤整"
        trend_desc = "震盪整理"

    # 量價
    vol = df["Volume"].astype(float)
    vol_now = float(vol.iloc[-1])
    vol_ma5 = float(vol.tail(5).mean()) if len(vol) >= 5 else vol_now
    price_chg = last - prev
    if vol_now > vol_ma5 * 1.5 and price_chg > 0:
        volume_price = "量增價漲，健康多頭"
    elif vol_now > vol_ma5 * 1.5 and price_chg < 0:
        volume_price = "量增價跌，出貨疑慮"
    elif vol_now < vol_ma5 * 0.8 and price_chg > 0:
        volume_price = "量縮價漲，動能不足"
    elif vol_now < vol_ma5 * 0.8 and price_chg < 0:
        volume_price = "量縮價跌，洗盤訊號"
    else:
        volume_price = "量價平淡"

    # 價格位置
    high_120 = float(df["High"].tail(120).max())
    low_120  = float(df["Low"].tail(120).min())
    if high_120 > low_120:
        pct = (last - low_120) / (high_120 - low_120)
        if pct >= 0.7:
            price_position = "高檔 / 接近上軌"
        elif pct >= 0.4:
            price_position = "中檔"
        else:
            price_position = "低檔"
    else:
        price_position = "—"

    overall = "多頭格局未變" if trend == "多頭" else ("空頭格局未變" if trend == "空頭" else "盤整觀望")

    summary = {
        "trend":              trend,
        "trend_desc":         trend_desc,
        "price_position":     price_position,
        "ma_alignment":       ma_align,
        "volume_price":       volume_price,
        "bollinger_position": bb_pos,
        "bollinger_state":    bb_state,
        "overall":            overall,
    }

    ma_align_code = "bull" if bull_ma else ("bear" if bear_ma else "none")
    trend_code    = "bull" if trend == "多頭" else ("bear" if trend == "空頭" else "range")
    kd_cross      = "golden" if kd_golden else ("death" if kd_death else "none")
    macd_status   = "red_bar" if hist0 > 0 else ("green_bar" if hist0 < 0 else "neutral")

    indicators = {
        "last":           round(last, 2),
        "prev":           round(prev, 2),
        "change_pct":     round((last - prev) / prev * 100, 2) if prev > 0 else 0,
        "ma5":            round(ma5, 2),
        "ma10":           round(ma10, 2),
        "ma20":           round(ma20, 2),
        "ma60":           round(ma60, 2),
        "k":              round(k0, 2),
        "d":              round(d0, 2),
        "j":              round(j0, 2),
        "kd_state":       kd_state,
        "kd_cross":       kd_cross,
        "ma_align_code":  ma_align_code,
        "trend_code":     trend_code,
        "macd_status":    macd_status,
        "dif":            round(dif0, 4),
        "dea":            round(dea0, 4),
        "hist":           round(hist0, 4),
        "macd_bull":      macd_bull,
        "macd_state":     macd_state,
        "rsi":            round(rsi, 2),
        "bb_mid":         round(mid0, 2),
        "bb_up":           round(up0, 2),
        "bb_lo":           round(lo0, 2),
        "high_120":       round(high_120, 2),
        "low_120":        round(low_120, 2),
        "vol_now":        int(vol_now),
        "vol_ma5":        int(vol_ma5),
    }

    indicators_table = [
        {"name": "KD (9,3)", "trend": "bull" if k0 > d0 else "bear",
         "desc": f"K {'>' if k0 > d0 else '<'} D，K 值 {k0:.0f}"},
        {"name": "MACD",     "trend": "bull" if macd_bull else "bear",
         "desc": f"DIF {'>' if macd_bull else '<'} DEA，{macd_state}"},
        {"name": "均線排列", "trend": "bull" if bull_ma else ("bear" if bear_ma else "neutral"),
         "desc": ma_align},
        {"name": "布林通道", "trend": "bull" if last > mid0 else "bear",
         "desc": f"{bb_state}，{bb_pos}"},
        {"name": "成交量",   "trend": "bull" if vol_now > vol_ma5 * 1.2 else "neutral",
         "desc": "量增" if vol_now > vol_ma5 * 1.2 else ("量縮" if vol_now < vol_ma5 * 0.8 else "持平")},
        {"name": "RSI (14)", "trend": "neutral" if 30 <= rsi <= 70 else ("bull" if rsi > 70 else "bear"),
         "desc": f"{rsi:.1f}，{'超買' if rsi > 70 else ('超賣' if rsi < 30 else '未超買超賣')}"},
    ]

    return {
        "summary":          summary,
        "indicators":       indicators,
        "indicators_table": indicators_table,
    }


# ── 籌碼面計算 ────────────────────────────────────────────────────────────────

TWSE_T86 = "https://www.twse.com.tw/rwd/zh/fund/T86"

_chip_cache: dict = {}


def _fetch_chip_for_date(date_str: str, ticker: str) -> Optional[dict]:
    """date_str format: YYYYMMDD。回傳該日該股三大法人買賣超（千股 → 張）"""
    cache_key = f"{date_str}|{ticker}"
    if cache_key in _chip_cache:
        return _chip_cache[cache_key]
    try:
        r = requests.get(
            TWSE_T86,
            params={"date": date_str, "selectType": "ALL", "response": "json"},
            timeout=10,
        )
        data = r.json()
        if data.get("stat") != "OK":
            _chip_cache[cache_key] = None
            return None
        fields = data.get("fields", [])
        rows   = data.get("data", [])
        idx_code = next((i for i, f in enumerate(fields) if "證券代號" in f), 0)

        def find_idx(name_part: str) -> int:
            for i, f in enumerate(fields):
                if name_part in f and "買賣超" in f:
                    return i
            return -1

        idx_foreign = find_idx("外陸資")
        if idx_foreign < 0:
            idx_foreign = find_idx("外資")
        idx_trust   = find_idx("投信")
        idx_dealer  = find_idx("自營商")

        for row in rows:
            if str(row[idx_code]).strip() == ticker:
                def parse(idx: int) -> float:
                    if idx < 0:
                        return 0.0
                    try:
                        return float(str(row[idx]).replace(",", ""))
                    except Exception:
                        return 0.0
                result = {
                    "date":             date_str,
                    "foreign":          parse(idx_foreign) / 1000,
                    "investment_trust": parse(idx_trust)   / 1000,
                    "dealer":           parse(idx_dealer)  / 1000,
                }
                result["total"] = result["foreign"] + result["investment_trust"] + result["dealer"]
                _chip_cache[cache_key] = result
                return result
        _chip_cache[cache_key] = None
        return None
    except Exception:
        return None


def calc_chips(ticker: str, lookback_days: int = 7) -> dict:
    """近 N 個交易日三大法人買賣超分析"""
    chips: list = []
    today = datetime.today()
    for delta in range(lookback_days * 3):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        result = _fetch_chip_for_date(d.strftime("%Y%m%d"), ticker)
        if result:
            chips.append({
                "date":    d.strftime("%m/%d"),
                "foreign": round(result["foreign"]),
                "trust":   round(result["investment_trust"]),
                "dealer":  round(result["dealer"]),
                "total":   round(result["total"]),
            })
        if len(chips) >= 5:
            break

    chips.reverse()  # 早 → 晚

    def consecutive(values: list, positive: bool = True) -> int:
        count = 0
        for v in reversed(values):
            if (v > 0 and positive) or (v < 0 and not positive):
                count += 1
            else:
                break
        return count

    foreign_vals = [c["foreign"] for c in chips]
    trust_vals   = [c["trust"] for c in chips]
    foreign_buy_days  = consecutive(foreign_vals, True)
    foreign_sell_days = consecutive(foreign_vals, False)
    trust_buy_days    = consecutive(trust_vals, True)
    trust_sell_days   = consecutive(trust_vals, False)

    total_recent = sum(c["total"] for c in chips[-3:]) if chips else 0
    if foreign_buy_days >= 3 and total_recent > 0:
        signal_level  = "safe"
        signal_reason = "法人主力同步做多，結構偏多。"
    elif foreign_sell_days >= 3 and total_recent < 0:
        signal_level  = "danger"
        signal_reason = "法人主力同步賣超，結構轉弱。"
    elif total_recent > 0:
        signal_level  = "watch"
        signal_reason = "法人偏多但連續性不足。"
    else:
        signal_level  = "watch"
        signal_reason = "法人態度分歧，宜觀望。"

    if not chips:
        conclusion = "無籌碼資料"
    elif foreign_buy_days >= 3:
        conclusion = f"外資連買 {foreign_buy_days} 日，法人偏多。"
    elif foreign_sell_days >= 3:
        conclusion = f"外資連賣 {foreign_sell_days} 日，法人偏空。"
    elif chips[-1]["foreign"] > 100:
        conclusion = "外資大幅買超，法人同向做多。"
    elif chips[-1]["foreign"] < -100:
        conclusion = "外資大幅賣超，法人轉空。"
    else:
        conclusion = "法人買賣平淡。"

    return {
        "chips":      chips,
        "conclusion": conclusion,
        "main_force": {"level": signal_level, "reason": signal_reason},
        "stats": {
            "foreign_buy_days":  foreign_buy_days,
            "foreign_sell_days": foreign_sell_days,
            "trust_buy_days":    trust_buy_days,
            "trust_sell_days":   trust_sell_days,
        },
    }


# ── 型態分析 ──────────────────────────────────────────────────────────────────

def _is_doji(o: float, h: float, l: float, c: float) -> bool:
    rng = h - l
    if rng <= 0:
        return False
    return abs(c - o) / rng < 0.1


def _is_long_lower_shadow(o: float, h: float, l: float, c: float) -> bool:
    rng = h - l
    if rng <= 0:
        return False
    body_lo = min(o, c)
    return (body_lo - l) / rng > 0.6


def _detect_k_signals(df: pd.DataFrame) -> list:
    """近 5 根 K 棒中辨識常見型態，回傳字串陣列"""
    signals: list = []
    n = len(df)
    if n < 3:
        return signals

    rows = df.tail(5).reset_index(drop=True)
    last = len(rows) - 1
    o, h, l, c = rows["Open"], rows["High"], rows["Low"], rows["Close"]
    last_date = str(rows.iloc[-1].get("ts", ""))[5:10] if "ts" in rows else ""
    suffix = f" {last_date}" if last_date else ""

    if n >= 3:
        last3 = df.tail(3).reset_index(drop=True)
        o3, h3, l3, c3 = last3["Open"], last3["High"], last3["Low"], last3["Close"]
        if all(c3[i] > o3[i] for i in range(3)) \
           and c3[1] > c3[0] and c3[2] > c3[1] \
           and h3[1] > h3[0] and h3[2] > h3[1]:
            signals.append(f"紅三兵{suffix}")
        if all(c3[i] < o3[i] for i in range(3)) \
           and c3[1] < c3[0] and c3[2] < c3[1] \
           and l3[1] < l3[0] and l3[2] < l3[1]:
            signals.append(f"三隻烏鴉{suffix}")

    if _is_doji(o[last], h[last], l[last], c[last]):
        signals.append(f"十字線{suffix}")

    if _is_long_lower_shadow(o[last], h[last], l[last], c[last]):
        signals.append(f"長下影線{suffix}")

    if last >= 2:
        i, j, k = last - 2, last - 1, last
        body_i = abs(c[i] - o[i])
        body_j = abs(c[j] - o[j])
        rng_i  = h[i] - l[i]
        if body_i > rng_i * 0.5 and body_j < rng_i * 0.3:
            mid_i = (o[i] + c[i]) / 2
            if c[i] < o[i] and c[k] > o[k] and c[k] > mid_i:
                signals.append(f"晨星{suffix}")
            elif c[i] > o[i] and c[k] < o[k] and c[k] < mid_i:
                signals.append(f"夜星{suffix}")

    return signals


def _detect_w_bottom(df: pd.DataFrame, lookback: int = 60) -> str:
    """回傳 formed / forming / none / insufficient"""
    if len(df) < 20:
        return "insufficient"
    sub = df.tail(lookback).reset_index(drop=True)
    lows = sub["Low"]
    mid = len(sub) // 2
    p1_idx = lows[:mid].idxmin()
    p2_idx = lows[mid:].idxmin()
    p1 = float(lows[p1_idx])
    p2 = float(lows[p2_idx])
    if p1_idx + 1 >= p2_idx:
        return "none"
    middle_high = float(sub["High"][p1_idx:p2_idx].max())
    rebound = (middle_high - p1) / p1 if p1 > 0 else 0
    if rebound < 0.03:
        return "none"
    if abs(p2 - p1) / p1 > 0.05:
        return "none"
    last_close = float(sub["Close"].iloc[-1])
    if last_close > middle_high:
        return "formed"
    if last_close > p2 * 1.02:
        return "forming"
    return "none"


def _detect_m_top(df: pd.DataFrame, lookback: int = 60) -> str:
    if len(df) < 20:
        return "insufficient"
    sub = df.tail(lookback).reset_index(drop=True)
    highs = sub["High"]
    mid = len(sub) // 2
    p1_idx = highs[:mid].idxmax()
    p2_idx = highs[mid:].idxmax()
    p1 = float(highs[p1_idx])
    p2 = float(highs[p2_idx])
    if p1_idx + 1 >= p2_idx:
        return "none"
    middle_low = float(sub["Low"][p1_idx:p2_idx].min())
    drop = (p1 - middle_low) / p1 if p1 > 0 else 0
    if drop < 0.03:
        return "none"
    if abs(p2 - p1) / p1 > 0.05:
        return "none"
    last_close = float(sub["Close"].iloc[-1])
    if last_close < middle_low:
        return "formed"
    if last_close < p2 * 0.98:
        return "forming"
    return "none"


def calc_pattern(kbars: list) -> dict:
    df = pd.DataFrame(kbars)
    if len(df) < 10:
        return {"w_bottom": "insufficient", "m_top": "insufficient", "k_signals": []}
    return {
        "w_bottom":  _detect_w_bottom(df),
        "m_top":     _detect_m_top(df),
        "k_signals": _detect_k_signals(df),
    }


# ── 量價分析 ──────────────────────────────────────────────────────────────────

def calc_volume_price(kbars: list, indicators: dict) -> dict:
    df = pd.DataFrame(kbars)
    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else last
    vol_now = float(df["Volume"].iloc[-1])
    vol_ma5 = float(df["Volume"].tail(5).mean()) if len(df) >= 5 else vol_now
    volume_ratio = round(vol_now / vol_ma5, 2) if vol_ma5 > 0 else 0
    ma20 = indicators.get("ma20", last)
    bias_ma20 = round((last - ma20) / ma20 * 100, 2) if ma20 > 0 else 0
    price_chg_pct = round((last - prev) / prev * 100, 2) if prev > 0 else 0

    if vol_now > vol_ma5 * 2:
        vol_state = "爆量"
    elif vol_now > vol_ma5 * 1.5 and price_chg_pct > 0:
        vol_state = "量增價漲"
    elif vol_now > vol_ma5 * 1.5 and price_chg_pct < 0:
        vol_state = "量增價跌"
    elif vol_now < vol_ma5 * 0.8 and abs(price_chg_pct) < 0.5:
        vol_state = "量縮價穩"
    elif vol_now < vol_ma5 * 0.8:
        vol_state = "量縮"
    else:
        vol_state = "持平"

    return {
        "volume_ratio": volume_ratio,
        "bias_ma20":    bias_ma20,
        "vol_state":    vol_state,
        "price_chg_pct": price_chg_pct,
    }


# ── 關鍵價位 ──────────────────────────────────────────────────────────────────

def calc_key_prices(kbars: list, indicators: dict) -> dict:
    df = pd.DataFrame(kbars)
    if len(df) < 20:
        raise ValueError("K 棒資料不足")

    last    = float(df["Close"].iloc[-1])
    high_20 = float(df["High"].tail(20).max())
    low_20  = float(df["Low"].tail(20).min())
    high_60 = float(df["High"].tail(60).max()) if len(df) >= 60 else high_20
    low_60  = float(df["Low"].tail(60).min()) if len(df) >= 60 else low_20

    ma20 = indicators.get("ma20", last)
    ma60 = indicators.get("ma60", ma20)

    pressure_lo = round(min(high_20, last * 1.04), 2)
    pressure_hi = round(max(high_20, high_60 * 0.99) if high_60 > high_20 else high_20 * 1.05, 2)
    if pressure_lo > pressure_hi:
        pressure_lo, pressure_hi = pressure_hi, pressure_lo

    support_lo = round(min(low_60, ma60 * 0.97), 2)
    support_hi = round(max(min(ma20, low_20 * 1.02), support_lo + 0.01), 2)

    pullback_hi = round(min(last * 0.99, pressure_lo * 0.97), 2)
    pullback_lo = round(min(ma20, last * 0.96), 2)
    if pullback_lo > pullback_hi:
        pullback_lo, pullback_hi = pullback_hi, pullback_lo

    return {
        "pressure":     f"{pressure_lo} ~ {pressure_hi}",
        "pullback":     f"{pullback_lo} ~ {pullback_hi}",
        "support":      f"{support_lo} ~ {support_hi}",
        "stop_loss":    round(support_lo, 2),
        "breakout":     f"突破 {pressure_hi}",
        "_pressure_hi": pressure_hi,
        "_pullback_lo": pullback_lo,
        "_pullback_hi": pullback_hi,
        "_support_lo":  support_lo,
    }


# ── 勝率計算 ──────────────────────────────────────────────────────────────────

OPERATORS = {
    "<": lambda a, b: a < b,    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,  ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,  "!=": lambda a, b: a != b,
    "lt": lambda a, b: a < b,   "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b, "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,  "ne": lambda a, b: a != b,
    "小於": lambda a, b: a < b, "大於": lambda a, b: a > b,
    "等於": lambda a, b: a == b,
}


def _eval_condition(cond: dict, ctx: dict) -> Optional[bool]:
    if not cond.get("enabled", True):
        return None
    field = cond.get("field")
    op    = cond.get("operator")
    val   = cond.get("value")
    actual = ctx.get(field)
    if actual is None:
        return None
    op_fn = OPERATORS.get(op)
    if op_fn is None:
        return str(actual) == str(val)
    try:
        return op_fn(float(actual), float(val))
    except Exception:
        return str(actual) == str(val)


def calc_win_rate(strategy: dict, technical: dict, chips: dict, fundamental: dict,
                  pattern: Optional[dict] = None, volume: Optional[dict] = None) -> dict:
    pattern = pattern or {}
    volume  = volume or {}
    ind = technical["indicators"]
    ctx = {
        "pe":             fundamental.get("pe"),
        "pb":             fundamental.get("pb"),
        "dividend_yield": fundamental.get("dividendYield"),
        "eps":            fundamental.get("eps"),
        "revenue_yoy":    fundamental.get("revenue_yoy"),
        "ma5":  ind.get("ma5"),  "ma10": ind.get("ma10"),
        "ma20": ind.get("ma20"), "ma60": ind.get("ma60"),
        "k":    ind.get("k"),    "d":    ind.get("d"),    "j": ind.get("j"),
        "rsi":  ind.get("rsi"),
        "ma_alignment":      ind.get("ma_align_code"),
        "trend":             ind.get("trend_code"),
        "kd_cross":          ind.get("kd_cross"),
        "macd_status":       ind.get("macd_status"),
        "foreign_consecutive_buy":  chips["stats"].get("foreign_buy_days"),
        "foreign_consecutive_sell": chips["stats"].get("foreign_sell_days"),
        "trust_consecutive_buy":    chips["stats"].get("trust_buy_days"),
        "trust_consecutive_sell":   chips["stats"].get("trust_sell_days"),
        "foreign_buy_days":  chips["stats"].get("foreign_buy_days"),
        "foreign_sell_days": chips["stats"].get("foreign_sell_days"),
        "trust_buy_days":    chips["stats"].get("trust_buy_days"),
        "trust_sell_days":   chips["stats"].get("trust_sell_days"),
        "w_bottom":     pattern.get("w_bottom"),
        "m_top":        pattern.get("m_top"),
        "vol_state":    volume.get("vol_state"),
        "volume_price": volume.get("vol_state"),
        "volume_ratio": volume.get("volume_ratio"),
        "bias_ma20":    volume.get("bias_ma20"),
    }

    conditions = strategy.get("conditions", {}) or {}
    total = 0
    hit = 0
    for cat in ("fundamental", "technical", "chips", "pattern", "volume"):
        for cond in conditions.get(cat, []) or []:
            if not cond.get("enabled", True):
                continue
            result = _eval_condition(cond, ctx)
            if result is None:
                continue
            total += 1
            if result:
                hit += 1

    if total == 0:
        tc = technical["indicators"].get("trend_code")
        base = 65 if tc == "bull" else (35 if tc == "bear" else 50)
        level = chips["main_force"].get("level")
        if level == "safe":
            base += 10
        elif level == "danger":
            base -= 10
        return {"win_rate": min(95, max(5, base)), "hit": 0, "total": 0}

    return {"win_rate": round(hit / total * 100), "hit": hit, "total": total}


# ── 操作建議 ──────────────────────────────────────────────────────────────────

def gen_suggestion(technical: dict, key_prices: dict) -> dict:
    trend = technical["indicators"].get("trend_code")
    last  = technical["indicators"]["last"]

    pressure_hi = key_prices["_pressure_hi"]
    pullback_lo = key_prices["_pullback_lo"]
    pullback_hi = key_prices["_pullback_hi"]
    support_lo  = key_prices["_support_lo"]

    if trend == "bull":
        strategy = "高檔等回檔" if last >= pressure_hi * 0.98 else "回檔找買點"
        entry = f"{pullback_lo} ~ {pullback_hi} (回檔買點)"
        add = f"突破 {pressure_hi} 並站穩"
        stop_loss = f"跌破 {support_lo} (支撐下方)"
        defense = f"{support_lo} (波段低點)"
    elif trend == "bear":
        strategy = "空手觀望或反彈空"
        entry = f"反彈至 {pressure_hi} 附近做空"
        add = f"跌破 {support_lo} 加碼空單"
        stop_loss = f"站回 {pressure_hi} 以上止損"
        defense = f"{pressure_hi}"
    else:
        strategy = "盤整觀望"
        entry = f"突破 {pressure_hi} 或站穩 {support_lo} 後再進場"
        add = "—"
        stop_loss = f"跌破 {support_lo}"
        defense = f"{support_lo}"

    return {
        "strategy":  strategy,
        "entry":     entry,
        "add":       add,
        "stop_loss": stop_loss,
        "defense":   defense,
    }


# ── 整合分析 ──────────────────────────────────────────────────────────────────

def _eval_strategy_match(strategy: dict, technical: dict, chips: dict,
                         fundamental: dict, pattern: dict, volume: dict) -> tuple:
    """回傳 (matched_all, hit, total)：所有啟用條件都命中時 matched_all=True"""
    win_rate_data = calc_win_rate(strategy, technical, chips, fundamental,
                                  pattern=pattern, volume=volume)
    total = win_rate_data["total"]
    hit   = win_rate_data["hit"]
    return (total > 0 and hit == total, hit, total, win_rate_data["win_rate"])


def screen(strategy: dict, candidates: list, kbars_fn, fundamental_map: dict,
           chips_fn=None, max_full_scan: int = 100) -> dict:
    """全市場掃描。
    candidates:    [(ticker, name)] 候選清單
    kbars_fn:      ticker -> kbars list
    fundamental_map: {ticker: {pe, pb, dividendYield, eps}}
    chips_fn:      ticker -> chips_data（可為 None，省略籌碼條件）
    max_full_scan: 通過快篩後最多做幾檔完整分析
    """
    import time
    t0 = time.time()
    matches: list = []
    scanned = 0

    fundamental_conds = (strategy.get("conditions") or {}).get("fundamental") or []

    # Stage 1: 用 fundamental 快篩
    quick_pass: list = []
    for ticker, name in candidates:
        scanned += 1
        f = fundamental_map.get(ticker, {})
        ctx_quick = {
            "pe": f.get("pe"), "pb": f.get("pb"),
            "dividend_yield": f.get("dividendYield"), "eps": f.get("eps"),
        }
        ok = True
        for cond in fundamental_conds:
            if not cond.get("enabled", True):
                continue
            res = _eval_condition(cond, ctx_quick)
            if res is False:
                ok = False
                break
        if ok:
            quick_pass.append((ticker, name, f))
        if len(quick_pass) >= max_full_scan:
            break

    # Stage 2: 對快篩通過的做完整技術分析
    for ticker, name, fund in quick_pass:
        try:
            kbars = kbars_fn(ticker)
            if not kbars or len(kbars) < 20:
                continue
            tech = calc_technical(kbars)
            chips_data = chips_fn(ticker) if chips_fn else {
                "chips": [], "conclusion": "",
                "main_force": {"level": "watch", "reason": ""},
                # stats 用 None 讓 calc_win_rate 略過籌碼條件（避免被當成 0 誤判）
                "stats": {"foreign_buy_days": None, "foreign_sell_days": None,
                          "trust_buy_days": None, "trust_sell_days": None},
            }
            pat = calc_pattern(kbars)
            vol = calc_volume_price(kbars, tech["indicators"])
            matched, hit, total, win_rate = _eval_strategy_match(
                strategy, tech, chips_data, fund, pat, vol)
            if not matched:
                continue
            ind  = tech["indicators"]
            recent_chips = chips_data["chips"]
            foreign_net = recent_chips[-1]["foreign"] if recent_chips else 0
            trust_net   = recent_chips[-1]["trust"]   if recent_chips else 0
            matches.append({
                "ticker":      ticker,
                "name":        name,
                "close":       ind.get("last"),
                "change_pct":  ind.get("change_pct"),
                "volume":      ind.get("vol_now"),
                "ma_status":   ind.get("ma_align_code"),
                "kd_k":        ind.get("k"),
                "macd_status": ind.get("macd_status"),
                "foreign_net": foreign_net,
                "trust_net":   trust_net,
                "win_rate":    win_rate,
                "signal":      chips_data["main_force"].get("level"),
            })
        except Exception:
            continue

    matches.sort(key=lambda x: x["win_rate"], reverse=True)
    return {
        "scan_count":   scanned,
        "match_count":  len(matches),
        "elapsed_sec":  round(time.time() - t0, 2),
        "stocks":       matches,
    }


def analyse(strategy: dict, ticker: str, kbars: list,
            fundamental: Optional[dict] = None,
            chips_data: Optional[dict] = None) -> dict:
    """整合分析，回傳完整 result 物件（對應前端 result 結構）"""
    technical = calc_technical(kbars)
    if chips_data is None:
        chips_data = calc_chips(ticker)
    key_prices    = calc_key_prices(kbars, technical["indicators"])
    pattern_data  = calc_pattern(kbars)
    volume_data   = calc_volume_price(kbars, technical["indicators"])
    win_rate_data = calc_win_rate(strategy, technical, chips_data, fundamental or {},
                                  pattern=pattern_data, volume=volume_data)
    suggestion    = gen_suggestion(technical, key_prices)

    summary = technical["summary"]
    conclusion = (
        f"{summary['overall']}，{summary['ma_alignment']}，{chips_data['conclusion']} "
        f"短線回測支撐 {key_prices['_pullback_lo']} 可布局，"
        f"{key_prices['breakout']} 為加碼訊號，"
        f"跌破 {key_prices['_support_lo']} 停損。"
    )

    public_key_prices = {k: v for k, v in key_prices.items() if not k.startswith("_")}

    return {
        "price":             technical["indicators"].get("last"),
        "change_pct":        technical["indicators"].get("change_pct"),
        "technical_summary": technical["summary"],
        "chips_analysis":    chips_data["chips"],
        "chips_conclusion":  chips_data["conclusion"],
        "key_prices":        public_key_prices,
        "main_force_signal": chips_data["main_force"],
        "pattern_analysis":  pattern_data,
        "volume_analysis":   volume_data,
        "indicators_table":  technical["indicators_table"],
        "indicators":        technical["indicators"],
        "win_rate":          win_rate_data["win_rate"],
        "win_rate_detail":   {"hit": win_rate_data["hit"], "total": win_rate_data["total"]},
        "suggestion":        suggestion,
        "conclusion":        conclusion,
    }
