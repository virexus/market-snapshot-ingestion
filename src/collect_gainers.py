import requests
from datetime import date
from db import get_connection

US_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?count=100&scrIds=day_gainers"
CA_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?count=100&scrIds=day_gainers&region=CA"

def fetch_gainers(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()["finance"]["result"][0]["quotes"]

def main():
    today = date.today()
    conn = get_connection()
    cur = conn.cursor()

    for market, url in [("US", US_URL), ("CAN", CA_URL)]:
        stocks = fetch_gainers(url)

        for stock in stocks:
            cur.execute("""
                INSERT INTO top_gainers
                (trade_date, market, symbol, name, price, change_percent, volume, market_cap, pe_ratio, raw_data)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (
                today,
                market,
                stock.get("symbol"),
                stock.get("shortName"),
                stock.get("regularMarketPrice"),
                stock.get("regularMarketChangePercent"),
                stock.get("regularMarketVolume"),
                stock.get("marketCap"),
                stock.get("trailingPE"),
                stock
            ))

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
