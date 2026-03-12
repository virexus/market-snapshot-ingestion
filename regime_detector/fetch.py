"""
fetch.py
--------
Fetches daily OHLCV data from Yahoo Finance using yfinance.
Used for daily updates — initial history loaded from Google Finance CSVs.
"""

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)

TICKERS = {
    'QQQ':  'QQQ',
    'TQQQ': 'TQQQ',
    'SQQQ': 'SQQQ',
    'VIX':  '^VIX',
    'QQQE': 'QQQE',   # Equal-weight Nasdaq 100 — breadth divergence (Rule ⑨)
}

DATA_DIR = Path(__file__).parent / 'data'


def _parse_date(date_str: str) -> str:
    """Normalise various date formats to YYYY-MM-DD."""
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%Y %H:%M:%S'):
        try:
            return datetime.strptime(date_str.split(' ')[0], fmt.split(' ')[0]).strftime('%Y-%m-%d')
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {date_str}")


def load_csv(path: Path) -> list[dict]:
    """Load OHLCV rows from a CSV file (Google Finance or our own format).
       Handles Close-only CSVs (like QQQE from Google Finance) by filling
       Open/High/Low from Close and Volume as 0."""
    rows = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                close = float(row['Close'])
                rows.append({
                    'date':   _parse_date(row['Date']),
                    'open':   float(row.get('Open', close)),
                    'high':   float(row.get('High', close)),
                    'low':    float(row.get('Low', close)),
                    'close':  close,
                    'volume': float(row.get('Volume', 0)),
                })
            except Exception as e:
                logger.debug(f"Skipping row: {e}")
    return sorted(rows, key=lambda x: x['date'])


def save_csv(rows: list[dict], path: Path) -> None:
    """Save OHLCV rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        writer.writeheader()
        for r in rows:
            writer.writerow({
                'Date':   r['date'],
                'Open':   r['open'],
                'High':   r['high'],
                'Low':    r['low'],
                'Close':  r['close'],
                'Volume': r['volume'],
            })


def fetch_latest(ticker_key: str, existing_rows: list[dict]) -> list[dict]:
    """
    Fetch any missing trading days from Yahoo Finance and append to existing rows.
    Only fetches from the day after the last existing row.

    Args:
        ticker_key   : one of 'QQQ', 'TQQQ', 'SQQQ', 'VIX'
        existing_rows: already-loaded rows sorted oldest → newest

    Returns:
        Updated full list of rows (existing + new).
    """
    yahoo_symbol = TICKERS[ticker_key]
    last_date    = existing_rows[-1]['date'] if existing_rows else '2020-01-01'
    start        = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    today        = datetime.today().strftime('%Y-%m-%d')
    tomorrow     = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')

    if start > today:
        logger.info(f"{ticker_key}: already up to date ({last_date})")
        return existing_rows

    logger.info(f"{ticker_key}: fetching {start} → {today}")
    try:
        # end is exclusive in yfinance — use tomorrow so today's close is included
        df = yf.download(yahoo_symbol, start=start, end=tomorrow,
                         auto_adjust=True, progress=False)
        # yfinance ≥0.2.55 returns MultiIndex columns even for single tickers
        if isinstance(df.columns, object) and hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)
        if df.empty:
            logger.warning(f"{ticker_key}: no new data returned")
            return existing_rows

        new_rows = []
        for date, row in df.iterrows():
            new_rows.append({
                'date':   date.strftime('%Y-%m-%d'),
                'open':   round(float(row['Open']), 4),
                'high':   round(float(row['High']), 4),
                'low':    round(float(row['Low']), 4),
                'close':  round(float(row['Close']), 4),
                'volume': float(row['Volume']),
            })

        combined = existing_rows + new_rows
        # Deduplicate by date, keep last occurrence
        seen = {}
        for r in combined:
            seen[r['date']] = r
        combined = sorted(seen.values(), key=lambda x: x['date'])
        logger.info(f"{ticker_key}: added {len(new_rows)} rows, total {len(combined)}")
        return combined

    except Exception as e:
        logger.error(f"{ticker_key}: fetch failed — {e}")
        return existing_rows


def load_and_update_all(data_dir: Path = DATA_DIR) -> dict[str, list[dict]]:
    """
    Load all tickers from CSV, fetch any missing days from Yahoo,
    save updated CSVs back to disk.

    Returns dict: {'QQQ': [...], 'TQQQ': [...], 'SQQQ': [...], 'VIX': [...]}
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    result = {}

    for key in TICKERS:
        path = data_dir / f"{key}.csv"
        existing = load_csv(path) if path.exists() else []
        updated  = fetch_latest(key, existing)
        save_csv(updated, path)
        result[key] = updated
        logger.info(f"{key}: {len(updated)} rows, last date {updated[-1]['date'] if updated else 'N/A'}")

    return result
