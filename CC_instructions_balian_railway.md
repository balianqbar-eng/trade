# CC 作業指令：XQ + Balian 資料夾遷移至 Railway.app

## 前置確認（人工已完成）
- Railway.app 帳號已註冊（GitHub 登入）
- GitHub repo 已建立（balian-quant）
- Anthropic API Key 已申請，備妥備用
- Win11 已安裝 ngrok 並取得公開 HTTPS 網址
- Win11 防火牆已手動開放 TCP port 8000
- XQ 全球贏家可正常登入報價

---

## 系統架構

```
Mac Mini
└── Parallels Win11（本機）
    ├── XQ 全球贏家（COM 元件）
    └── Balian 資料夾
        ├── xq_bridge/       ← 留在本機
        │   ├── xq_bridge.py
        │   └── server.py    ← FastAPI，對外開放 port 8000
        ├── data/            ← CSV / Excel 留在本機
        └── config/          ← XQ 設定檔留在本機

Railway.app（Linux 雲端）
└── balian-quant/            ← 從 GitHub 自動部署
    ├── main.py
    ├── strategy.py
    ├── backtest.py
    ├── screener.py
    ├── claude_analyst.py
    ├── requirements.txt
    └── Procfile
```

---

## 任務一：Win11 本機（Parallels）

### Step 1｜整理 Balian 資料夾

在 Win11 裡建立以下目錄結構：

```
C:\Balian\
├── xq_bridge\
│   ├── xq_bridge.py
│   └── server.py
├── data\
└── config\
```

### Step 2｜安裝依賴套件

```bash
conda activate xq
pip install fastapi uvicorn pandas numpy pywin32 requests anthropic
python Scripts/pywin32_postinstall.py -install
```

### Step 3｜建立 xq_bridge.py

```python
import win32com.client
import pandas as pd
from datetime import datetime

class XQBridge:
    def __init__(self):
        self.xq = win32com.client.Dispatch("XQData.XQDataManager")
        self.xq.Connect()

    def get_kbar(self, symbol: str, period: str = "D", bars: int = 250) -> pd.DataFrame:
        data = self.xq.GetKBar(symbol, period, bars)
        df = pd.DataFrame(data, columns=["date","open","high","low","close","volume"])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def get_realtime(self, symbol: str) -> dict:
        tick = self.xq.GetRealTime(symbol)
        return {
            "price": tick.Price,
            "volume": tick.Volume,
            "bid": tick.Bid,
            "ask": tick.Ask,
            "time": datetime.now().isoformat()
        }

    def get_universe(self, market: str = "TW") -> list:
        return self.xq.GetSymbolList(market)
```

### Step 4｜建立 server.py（FastAPI 橋接）

```python
from fastapi import FastAPI
from xq_bridge import XQBridge
import uvicorn

app = FastAPI()
xq = XQBridge()

@app.get("/kbar/{symbol}")
def get_kbar(symbol: str, period: str = "D", bars: int = 250):
    df = xq.get_kbar(symbol, period, bars)
    return df.reset_index().to_dict(orient="records")

@app.get("/realtime/{symbol}")
def get_realtime(symbol: str):
    return xq.get_realtime(symbol)

@app.get("/universe")
def get_universe():
    return xq.get_universe("TW")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Step 5｜設定開機自動啟動（Windows 工作排程器）

```
工作排程器 → 建立工作
名稱：XQ_Bridge_Server
觸發程序：登入時
動作：程式 → python
引數：C:\Balian\xq_bridge\server.py
執行身分：系統管理員
```

### Step 6｜驗證本機 server 正常

```bash
# 在 Win11 瀏覽器或 PowerShell 測試
curl http://localhost:8000/kbar/2330
# 應回傳 JSON 格式的 K 線資料
```

---

## 任務二：Railway.app 部署

### Step 1｜建立本地專案資料夾（Mac 側）

```bash
mkdir balian-quant
cd balian-quant
git init
git remote add origin https://github.com/你的帳號/balian-quant.git
```

### Step 2｜建立 requirements.txt

```
fastapi
uvicorn
pandas
numpy
requests
anthropic
schedule
```

### Step 3｜建立 Procfile

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Step 4｜建立 strategy.py

```python
import pandas as pd

