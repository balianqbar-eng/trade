import win32com.client
import pandas as pd
from datetime import datetime


class XQBridge:
    def __init__(self):
        self.xq = win32com.client.Dispatch("XQData.XQDataManager")
        self.xq.Connect()

    def get_kbar(self, symbol: str, period: str = "D", bars: int = 250) -> pd.DataFrame:
        # 若報錯請先 print(dir(self.xq)) 確認實際方法名稱
        data = self.xq.GetKBar(symbol, period, bars)
        df = pd.DataFrame(data, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def get_realtime(self, symbol: str) -> dict:
        tick = self.xq.GetRealTime(symbol)
        return {
            "price":  tick.Price,
            "volume": tick.Volume,
            "bid":    tick.Bid,
            "ask":    tick.Ask,
            "time":   datetime.now().isoformat(),
        }

    def get_universe(self, market: str = "TW") -> list:
        return list(self.xq.GetSymbolList(market))

    def get_watchlist_groups(self) -> list:
        # 如果報錯請 print(dir(self.xq)) 確認正確方法名稱
        return list(self.xq.GetPortfolioNameList())

    def get_watchlist(self, group: str) -> list:
        symbols = self.xq.GetPortfolioSymbol(group)
        result = []
        for s in symbols:
            try:
                name = self.xq.GetSymbolName(s) or s
            except Exception:
                name = s
            result.append({"ticker": str(s), "name": str(name)})
        return result
