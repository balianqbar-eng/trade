"""
Win11 本機 XQ 橋接伺服器，對外開放 port 8000（ngrok tunnel 目標）
啟動：python server.py
"""
from fastapi import FastAPI
from xq_bridge import XQBridge
import uvicorn

app = FastAPI()
xq = XQBridge()


@app.get("/health")
def health():
    return {"status": "ok"}


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


@app.get("/watchlists")
def get_watchlists():
    return xq.get_watchlist_groups()


@app.get("/watchlist")
def get_watchlist(group: str):
    return xq.get_watchlist(group)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