class TechStrategy:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._calc_indicators()

    def _calc_indicators(self):
        c = self.df["close"]
        self.df["ma5"]  = c.rolling(5).mean()
        self.df["ma20"] = c.rolling(20).mean()
        self.df["ma60"] = c.rolling(60).mean()
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        self.df["rsi"] = 100 - 100 / (1 + gain / loss)
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        self.df["macd"]   = ema12 - ema26
        self.df["signal"] = self.df["macd"].ewm(span=9).mean()
        self.df["hist"]   = self.df["macd"] - self.df["signal"]

    def generate_signals(self) -> pd.Series:
        df = self.df
        buy  = (df["ma5"] > df["ma20"]) & (df["ma5"].shift() <= df["ma20"].shift()) & (df["rsi"] < 70)
        sell = (df["ma5"] < df["ma20"]) & (df["ma5"].shift() >= df["ma20"].shift()) & (df["rsi"] > 30)
        signals = pd.Series(0, index=df.index)
        signals[buy]  =  1
        signals[sell] = -1
        return signals
```

### Step 5｜建立 backtest.py

```python
import pandas as pd

class Backtest:
    def __init__(self, df: pd.DataFrame, signals: pd.Series,
                 capital: float = 1_000_000, fee_rate: float = 0.001425):
        self.df = df
        self.signals = signals
        self.capital = capital
        self.fee_rate = fee_rate

    def run(self) -> dict:
        equity, position, entry_price = self.capital, 0, 0
        trades, equity_curve = [], []

        for date, row in self.df.iterrows():
            sig = self.signals.get(date, 0)
            price = row["close"]

            if sig == 1 and position == 0:
                shares = int(equity / price / 1000) * 1000
                cost = shares * price * (1 + self.fee_rate)
                if shares > 0:
                    equity -= cost
                    position, entry_price = shares, price

            elif sig == -1 and position > 0:
                revenue = position * price * (1 - self.fee_rate - 0.003)
                pnl = revenue - position * entry_price
                trades.append({"date": str(date), "pnl": pnl,
                                "return": pnl / (position * entry_price)})
                equity += revenue
                position = 0

            equity_curve.append(equity + position * price)

        trades_df = pd.DataFrame(trades)
        total_return = (equity_curve[-1] - self.capital) / self.capital
        win_rate = float((trades_df["pnl"] > 0).mean()) if len(trades_df) else 0

        return {
            "total_return": round(total_return, 4),
            "win_rate": round(win_rate, 4),
            "trade_count": len(trades_df),
            "max_drawdown": round(self._max_drawdown(equity_curve), 4),
            "trades": trades_df.to_dict(orient="records")
        }

    def _max_drawdown(self, curve):
        arr = pd.Series(curve)
        roll_max = arr.cummax()
        return float(((arr - roll_max) / roll_max).min())
```

### Step 6｜建立 screener.py

```python
import pandas as pd
import requests
import os

class Screener:
    def __init__(self):
        self.xq_url = os.environ["XQ_BRIDGE_URL"]

    def fetch_kbar(self, symbol: str) -> pd.DataFrame:
        resp = requests.get(f"{self.xq_url}/kbar/{symbol}",
                            params={"period": "D", "bars": 100}, timeout=10)
        return pd.DataFrame(resp.json())

    def screen(self, universe: list, conditions: dict) -> pd.DataFrame:
        from strategy import TechStrategy
        results = []
        for symbol in universe:
            try:
                df = self.fetch_kbar(symbol)
                if df.empty:
                    continue
                strat = TechStrategy(df)
                last = strat.df.iloc[-1]
                rsi_ok  = conditions.get("rsi_min", 0) <= last["rsi"] <= conditions.get("rsi_max", 100)
                trend_ok = last["ma5"] > last["ma20"] if conditions.get("ma_trend") == "up" else True
                vol_ok   = last["volume"] >= conditions.get("volume_min", 0)
                if rsi_ok and trend_ok and vol_ok:
                    results.append({"symbol": symbol, "rsi": round(last["rsi"], 2),
                                    "close": last["close"], "ma5": round(last["ma5"], 2)})
            except Exception:
                continue
        return pd.DataFrame(results).sort_values("rsi") if results else pd.DataFrame()
