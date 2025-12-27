import requests
import time
import random
from datetime import date
from db import get_connection

US_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?count=100&scrIds=day_gainers"
CA_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?count=100&scrIds=day_gainers&region=CA"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MarketSnapshotBot/1.0)",
    "Accept": "application/json"
}

def fetch_gainers(url, retries=3):
    for attempt in range(retries):
        r = requests.get(url, headers=HEADERS, timeout=20)

        if r.status_code == 200:
            return r.json()

        if r.status_code == 429:
            sleep = 2 ** attempt + random.random()
            print(f"429 rate limited. Retrying in {sleep:.1f}s")
            time.sleep(sleep)
        else:
            r.raise_for_status()

    raise RuntimeError("Yahoo request failed after retries")

def extract_quotes(payload):
    return (
        payload
        .get("finance", {})
        .get("result", [{}])[0]
        .get("quotes", [])
    )

def main():
    today = date.today()
    conn = get_connection()
    cur = conn.cursor()

    for market, url in [("US", US_URL), ("CAN", CA_URL)]:
        payload = fetch_gainers(url)
        stocks = extract_quotes(payload)

        print(f"{market}: {len(stocks)} gainers")

        for stock in stocks:
            cur.execute("""
                INSERT INTO top_gainers (
                    trade_date,
                    market,
                    symbol,
                    name,
                    price,
                    change_percent,
                    volume,
                    market_cap,
                    pe_ratio,
                    raw_data
                )
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
                stock  # JSONB
            ))

        # polite delay between markets
        time.sleep(2)

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
