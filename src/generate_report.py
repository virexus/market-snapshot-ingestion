import os
import psycopg2
from datetime import datetime

QUERY = """
SELECT
    symbol,
    MAX(name)            AS name,
    market,
    COUNT(DISTINCT trade_date)          AS days_appeared,
    ROUND(AVG(change_percent)::numeric, 2) AS avg_change_pct,
    ROUND(AVG(price)::numeric, 2)          AS avg_price,
    MAX(trade_date)                     AS last_seen
FROM top_gainers
GROUP BY symbol, market
ORDER BY days_appeared DESC, avg_change_pct DESC
LIMIT 10
"""

def fetch_rows():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(QUERY)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def build_html(rows):
    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    table_rows = ""
    for rank, (symbol, name, market, days, avg_chg, avg_price, last_seen) in enumerate(rows, 1):
        market_class = "us" if market == "US" else "can"
        table_rows += f"""
            <tr>
                <td class="rank">{rank}</td>
                <td class="symbol">{symbol}</td>
                <td>{name or "—"}</td>
                <td><span class="badge {market_class}">{market}</span></td>
                <td class="center">{days}</td>
                <td class="positive">+{avg_chg}%</td>
                <td>${avg_price:,}</td>
                <td>{last_seen}</td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Top 10 Recurring Gainers</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2.5rem 1.5rem;
    }}

    .container {{ max-width: 960px; margin: 0 auto; }}

    header {{ margin-bottom: 2rem; }}
    h1 {{ font-size: 1.75rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.35rem; }}
    .subtitle {{ color: #94a3b8; font-size: 0.9rem; }}

    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 0.75rem;
      overflow: hidden;
    }}

    table {{ width: 100%; border-collapse: collapse; }}

    thead th {{
      background: #0f172a;
      color: #64748b;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 0.75rem 1rem;
      text-align: left;
      white-space: nowrap;
    }}

    tbody td {{
      padding: 0.875rem 1rem;
      border-top: 1px solid #1e293b;
      font-size: 0.875rem;
      white-space: nowrap;
    }}

    tbody tr {{ background: #1e293b; }}
    tbody tr:nth-child(even) {{ background: #182030; }}
    tbody tr:hover td {{ background: #243350; }}

    .rank {{ color: #64748b; font-size: 0.8rem; width: 2rem; }}
    .symbol {{ font-weight: 700; color: #f1f5f9; letter-spacing: 0.03em; }}
    .center {{ text-align: center; }}
    .positive {{ color: #4ade80; font-weight: 600; }}

    .badge {{
      display: inline-block;
      padding: 0.15rem 0.55rem;
      border-radius: 0.3rem;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .badge.us  {{ background: #1d3a8a; color: #93c5fd; }}
    .badge.can {{ background: #78350f; color: #fcd34d; }}

    footer {{
      margin-top: 1.25rem;
      text-align: right;
      color: #475569;
      font-size: 0.75rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Top 10 Recurring Gainers</h1>
      <p class="subtitle">
        Stocks appearing most frequently in the daily top-gainers screener &mdash; US &amp; Canada
      </p>
    </header>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Symbol</th>
            <th>Name</th>
            <th>Market</th>
            <th style="text-align:center">Days in Top Gainers</th>
            <th>Avg Daily Gain</th>
            <th>Avg Price</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>{table_rows}
        </tbody>
      </table>
    </div>

    <footer>Updated: {updated}</footer>
  </div>
</body>
</html>
"""

def main():
    rows = fetch_rows()
    html = build_html(rows)

    os.makedirs("site", exist_ok=True)
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated site/index.html ({len(rows)} rows)")

if __name__ == "__main__":
    main()
