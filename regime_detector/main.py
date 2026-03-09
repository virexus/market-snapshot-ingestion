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
from regime  import compute_signal, should_act
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

    if len(qqq_rows) < 210:
        logger.error("Not enough QQQ data — need 210+ rows for EMA200")
        sys.exit(1)

    # 2. Get current prices
    qqq_price  = qqq_rows[-1]['close']
    tqqq_price = tqqq_rows[-1]['close'] if tqqq_rows else 0
    sqqq_price = sqqq_rows[-1]['close'] if sqqq_rows else 0
    vix_value  = vix_rows[-1]['close']  if vix_rows  else 20.0
    data_date  = qqq_rows[-1]['date']

    logger.info(f"Data date: {data_date} | QQQ: ${qqq_price:.2f} | VIX: {vix_value:.2f}")

    # 3. Compute regime signal
    result = compute_signal(qqq_rows, vix_value)
    signal     = result['signal']
    confidence = result['confidence']
    master     = result['master']
    score      = result['score']
    ind        = result['indicators']

    logger.info(f"Signal: {signal} ({confidence}%) | Master: {master} | Score: {score:+d}")
    logger.info(f"EMA200 dist: {ind['ema200_dist']:+.2f}% | RSI: {ind['rsi']} | MACD hist: {ind['macd_hist']}")

    # 4. Load history and check confirmation
    log           = load_signal_log()
    prev_signal   = get_prev_signal(log)
    last_alerted  = get_last_alerted_signal(log)
    sig_history   = get_signal_history(log, n=5)
    sig_history.append(signal)  # include today

    # confirmed = signal has held for 2 consecutive closes (yesterday in log + today)
    # action_required = confirmed AND haven't already alerted for this signal direction
    changed         = signal != prev_signal
    confirmed       = should_act(signal, prev_signal, sig_history, confirm_days=2)
    action_required = confirmed and (signal != last_alerted)

    if changed and not confirmed:
        logger.info(f"Signal changed {prev_signal} → {signal} but NOT yet confirmed (need 2 days)")
    elif action_required:
        logger.info(f"⚡ ACTION REQUIRED: {prev_signal} → {signal}")
    else:
        logger.info(f"No change: holding {signal}")

    # 5. Build reasoning string
    master_desc = {
        'BULL': f"QQQ {ind['ema200_dist']:+.1f}% above EMA200 (${ind['ema200']:.2f}) — bull market confirmed.",
        'BEAR': f"QQQ {ind['ema200_dist']:+.1f}% below EMA200 (${ind['ema200']:.2f}) — bear market confirmed.",
        'CHOP': f"QQQ within ±1% of EMA200 (${ind['ema200']:.2f}) — transitional zone.",
    }[master]

    reasoning = (
        f"{master_desc} "
        f"Layer 2 score {score:+d}: "
        f"EMA20 {ind['ema20']:.2f} vs EMA50 {ind['ema50']:.2f}, "
        f"RSI {ind['rsi']:.1f}, MACD hist {ind['macd_hist']:+.4f}, "
        f"BB%B {ind['bb_pct']*100:.0f}%, W%R {ind['williams_r']:.1f}, "
        f"VIX {vix_value:.1f}."
    )

    # 6. Log and notify
    append_signal_log(
        date=data_date, signal=signal, confidence=confidence,
        master=master, score=score, qqq_price=qqq_price,
        tqqq_price=tqqq_price, sqqq_price=sqqq_price,
        vix=vix_value, action_required=action_required,
    )

    notify(
        date=data_date, signal=signal, confidence=confidence,
        master=master, score=score, reasoning=reasoning,
        qqq_price=qqq_price, tqqq_price=tqqq_price,
        sqqq_price=sqqq_price, vix=vix_value,
        prev_signal=prev_signal, action_required=action_required,
    )

    logger.info("=== Done ===")
    return signal, confidence, action_required


if __name__ == '__main__':
    run()
