import pythoncom
import win32com.client
import pandas as pd
from datetime import datetime

# XQ COM 類別名稱（嗨投資 XQLite）
_XQ_COM_CLASS = "XQAddin.Addin"


class XQBridge:
    def __init__(self):
        self.xq = None

    def _connect(self):
        if self.xq is None:
            pythoncom.CoInitialize()
            try:
                self.xq = win32com.client.GetActiveObject(_XQ_COM_CLASS)
            except Exception:
                self.xq = win32com.client.Dispatch(_XQ_COM_CLASS)
        return self.xq

    def get_methods(self) -> list:
        """列出 COM 物件所有可用方法，用於偵錯"""
        return sorted([m for m in dir(self._connect()) if not m.startswith("_")])

    def get_kbar(self, symbol: str, period: str = "D", bars: int = 250) -> pd.DataFrame:
        data = self._connect().GetKBar(symbol, period, bars)
        df = pd.DataFrame(data, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def get_realtime(self, symbol: str) -> dict:
        tick = self._connect().GetRealTime(symbol)
        return {
            "price":  tick.Price,
            "volume": tick.Volume,
            "bid":    tick.Bid,
            "ask":    tick.Ask,
            "time":   datetime.now().isoformat(),
        }

    def get_universe(self, market: str = "TW") -> list:
        return list(self._connect().GetSymbolList(market))

    def get_watchlist_groups(self) -> list:
        return list(self._connect().GetPortfolioNameList())

    def get_watchlist(self, group: str) -> list:
        symbols = self._connect().GetPortfolioSymbol(group)
        result = []
        for s in symbols:
            try:
                name = self._connect().GetSymbolName(s) or s
            except Exception:
                name = s
            result.append({"ticker": str(s), "name": str(name)})
        return result
