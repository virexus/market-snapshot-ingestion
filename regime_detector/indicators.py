"""
indicators.py
-------------
All technical indicator calculations for the regime detector.
Uses QQQ (clean, no leverage decay) as the signal source.

Updated for V7:
  - EMA10 added (ultra-fast re-entry)
  - RSI5 added (bull market overbought exit)
  - MACD now returns prev histogram for crossover detection
  - ROC10 added (ultra-fast momentum filter)
  - get_qqq_indicators() exposes all V7 fields
"""

import math


def calc_ema(closes: list, period: int) -> list:
    """Exponential Moving Average."""
    k = 2 / (period + 1)
    ema = [closes[0]]
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))
    return ema


def calc_rsi(closes: list, period: int = 14) -> float:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100 - (100 / (1 + ag / al)) if al != 0 else 100.0


def calc_macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD (Moving Average Convergence Divergence).
    Returns: (macd_line, signal_line, histogram, prev_histogram)

    prev_histogram is needed to detect bullish crossovers:
      cross_up = histogram > 0 and prev_histogram <= 0
    """
    if len(closes) < slow + signal + 1:
        return 0.0, 0.0, 0.0, 0.0
    ema_fast    = calc_ema(closes, fast)
    ema_slow    = calc_ema(closes, slow)
    macd_line   = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calc_ema(macd_line[slow - 1:], signal)
    histogram      = macd_line[-1] - signal_line[-1]
    prev_histogram = macd_line[-2] - signal_line[-2]
    return (
        round(macd_line[-1],   4),
        round(signal_line[-1], 4),
        round(histogram,       4),
        round(prev_histogram,  4),
    )


def calc_bollinger(closes: list, period: int = 20):
    """
    Bollinger Bands.
    Returns: (upper, middle, lower, pct_b)
    pct_b = 0 means price at lower band, 1 = upper band.
    """
    if len(closes) < period:
        return closes[-1] * 1.05, closes[-1], closes[-1] * 0.95, 0.5
    window = closes[-period:]
    mid    = sum(window) / period
    std    = math.sqrt(sum((x - mid) ** 2 for x in window) / period)
    upper  = mid + 2 * std
    lower  = mid - 2 * std
    pct_b  = (closes[-1] - lower) / (upper - lower) if upper != lower else 0.5
    return round(upper, 4), round(mid, 4), round(lower, 4), round(pct_b, 4)


def calc_williams_r(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Williams %R. Range: -100 (oversold) to 0 (overbought)."""
    if len(closes) < period:
        return -50.0
    h = max(highs[-period:])
    l = min(lows[-period:])
    return round(-100 * (h - closes[-1]) / (h - l), 2) if h != l else -50.0


def calc_obv(closes: list, volumes: list) -> list:
    """On-Balance Volume."""
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def calc_roc(closes: list, period: int) -> float:
    """Rate of Change - percentage price change over N days."""
    if len(closes) < period + 1:
        return 0.0
    return round((closes[-1] / closes[-period - 1] - 1) * 100, 4)


