import os
import json
import psycopg2
from datetime import datetime

LOOKBACK_DAYS = 90
MIN_APPEARANCES = 2

QUERY = f"""
SELECT
    symbol,
    MAX(name)                              AS name,
    market,
    COUNT(DISTINCT trade_date)             AS days_appeared,
    ROUND(AVG(change_percent)::numeric, 2) AS avg_change_pct,
    ROUND(AVG(price)::numeric, 2)          AS avg_price,
    MAX(trade_date)                        AS last_seen
FROM top_gainers
WHERE trade_date >= CURRENT_DATE - INTERVAL '{LOOKBACK_DAYS} days'
GROUP BY symbol, market
HAVING COUNT(DISTINCT trade_date) >= {MIN_APPEARANCES}
ORDER BY days_appeared DESC, avg_change_pct DESC
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

    data = [
        {
            "symbol":      row[0],
            "name":        row[1] or "—",
            "market":      row[2],
            "days":        row[3],
            "avg_chg":     float(row[4]),
            "avg_price":   float(row[5]),
            "last_seen":   str(row[6]),
        }
        for row in rows
    ]

    data_json = json.dumps(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Recurring Gainers</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2.5rem 1.5rem;
    }}

    .container {{ max-width: 1000px; margin: 0 auto; }}

    header {{ margin-bottom: 1.75rem; }}
    h1 {{ font-size: 1.75rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.3rem; }}
    .subtitle {{ color: #94a3b8; font-size: 0.875rem; }}

    .controls {{
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.25rem;
      flex-wrap: wrap;
    }}

    .controls label {{
      color: #94a3b8;
      font-size: 0.825rem;
      font-weight: 500;
    }}

    select {{
      background: #1e293b;
      color: #e2e8f0;
      border: 1px solid #334155;
      border-radius: 0.4rem;
      padding: 0.45rem 0.75rem;
      font-size: 0.875rem;
      cursor: pointer;
      outline: none;
    }}
    select:focus {{ border-color: #3b82f6; }}

    .count {{
      margin-left: auto;
      color: #64748b;
      font-size: 0.8rem;
    }}

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
      cursor: pointer;
      user-select: none;
    }}
    thead th:hover {{ color: #94a3b8; }}
    thead th.sorted {{ color: #38bdf8; }}
    thead th .arrow {{ margin-left: 0.3rem; opacity: 0.5; }}
    thead th.sorted .arrow {{ opacity: 1; }}

    tbody td {{
      padding: 0.875rem 1rem;
      border-top: 1px solid #263145;
      font-size: 0.875rem;
      white-space: nowrap;
    }}

    tbody tr {{ background: #1e293b; }}
    tbody tr:nth-child(even) {{ background: #182030; }}
    tbody tr:hover td {{ background: #243350; }}

    .rank   {{ color: #64748b; font-size: 0.8rem; width: 2.5rem; }}
    .symbol {{ font-weight: 700; color: #f1f5f9; letter-spacing: 0.03em; }}
    .center {{ text-align: center; }}
    .right  {{ text-align: right; }}
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

    .empty {{
      text-align: center;
      padding: 3rem 1rem;
      color: #475569;
      font-size: 0.9rem;
    }}

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
      <h1>Recurring Gainers</h1>
      <p class="subtitle">Stocks appearing most frequently in the daily top-gainers screener &mdash; US &amp; Canada &mdash; last {LOOKBACK_DAYS} days</p>
    </header>

    <div class="controls">
      <label for="market-filter">Market</label>
      <select id="market-filter">
        <option value="all">All</option>
        <option value="US">US</option>
        <option value="CAN">Canada</option>
      </select>

      <label for="gain-filter">Avg Daily Gain</label>
      <select id="gain-filter">
        <option value="all">All</option>
        <option value="0-5">0% – 5%</option>
        <option value="5-10">5% – 10%</option>
        <option value="10-20">10% – 20%</option>
        <option value="20+">20%+</option>
      </select>

      <span class="count" id="row-count"></span>
    </div>

    <div class="card">
      <table>
        <thead>
          <tr>
            <th class="rank">#</th>
            <th data-col="symbol">Symbol <span class="arrow">↕</span></th>
            <th data-col="name">Name <span class="arrow">↕</span></th>
            <th data-col="market">Market <span class="arrow">↕</span></th>
            <th data-col="days" class="center sorted">Days <span class="arrow">↓</span></th>
            <th data-col="avg_chg" class="right">Avg Gain <span class="arrow">↕</span></th>
            <th data-col="avg_price" class="right">Avg Price <span class="arrow">↕</span></th>
            <th data-col="last_seen">Last Seen <span class="arrow">↕</span></th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>

    <footer>Updated: {updated}</footer>
  </div>

  <script>
    const ALL_DATA = {data_json};

    let sortCol = "days";
    let sortAsc = false;

    function inGainRange(val, range) {{
      if (range === "all") return true;
      if (range === "0-5")  return val >= 0  && val < 5;
      if (range === "5-10") return val >= 5  && val < 10;
      if (range === "10-20")return val >= 10 && val < 20;
      if (range === "20+")  return val >= 20;
      return true;
    }}

    function render() {{
      const marketVal = document.getElementById("market-filter").value;
      const gainVal   = document.getElementById("gain-filter").value;

      let rows = ALL_DATA.filter(r =>
        (marketVal === "all" || r.market === marketVal) &&
        inGainRange(r.avg_chg, gainVal)
      );

      rows.sort((a, b) => {{
        let av = a[sortCol], bv = b[sortCol];
        if (typeof av === "string") av = av.toLowerCase();
        if (typeof bv === "string") bv = bv.toLowerCase();
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ?  1 : -1;
        return 0;
      }});

      const tbody = document.getElementById("table-body");

      if (rows.length === 0) {{
        tbody.innerHTML = `<tr><td colspan="8" class="empty">No results match the selected filters.</td></tr>`;
        document.getElementById("row-count").textContent = "0 results";
        return;
      }}

      tbody.innerHTML = rows.map((r, i) => `
        <tr>
          <td class="rank">${{i + 1}}</td>
          <td class="symbol">${{r.symbol}}</td>
          <td>${{r.name}}</td>
          <td><span class="badge ${{r.market === 'US' ? 'us' : 'can'}}">${{r.market}}</span></td>
          <td class="center">${{r.days}}</td>
          <td class="right positive">+${{r.avg_chg.toFixed(2)}}%</td>
          <td class="right">$${{r.avg_price.toLocaleString()}}</td>
          <td>${{r.last_seen}}</td>
        </tr>
      `).join("");

      document.getElementById("row-count").textContent = `${{rows.length}} result${{rows.length !== 1 ? "s" : ""}}`;
    }}

    // Sorting
    document.querySelectorAll("thead th[data-col]").forEach(th => {{
      th.addEventListener("click", () => {{
        const col = th.dataset.col;
        if (sortCol === col) {{
          sortAsc = !sortAsc;
        }} else {{
          sortCol = col;
          sortAsc = col === "symbol" || col === "name";
        }}

        document.querySelectorAll("thead th").forEach(h => {{
          h.classList.remove("sorted");
          const arrow = h.querySelector(".arrow");
          if (arrow) arrow.textContent = "↕";
        }});

        th.classList.add("sorted");
        th.querySelector(".arrow").textContent = sortAsc ? "↑" : "↓";
        render();
      }});
    }});

    document.getElementById("market-filter").addEventListener("change", render);
    document.getElementById("gain-filter").addEventListener("change", render);

    render();
  </script>
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
