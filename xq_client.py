"""
XQ Mac 端 client
Win11 IP：10.211.55.3，port：8089
"""
import requests

BASE = "http://10.211.55.3:8089"

def quote(code: str) -> dict:
    """取得個股即時報價"""
    r = requests.get(f"{BASE}/quote/{code}", timeout=5)
    r.raise_for_status()
    return r.json()

def field(code: str, f: str):
    """取得單一欄位"""
    r = requests.get(f"{BASE}/quote/{code}/{f}", timeout=5)
    r.raise_for_status()
    return r.json()["value"]

def batch(codes: list[str], fields: list[str] = None) -> dict:
    """批次查詢"""
    params = {"codes": ",".join(codes)}
    if fields:
        params["fields"] = ",".join(fields)
    r = requests.get(f"{BASE}/batch", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def health() -> bool:
    try:
        r = requests.get(f"{BASE}/health", timeout=3)
        return r.json().get("status") == "ok"
    except:
        return False

if __name__ == "__main__":
    if not health():
        print("Server 無法連線，請先在 Win11 啟動 xq_server.py")
        exit(1)
    print("=== 台積電 (2330) ===")
    print(quote("2330"))
    print("\n=== 批次查詢 2330, 2317, 2412 ===")
    print(batch(["2330", "2317", "2412"], ["LTP", "High", "Low", "VOL"]))