def get_qqq_indicators(rows: list, vix_rows: list = None, qqqe_rows: list = None) -> dict:
    """
    Compute all indicators from QQQ OHLCV rows.
    Requires at least 210 rows (for EMA200).

    Args:
        rows      : QQQ OHLCV dicts sorted oldest to newest
        vix_rows  : VIX close dicts sorted oldest to newest (optional)
        qqqe_rows : QQQE close dicts sorted oldest to newest (optional, Rule ⑨)

    Returns dict of all indicator values needed by V8, or None if insufficient data.
    """
    if len(rows) < 210:
        return None

    c = [r['close']          for r in rows]
    h = [r['high']           for r in rows]
    l = [r['low']            for r in rows]
    v = [r.get('volume', 0)  for r in rows]

    price = c[-1]

    # EMAs
    ema10  = calc_ema(c, 10)[-1]
    ema20  = calc_ema(c, 20)[-1]
    ema50  = calc_ema(c, 50)[-1]
    ema100 = calc_ema(c, 100)[-1]
    ema200 = calc_ema(c, 200)[-1]

    # RSI - two periods
    rsi14 = calc_rsi(c[-50:], 14)
    rsi5  = calc_rsi(c[-30:],  5)

    # ROC
    roc10 = calc_roc(c, 10)
    roc20 = calc_roc(c, 20)
    roc60 = calc_roc(c, 60)

    # MACD - returns prev_histogram for crossover detection
    macd_line, macd_sig, macd_hist, macd_hist_prev = calc_macd(c)
    macd_cross_up = (macd_hist > 0 and macd_hist_prev <= 0)

    # Bollinger Bands
    bb_u, bb_m, bb_l, bb_pct = calc_bollinger(c)

    # Williams %R
    wr14 = calc_williams_r(h, l, c, 14)

    # OBV slope
    obv       = calc_obv(c[-20:], v[-20:])
    obv_slope = (obv[-1] - obv[-5]) / (abs(obv[-5]) + 1)

    # Volume ratio vs 20-day average
    vol_avg   = sum(v[-21:-1]) / 20 if len(v) > 20 else v[-1]
    vol_ratio = v[-1] / vol_avg if vol_avg > 0 else 1.0

    # VIX (for VIX retreat rule)
    vix_now    = 20.0
    vix_5avg   = 20.0
    vix_retreat = False
    if vix_rows and len(vix_rows) >= 5:
        vix_now   = vix_rows[-1]['close']
        vix_5avg  = sum(r['close'] for r in vix_rows[-5:]) / 5
        vix_retreat = (vix_now < vix_5avg) and (vix_5avg > 28)

    # QQQE Breadth Divergence (Rule ⑨)
    qqqe_price      = 0.0
    qqqe_ema200     = 0.0
    breadth_warning = False
    if qqqe_rows and len(qqqe_rows) >= 210:
        qqqe_closes  = [r['close'] for r in qqqe_rows]
        qqqe_price   = qqqe_closes[-1]
        qqqe_ema200  = calc_ema(qqqe_closes, 200)[-1]
        breadth_warning = qqqe_price < qqqe_ema200

    return {
        # Price
        'price':          round(price, 2),
        'change_pct':     round((c[-1] / c[-2] - 1) * 100, 2),

        # EMAs
        'ema10':          round(ema10,  2),
        'ema20':          round(ema20,  2),
        'ema50':          round(ema50,  2),
        'ema100':         round(ema100, 2),
        'ema200':         round(ema200, 2),
        'ema200_dist':    round((price - ema200) / ema200 * 100, 2),

        # RSI
        'rsi5':           round(rsi5,  2),
        'rsi14':          round(rsi14, 2),

        # ROC
        'roc10':          round(roc10, 4),
        'roc20':          round(roc20, 4),
        'roc60':          round(roc60, 4),

        # MACD
        'macd':           round(macd_line,      4),
        'macd_signal':    round(macd_sig,        4),
        'macd_hist':      round(macd_hist,       4),
        'macd_hist_prev': round(macd_hist_prev,  4),
        'macd_cross_up':  macd_cross_up,

        # Bollinger Bands
        'bb_upper':       round(bb_u,   2),
        'bb_middle':      round(bb_m,   2),
        'bb_lower':       round(bb_l,   2),
        'bb_pct':         round(bb_pct, 4),

        # Williams %R
        'williams_r':     round(wr14, 2),

        # OBV / Volume
        'obv_slope':      round(obv_slope, 6),
        'vol_ratio':      round(vol_ratio, 3),

        # VIX
        'vix':            round(vix_now,  2),
        'vix_5avg':       round(vix_5avg, 2),
        'vix_retreat':    vix_retreat,

        # QQQE Breadth (Rule ⑨)
        'qqqe_price':       round(qqqe_price,  2),
        'qqqe_ema200':      round(qqqe_ema200, 2),
        'breadth_warning':  breadth_warning,
    }
