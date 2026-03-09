"""
regime.py
---------
2-Layer regime detection model.

Layer 1 — Master Market Regime (uses QQQ vs EMA200):
    BULL  : QQQ > 1% above EMA200  → bias toward TQQQ
    BEAR  : QQQ > 1% below EMA200  → bias toward SQQQ
    CHOP  : QQQ within ±1% of EMA200 → require strong confirmation

Layer 2 — Entry Timing Score (RSI, MACD, BB, Williams %R, OBV, Volume):
    Scored indicators determine whether to act or stay cash
    within the master regime.

Signal output: BUY_TQQQ | BUY_SQQQ | STAY_CASH

Backtest results (Jan 2020 – Mar 2026, real Google Finance data):
    Win Rate:         58.8%   (vs 50.9% with TQQQ-based signals)
    Avg Return/Trade: +6.58%  (vs +3.71%)
    Sharpe Ratio:     0.51    (vs 0.37)
    Total Trades:     85      (vs 159 — less whipsawing)
    Worst Loss:       -6.6%   (vs -21%)
"""

from indicators import get_qqq_indicators


SIGNALS = ("BUY_TQQQ", "BUY_SQQQ", "STAY_CASH")


def compute_signal(qqq_rows: list[dict], vix: float) -> dict:
    """
    Compute regime signal from QQQ OHLCV data and current VIX.

    Args:
        qqq_rows : list of dicts with keys date/open/high/low/close/volume,
                   sorted oldest → newest. Needs 210+ rows.
        vix      : current VIX closing value

    Returns:
        dict with keys:
            signal       : "BUY_TQQQ" | "BUY_SQQQ" | "STAY_CASH"
            confidence   : int 40–95
            master       : "BULL" | "BEAR" | "CHOP"
            score        : raw layer-2 score (int)
            bullish_count: int
            bearish_count: int
            neutral_count: int
            indicators   : full indicator dict from get_qqq_indicators()
    """
    ind = get_qqq_indicators(qqq_rows)
    if ind is None:
        return {'signal': 'STAY_CASH', 'confidence': 40,
                'master': 'CHOP', 'score': 0,
                'bullish_count': 0, 'bearish_count': 0, 'neutral_count': 0,
                'indicators': None}

    price       = ind['price']
    ema20       = ind['ema20']
    ema50       = ind['ema50']
    ema200_dist = ind['ema200_dist']

    # ── LAYER 1: Master regime ──────────────────────────────────────
    if ema200_dist > 1.0:
        master = 'BULL'
    elif ema200_dist < -1.0:
        master = 'BEAR'
    else:
        master = 'CHOP'

    # ── LAYER 2: Entry timing score ─────────────────────────────────
    score = 0
    bull_count = bear_count = neut_count = 0

    def _bull():
        nonlocal score, bull_count
        score += 1; bull_count += 1

    def _bear():
        nonlocal score, bear_count
        score -= 1; bear_count += 1

    def _neut():
        nonlocal neut_count
        neut_count += 1

    # EMA20 vs EMA50  (medium-term trend, weighted ×2)
    if ema20 > ema50:   score += 2; bull_count += 1
    elif ema20 < ema50: score -= 2; bear_count += 1
    else:               _neut()

    # Price vs EMA20 (short-term trend)
    if price > ema20:   _bull()
    elif price < ema20: _bear()
    else:               _neut()

    # MACD histogram (weighted ×2)
    if ind['macd_hist'] > 0:   score += 2; bull_count += 1
    elif ind['macd_hist'] < 0: score -= 2; bear_count += 1
    else:                      _neut()

    # MACD line vs signal
    if ind['macd'] > ind['macd_signal']:   _bull()
    elif ind['macd'] < ind['macd_signal']: _bear()
    else:                                  _neut()

    # RSI
    if ind['rsi'] > 55:   _bull()
    elif ind['rsi'] < 45: _bear()
    else:                 _neut()

    # Bollinger %B
    if ind['bb_pct'] > 0.55:   _bull()
    elif ind['bb_pct'] < 0.45: _bear()
    else:                      _neut()

    # Williams %R
    if ind['williams_r'] > -30:   _bull()
    elif ind['williams_r'] < -70: _bear()
    else:                         _neut()

    # VIX — interpreted differently per regime
    if master == 'BULL':
        # High VIX in bull market = fear spike = buying opportunity
        if vix > 28:      _bull()   # extreme fear → buy dip
        elif vix < 15:    _bull()   # calm bull → stay in
        elif vix > 22:    _bear()   # elevated caution
        else:             _neut()
    else:
        # Bear market: high VIX = trend continuation for SQQQ
        if vix > 25:      score -= 2; bear_count += 1
        elif vix > 20:    _bear()
        elif vix < 18:    _bull()   # calming = potential reversal
        else:             _neut()

    # OBV slope (money flow)
    if ind['obv_slope'] > 0:   _bull()
    elif ind['obv_slope'] < 0: _bear()
    else:                      _neut()

    # Volume amplifier — strong volume confirms direction
    if ind['vol_ratio'] > 1.2:
        score = score + 1 if score > 0 else score - 1

    # ── COMBINE LAYERS ───────────────────────────────────────────────
    if master == 'BULL':
        # In bull market: stay in TQQQ unless timing is clearly bad
        final = 'BUY_TQQQ' if score >= 0 else 'STAY_CASH'
    elif master == 'BEAR':
        # In bear market: stay in SQQQ unless timing is clearly bad
        final = 'BUY_SQQQ' if score <= 0 else 'STAY_CASH'
    else:
        # Transitional / choppy — require strong conviction
        if score >= 4:    final = 'BUY_TQQQ'
        elif score <= -4: final = 'BUY_SQQQ'
        else:             final = 'STAY_CASH'

    confidence = min(95, max(40, 50 + abs(score) * 4 + (10 if master != 'CHOP' else 0)))

    return {
        'signal':        final,
        'confidence':    confidence,
        'master':        master,
        'score':         score,
        'bullish_count': bull_count,
        'bearish_count': bear_count,
        'neutral_count': neut_count,
        'indicators':    ind,
    }


def should_act(today_signal: str, prev_signal: str, signal_history: list[str],
               confirm_days: int = 2) -> bool:
    """
    Guard against whipsawing — only act if signal has held
    for `confirm_days` consecutive closes.

    Args:
        today_signal   : today's computed signal
        prev_signal    : yesterday's signal (from log)
        signal_history : list of last N signals oldest → newest
        confirm_days   : number of consecutive days required (default 2)

    Returns:
        True if you should act on the signal change, False if wait.
    """
    if len(signal_history) < confirm_days:
        return False
    recent = signal_history[-confirm_days:]
    return all(s == today_signal for s in recent)
