"""
Smoke tests — 每次 commit 前跑一遍
用法：python smoke_test.py
"""
import sys
import random

PASS = []
FAIL = []

def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  OK  {name}")
    except Exception as e:
        FAIL.append(name)
        print(f"  FAIL {name}: {e}")


# ── 假 K 棒資料（60 根，帶上升趨勢）────────────────────────────────────────────

def _make_kbars(n=60):
    random.seed(42)
    price = 50.0
    rows = []
    for _ in range(n):
        o = price
        h = o + random.uniform(0, 2)
        l = o - random.uniform(0, 1)
        c = random.uniform(l, h)
        vol = random.randint(1000, 5000)
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": vol})
        price = c + random.uniform(-0.5, 1.0)
    return rows

KBARS = _make_kbars()

FAKE_CHIPS = {
    "chips": [],
    "stats": {
        "foreign_buy_days": 3,
        "foreign_sell_days": 0,
        "trust_buy_days": 2,
        "trust_sell_days": 0,
    },
    "conclusion": "外資連買 3 日，籌碼偏多",
    "main_force": {"level": "safe", "reason": "法人主力同步做多"},
}

FAKE_STRATEGY = {
    "name": "測試策略",
    "conditions": {
        "technical": [
            {"field": "k", "operator": "gt", "value": 20, "enabled": True},
        ],
    },
}


# ── 1. strategy_engine 純函式 ─────────────────────────────────────────────────

import strategy_engine as se

def test_calc_technical():
    r = se.calc_technical(KBARS)
    assert "summary" in r
    assert "indicators" in r
    ind = r["indicators"]
    assert ind["last"] > 0
    assert 0 <= ind["k"] <= 100
    assert 0 <= ind["rsi"] <= 100

def test_calc_pattern():
    r = se.calc_pattern(KBARS)
    assert "w_bottom" in r
    assert "m_top" in r
    assert r["w_bottom"] in ("formed", "forming", "none", "insufficient")

def test_calc_volume_price():
    tech = se.calc_technical(KBARS)
    r = se.calc_volume_price(KBARS, tech["indicators"])
    assert "vol_state" in r
    assert "volume_ratio" in r

def test_analyse_returns_shape():
    r = se.analyse(FAKE_STRATEGY, "2330", KBARS, fundamental={}, chips_data=FAKE_CHIPS)
    assert r["price"] > 0
    assert "suggestion" in r
    assert "win_rate" in r
    assert 0 <= r["win_rate"] <= 100
    assert "conclusion" in r

def test_eval_condition_gt():
    cond = {"field": "k", "operator": "gt", "value": 20, "enabled": True}
    assert se._eval_condition(cond, {"k": 50}) is True
    assert se._eval_condition(cond, {"k": 10}) is False

def test_eval_condition_disabled():
    cond = {"field": "k", "operator": "gt", "value": 20, "enabled": False}
    assert se._eval_condition(cond, {"k": 5}) is None

def test_eval_condition_missing_field():
    cond = {"field": "pe", "operator": "lt", "value": 15, "enabled": True}
    assert se._eval_condition(cond, {}) is None


print("\n── strategy_engine ──")
check("calc_technical 回傳正確結構", test_calc_technical)
check("calc_pattern 回傳合法 enum", test_calc_pattern)
check("calc_volume_price 有 vol_state", test_calc_volume_price)
check("analyse 回傳 price/signal/win_rate", test_analyse_returns_shape)
check("_eval_condition gt 運算", test_eval_condition_gt)
check("_eval_condition disabled 回 None", test_eval_condition_disabled)
check("_eval_condition 欄位缺失回 None", test_eval_condition_missing_field)


# ── 2. HTTP 端點（需要 server 在跑）──────────────────────────────────────────

try:
    import requests
    SERVER = "http://localhost:8000"

    def test_health():
        r = requests.get(f"{SERVER}/health", timeout=3)
        assert r.status_code == 200

    def test_strategies_list():
        r = requests.get(f"{SERVER}/qianshao/strategies", timeout=3)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_screen_history():
        r = requests.get(f"{SERVER}/qianshao/screen/history", timeout=3)
        assert r.status_code == 200

    def test_analysis_history():
        r = requests.get(f"{SERVER}/qianshao/analysis/history", timeout=3)
        assert r.status_code == 200

    print("\n── HTTP endpoints ──")
    check("/health 回 200", test_health)
    check("/qianshao/strategies 回 list", test_strategies_list)
    check("/qianshao/screen/history 回 200", test_screen_history)
    check("/qianshao/analysis/history 回 200", test_analysis_history)

except requests.exceptions.ConnectionError:
    print("\n── HTTP endpoints ── (略過：server 未啟動)")
except ImportError:
    print("\n── HTTP endpoints ── (略過：requests 未安裝)")


# ── 結果 ──────────────────────────────────────────────────────────────────────

print(f"\n結果：{len(PASS)} 通過，{len(FAIL)} 失敗")
if FAIL:
    print("失敗項目：", ", ".join(FAIL))
    sys.exit(1)
