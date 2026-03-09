"""
indicators.py
-------------
All technical indicator calculations for the regime detector.
Uses QQQ (clean, no leverage decay) as the signal source.
"""

import math


def calc_ema(closes: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    k = 2 / (period + 1)
    ema = [closes[0]]
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))
    return ema


def calc_rsi(closes: list[float], period: int = 14) -> float:
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


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD (Moving Average Convergence Divergence).
    Returns: (macd_line, signal_line, histogram)
    """
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    macd_line   = [f - s for f, s in zip(ema_fast[slow - 1:], ema_slow[slow - 1:])]
    signal_line = calc_ema(macd_line, signal)
    histogram   = macd_line[-1] - signal_line[-1]
    return round(macd_line[-1], 4), round(signal_line[-1], 4), round(histogram, 4)


def calc_bollinger(closes: list[float], period: int = 20):
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


def calc_williams_r(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Williams %R. Range: -100 (oversold) to 0 (overbought)."""
    if len(closes) < period:
        return -50.0
    h = max(highs[-period:])
    l = min(lows[-period:])
    return round(-100 * (h - closes[-1]) / (h - l), 2) if h != l else -50.0


def calc_obv(closes: list[float], volumes: list[float]) -> list[float]:
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


def get_qqq_indicators(rows: list[dict]) -> dict | None:
    """
    Compute all indicators from QQQ OHLCV rows.
    Requires at least 210 rows (for EMA200).
    Returns dict of indicator values or None if insufficient data.
    """
    if len(rows) < 210:
        return None

    c = [r['close']  for r in rows]
    h = [r['high']   for r in rows]
    l = [r['low']    for r in rows]
    v = [r['volume'] for r in rows]

    price  = c[-1]
    ema20  = calc_ema(c, 20)[-1]
    ema50  = calc_ema(c, 50)[-1]
    ema200 = calc_ema(c, 200)[-1]

    rsi              = calc_rsi(c[-50:])
    macd, ms, mh     = calc_macd(c)
    bb_u, bb_m, bb_l, bb_pct = calc_bollinger(c)
    wr               = calc_williams_r(h, l, c)

    # OBV slope: direction of money flow over last 5 days
    obv        = calc_obv(c[-20:], v[-20:])
    obv_slope  = (obv[-1] - obv[-5]) / (abs(obv[-5]) + 1)

    # Volume ratio vs 20-day average
    vol_avg   = sum(v[-21:-1]) / 20 if len(v) > 20 else v[-1]
    vol_ratio = v[-1] / vol_avg if vol_avg > 0 else 1.0

    return {
        'price':        round(price, 2),
        'change_pct':   round((c[-1] / c[-2] - 1) * 100, 2),
        'ema20':        round(ema20, 2),
        'ema50':        round(ema50, 2),
        'ema200':       round(ema200, 2),
        'ema200_dist':  round((price - ema200) / ema200 * 100, 2),
        'rsi':          round(rsi, 2),
        'macd':         round(macd, 4),
        'macd_signal':  round(ms, 4),
        'macd_hist':    round(mh, 4),
        'bb_upper':     round(bb_u, 2),
        'bb_middle':    round(bb_m, 2),
        'bb_lower':     round(bb_l, 2),
        'bb_pct':       round(bb_pct, 4),
        'williams_r':   round(wr, 2),
        'obv_slope':    round(obv_slope, 6),
        'vol_ratio':    round(vol_ratio, 3),
    }
