"""
fetch.py
--------
Fetches daily OHLCV data from Yahoo Finance using yfinance.

Usage:
    Daily update (called by main.py / GitHub Actions):
        from fetch import load_and_update_all
        data = load_and_update_all()

    One-time bootstrap — replace all CSVs with clean Yahoo data:
        python fetch.py --bootstrap

    Validate data integrity:
        python fetch.py --validate
"""

import csv
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# yfinance imported lazily — only needed for download commands,
# not for validate or load_csv. Allows Python 3.7 for offline use.
yf = None

def _ensure_yfinance():
    """Import yfinance on first use. Fails with a clear message if missing."""
    global yf
    if yf is None:
        try:
            import yfinance
            yf = yfinance
        except ImportError:
            print("\n  ERROR: yfinance is not installed or your Python is too old.")
            print("  yfinance requires Python 3.8+.")
            print()
            print("  Options:")
            print("    1. Upgrade Python to 3.8+ and run: pip install yfinance")
            print("    2. Run --bootstrap from GitHub Actions (uses Python 3.10+)")
            print("    3. Pin older version: pip install yfinance==0.1.70")
            print()
            sys.exit(1)

logger = logging.getLogger(__name__)

TICKERS = {
    'QQQ':  'QQQ',
    'TQQQ': 'TQQQ',
    'SQQQ': 'SQQQ',
    'VIX':  '^VIX',
    'QQQE': 'QQQE',   # Equal-weight Nasdaq 100 — breadth divergence (Rule ⑨)
}

# TQQQ/SQQQ inception: Feb 9, 2010. Use this as default start.
BOOTSTRAP_START = '2010-02-01'

DATA_DIR = Path(__file__).parent / 'data'


def _parse_date(date_str: str) -> str:
    """Normalise various date formats to YYYY-MM-DD."""
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%Y %H:%M:%S'):
        try:
            return datetime.strptime(date_str.split(' ')[0], fmt.split(' ')[0]).strftime('%Y-%m-%d')
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {date_str}")


def _df_to_rows(df) -> list:
    """Convert a yfinance DataFrame to our standard row format."""
    # yfinance ≥0.2.55 returns MultiIndex columns even for single tickers
    if hasattr(df.columns, 'levels') and df.columns.nlevels > 1:
        df.columns = df.columns.droplevel(1)
    rows = []
    for date, row in df.iterrows():
        try:
            rows.append({
                'date':   date.strftime('%Y-%m-%d'),
                'open':   round(float(row['Open']), 4),
                'high':   round(float(row['High']), 4),
                'low':    round(float(row['Low']), 4),
                'close':  round(float(row['Close']), 4),
                'volume': float(row['Volume']),
            })
        except Exception as e:
            logger.debug(f"Skipping row {date}: {e}")
    return rows


def load_csv(path: Path) -> list:
    """Load OHLCV rows from a CSV file.
       Handles Close-only CSVs (like QQQE) by filling OHLV from Close."""
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


def save_csv(rows: list, path: Path) -> None:
    """Save OHLCV rows to CSV in clean YYYY-MM-DD format."""
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


def fetch_latest(ticker_key: str, existing_rows: list) -> list:
    """
    Fetch any missing trading days from Yahoo Finance and append.
    Only fetches from the day after the last existing row.
    """
    _ensure_yfinance()
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
        df = yf.download(yahoo_symbol, start=start, end=tomorrow,
                         auto_adjust=True, progress=False)
        if df.empty:
            logger.warning(f"{ticker_key}: no new data returned")
            return existing_rows

        new_rows = _df_to_rows(df)
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


def bootstrap(data_dir=DATA_DIR, start=BOOTSTRAP_START):
    """
    One-time full download from Yahoo Finance for all tickers.
    REPLACES existing CSVs entirely — no mixing with Google Finance data.

    Usage:
        python fetch.py --bootstrap

    This ensures all data comes from a single source (Yahoo) with
    consistent split adjustments, volume figures, and date formats.
    """
    _ensure_yfinance()
    data_dir.mkdir(parents=True, exist_ok=True)
    tomorrow = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    result = {}

    for key, symbol in TICKERS.items():
        path = data_dir / f"{key}.csv"
        print(f"  {key} ({symbol}): downloading {start} → today ... ", end='', flush=True)

        try:
            df = yf.download(symbol, start=start, end=tomorrow,
                             auto_adjust=True, progress=False)
            if df.empty:
                print(f"EMPTY — skipped")
                continue

            rows = _df_to_rows(df)

            # Back up existing file
            if path.exists():
                backup = path.with_suffix('.csv.bak')
                path.rename(backup)
                print(f"{len(rows)} rows (backed up old → {backup.name}) ", end='')
            else:
                print(f"{len(rows)} rows ", end='')

            save_csv(rows, path)
            result[key] = rows

            # Quick sanity check
            print(f"| {rows[0]['date']} → {rows[-1]['date']} | "
                  f"Close: ${rows[-1]['close']:.2f} | Vol: {rows[-1]['volume']:,.0f}")

        except Exception as e:
            print(f"FAILED — {e}")

    return result