```

### Step 7｜建立 claude_analyst.py

```python
import anthropic
import os

class ClaudeAnalyst:
    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )

    def interpret(self, symbol: str, result: dict) -> str:
        prompt = f"""
你是一位台股量化分析師，請用繁體中文針對以下回測結果給出簡短專業評語（100字以內）：

股票代號：{symbol}
總報酬：{result['total_return']:.2%}
勝率：{result['win_rate']:.2%}
最大回撤：{result['max_drawdown']:.2%}
交易次數：{result['trade_count']}
        """
        msg = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text

    def screen_comment(self, stocks: list) -> str:
        prompt = f"""
以下是今日量化選股結果，請用繁體中文給出市場觀察摘要（150字以內）：
{stocks}
        """
        msg = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
```

### Step 8｜建立 main.py

```python
from fastapi import FastAPI
from strategy import TechStrategy
from backtest import Backtest
from screener import Screener
from claude_analyst import ClaudeAnalyst
import requests, os
import pandas as pd

app = FastAPI()
XQ_URL = os.environ["XQ_BRIDGE_URL"]

def fetch_kbar(symbol: str, period="D", bars=250) -> pd.DataFrame:
    resp = requests.get(f"{XQ_URL}/kbar/{symbol}",
                        params={"period": period, "bars": bars}, timeout=15)
    return pd.DataFrame(resp.json())

@app.get("/")
def root():
    return {"status": "Balian Quant API running"}

@app.get("/analyse/{symbol}")
def analyse(symbol: str):
    df = fetch_kbar(symbol)
    signals = TechStrategy(df).generate_signals()
    result = Backtest(df, signals).run()
    comment = ClaudeAnalyst().interpret(symbol, result)
    return {"symbol": symbol, "result": result, "comment": comment}

@app.get("/screen")
def screen(rsi_min: int = 40, rsi_max: int = 60, ma_trend: str = "up"):
    universe = requests.get(f"{XQ_URL}/universe", timeout=30).json()
    screener = Screener()
    stocks = screener.screen(universe[:100],
                             {"rsi_min": rsi_min, "rsi_max": rsi_max, "ma_trend": ma_trend})
    comment = ClaudeAnalyst().screen_comment(stocks.to_dict(orient="records"))
    return {"stocks": stocks.to_dict(orient="records"), "comment": comment}

@app.get("/realtime/{symbol}")
def realtime(symbol: str):
    return requests.get(f"{XQ_URL}/realtime/{symbol}", timeout=10).json()
```

### Step 9｜推上 GitHub 並連結 Railway

```bash
# Mac 終端機
cd balian-quant
git add .
git commit -m "init: balian quant railway deploy"
git push origin main

# Railway CLI
npm install -g @railway/cli
railway login
railway link   # 選擇已建立的 balian-quant 專案
railway up
```

### Step 10｜Railway Dashboard 填入環境變數

```
ANTHROPIC_API_KEY = sk-ant-xxxxxxxx（你的 API Key）
XQ_BRIDGE_URL    = https://xxxx.ngrok.io（ngrok 產生的網址）
```

---

## 驗收測試

```bash
# 測試 Win11 本機 bridge
curl http://localhost:8000/kbar/2330

# 測試 Railway 分析 API
curl https://your-app.railway.app/analyse/2330

# 測試選股
curl "https://your-app.railway.app/screen?rsi_min=40&rsi_max=60&ma_trend=up"
```

---

## 補充說明給 CC

1. XQ 的 COM 方法名稱（GetKBar、GetRealTime、GetSymbolList）依版本可能不同，若報錯請先執行 `import win32com.client; xq = win32com.client.Dispatch("XQData.XQDataManager"); print(dir(xq))` 確認實際方法名稱。
2. ngrok 免費版每次重啟網址會變，若要固定可改用 Cloudflare Tunnel（免費且網址固定）。
3. Railway 免費額度每月 $5 美元，量化分析流量正常情況下足夠。
4. Win11 時區請確認設定為台北（UTC+8），避免 K 線時間戳記錯誤。
5. Balian 資料夾內原有的 CSV/Excel 資料留在本機 `C:\Balian\data\`，不需要上傳到 Railway。
