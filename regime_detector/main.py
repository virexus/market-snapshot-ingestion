"""
main.py
-------
Daily regime detector entry point.
Run this after market close (4:30 PM ET) to get today's signal.

Usage:
    python regime_detector/main.py

GitHub Actions runs this automatically at 4:30 PM ET on weekdays.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Make sure imports work whether run from repo root or this directory
sys.path.insert(0, str(Path(__file__).parent))

from fetch   import load_and_update_all
from regime  import compute_signal, should_act, explain
from notify  import (load_signal_log, append_signal_log,
                     get_prev_signal, get_signal_history,
                     get_last_alerted_signal, notify)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / 'data'


def run():
    today = datetime.today().strftime('%Y-%m-%d')
    logger.info(f"=== Regime Detector — {today} ===")

    # 1. Fetch / update all data from Yahoo Finance
    logger.info("Fetching latest data...")
    data = load_and_update_all(DATA_DIR)

    qqq_rows  = data['QQQ']
    tqqq_rows = data['TQQQ']
    sqqq_rows = data['SQQQ']
    vix_rows  = data['VIX']
    qqqe_rows = data.get('QQQE', [])

    if len(qqq_rows) < 210:
        logger.error("Not enough QQQ data — need 210+ rows for EMA200")
        sys.exit(1)

    # 2. Get current prices
    qqq_price  = qqq_rows[-1]['close']
    tqqq_price = tqqq_rows[-1]['close'] if tqqq_rows else 0
    sqqq_price = sqqq_rows[-1]['close'] if sqqq_rows else 0
    vix_value  = vix_rows[-1]['close']  if vix_rows  else 20.0
    data_date  = qqq_rows[-1]['date']

    logger.info(f"Data date: {data_date} | QQQ: ${qqq_price:.2f} | VIX: {vix_value:.2f} | QQQE: ${qqqe_rows[-1]['close']:.2f}" if qqqe_rows else f"Data date: {data_date} | QQQ: ${qqq_price:.2f} | VIX: {vix_value:.2f} | QQQE: N/A")

    # 3. Compute regime signal (V9: tqqq/sqqq added for volume z-score)
    result = compute_signal(qqq_rows, vix_rows, qqqe_rows, tqqq_rows, sqqq_rows)
    signal     = result['signal']
    confidence = result['confidence']
    rule       = result['rule']
    # Derive a master label for notification display
    master = 'BULL' if result['golden_cross'] else ('BEAR' if result['ema200_dist'] < -1.0 else 'CHOP')

    logger.info(f"Signal: {signal} ({confidence}%) | Rule: {rule}")
    logger.info(
        f"EMA200 dist: {result['ema200_dist']:+.2f}%"
        f" | RSI14: {result['rsi14']} | RSI5: {result['rsi5']}"
        f" | MACD hist: {result['macd_hist']}"
        f" | QQQE breadth: {'⚠ WARNING' if result.get('breadth_warning') else 'OK'}"
        f" | Vol Z60: {result.get('vol_zscore', 0):.2f}"
        f" | CB: {'⚠ ACTIVE' if result.get('circuit_breaker') else 'off'}"
    )

    # 4. Load history and check confirmation
    log           = load_signal_log()
    prev_signal   = get_prev_signal(log)
    last_alerted  = get_last_alerted_signal(log)
    sig_history   = get_signal_history(log, n=5)
    sig_history.append(signal)  # include today

    # confirmed = signal held for 2 consecutive closes (yesterday in log + today)
    # action_required = confirmed AND haven't already alerted for this direction
    changed         = should_act(signal, prev_signal)   # V7: simple signal != prev check
    confirmed       = len(sig_history) >= 2 and all(s == signal for s in sig_history[-2:])
    action_required = confirmed and (signal != last_alerted)

    if changed and not confirmed:
        logger.info(f"Signal changed {prev_signal} → {signal} but NOT yet confirmed (need 2 days)")
    elif action_required:
        logger.info(f"⚡ ACTION REQUIRED: {prev_signal} → {signal}")
    else:
        logger.info(f"No change: holding {signal}")

    # 5. Build reasoning string (V7 explain() returns a formatted one-liner)
    reasoning = explain(result)

    # 6. Log and notify
    append_signal_log(
        date=data_date, signal=signal, confidence=confidence,
        master=master, score=rule, qqq_price=qqq_price,
        tqqq_price=tqqq_price, sqqq_price=sqqq_price,
        vix=vix_value, action_required=action_required,
    )

    notify(
        date=data_date, signal=signal, confidence=confidence,
        master=master, score=rule, reasoning=reasoning,
        qqq_price=qqq_price, tqqq_price=tqqq_price,
        sqqq_price=sqqq_price, vix=vix_value,
        prev_signal=prev_signal, action_required=action_required,
    )

    logger.info("=== Done ===")
    return signal, confidence, action_required


if __name__ == '__main__':
    run()