def validate(data_dir: Path = DATA_DIR) -> bool:
    """
    Validate data integrity across all tickers.
    Checks: date format, price sanity, volume sanity, cross-ticker alignment.
    """
    all_ok = True

    print(f"\n  Validating data in {data_dir}:")
    date_sets = {}

    for key in TICKERS:
        path = data_dir / f"{key}.csv"
        if not path.exists():
            print(f"    {key}: MISSING")
            all_ok = False
            continue

        rows = load_csv(path)
        dates = [r['date'] for r in rows]
        date_sets[key] = set(dates)

        # Check date format (should be YYYY-MM-DD)
        bad_dates = [d for d in dates if len(d) != 10 or d[4] != '-']
        if bad_dates:
            print(f"    {key}: ✗ BAD DATE FORMAT — {bad_dates[:3]}")
            all_ok = False

        # Check for duplicate dates
        if len(dates) != len(set(dates)):
            dupes = len(dates) - len(set(dates))
            print(f"    {key}: ✗ {dupes} DUPLICATE DATES")
            all_ok = False

        # Check price sanity (no zeros, no extreme values)
        bad_prices = [r for r in rows if r['close'] <= 0 or r['open'] <= 0]
        if bad_prices:
            print(f"    {key}: ✗ {len(bad_prices)} rows with zero/negative prices")
            all_ok = False

        # Check volume sanity (no scientific notation artifacts > 1 billion)
        bad_vols = [r for r in rows if r['volume'] > 1e9]
        if bad_vols:
            print(f"    {key}: ✗ {len(bad_vols)} rows with suspicious volume > 1B")
            print(f"           Last bad: {bad_vols[-1]['date']} vol={bad_vols[-1]['volume']:.0f}")
            all_ok = False

        # Check continuity (no gaps > 5 business days)
        for i in range(1, len(dates)):
            d1 = datetime.strptime(dates[i-1], '%Y-%m-%d')
            d2 = datetime.strptime(dates[i], '%Y-%m-%d')
            gap = (d2 - d1).days
            if gap > 7:  # allow weekends + 1 holiday
                pass  # Long weekends happen (Thanksgiving, etc)

        if not bad_dates and not bad_prices and not bad_vols:
            print(f"    {key}: ✓ {len(rows)} rows | {rows[0]['date']} → {rows[-1]['date']} | "
                  f"Close: ${rows[-1]['close']:.2f}")

    # Cross-ticker date alignment
    if 'QQQ' in date_sets and 'TQQQ' in date_sets and 'SQQQ' in date_sets:
        common = date_sets['QQQ'] & date_sets['TQQQ'] & date_sets['SQQQ']
        only_qqq = date_sets['QQQ'] - date_sets['TQQQ']
        only_tqqq = date_sets['TQQQ'] - date_sets['QQQ']
        print(f"\n    Cross-ticker alignment:")
        print(f"      Common dates (QQQ ∩ TQQQ ∩ SQQQ): {len(common)}")
        if only_qqq:
            print(f"      QQQ only (no TQQQ): {len(only_qqq)} dates — {sorted(only_qqq)[:5]}...")
        if only_tqqq:
            print(f"      TQQQ only (no QQQ): {len(only_tqqq)} dates — {sorted(only_tqqq)[:5]}...")

        if len(common) >= 3800:
            print(f"      ✓ Good alignment")
        else:
            print(f"      ⚠ Low overlap — may need investigation")

    if all_ok:
        print(f"\n    ✓ All validations passed")
    else:
        print(f"\n    ✗ Issues found — run --bootstrap to fix")

    return all_ok


def load_and_update_all(data_dir: Path = DATA_DIR) -> dict:
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


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s  %(levelname)-8s  %(message)s')

    if '--bootstrap' in sys.argv:
        print("=" * 60)
        print("  BOOTSTRAP: Full Yahoo Finance download")
        print("  This will REPLACE all existing CSVs.")
        print("  Old files will be backed up as .csv.bak")
        print("=" * 60)

        # Optional: custom start date
        start = BOOTSTRAP_START
        for arg in sys.argv:
            if arg.startswith('--start='):
                start = arg.split('=')[1]

        print(f"\n  Downloading from {start} ...\n")
        data = bootstrap(start=start)
        print(f"\n  Done. Run --validate to verify.\n")

    elif '--validate' in sys.argv:
        print("=" * 60)
        print("  DATA VALIDATION")
        print("=" * 60)
        validate()

    else:
        print("Usage:")
        print("  python fetch.py --bootstrap           Full Yahoo download (one-time)")
        print("  python fetch.py --bootstrap --start=2010-02-01")
        print("  python fetch.py --validate            Check data integrity")
        print()
        print("For daily updates, use main.py (calls load_and_update_all)")

