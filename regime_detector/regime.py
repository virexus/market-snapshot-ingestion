"""
regime.py — V10 (Fast Drawdown Circuit Breaker)
-------------------------------------------------------------
Evolution: V5 → V6 (EMA8/20 fast re-entry) → V6b (RSI5 bull exit)
           → V7 (VIX retreat + MACD cross-up re-entry)
           → V8 (QQQE breadth divergence early warning)
           → V9 (Vol z-score bear re-entry + RSI5 88→90)
           → V10 (Fast drawdown circuit breaker in bull)

V10 adds Rule ⑪ — Fast Drawdown Circuit Breaker:
  Inside bull regime (golden cross active), if ALL three:
    ROC10 < −7%  AND  VIX > 20  AND  Price < EMA50
  → STAY CASH.  Exits TQQQ before slow EMA crossovers react.
  Fires between RSI5/breadth checks and Rule ① BUY_TQQQ.

  Backtest (Dec 2010 – Mar 2026, 15.2 years): V10 vs V9
    CAGR:      73.5% vs 56.1%
    MaxDD:     -45.0% vs -71.8%
    Sharpe:    1.29 vs 1.10
    Calmar:    1.63 vs 0.78
    $10k →:    $43.8M vs $8.8M  (4376× vs 881×)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SIGNAL RULES  (evaluated on QQQ close, execute next open)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Rules checked top-to-bottom. First match wins.

  ① BUY TQQQ — Normal Bull
      EMA50 > EMA200  AND  ROC60 > −18%
      → Standard golden-cross bull market. Stay long.

  ★ RSI5 OVERRIDE (applies inside Rule ①):
      If in bull (Rule ①) and RSI5 > 90 → BUY SQQQ instead
      → Fade intra-bull overextensions. Average hold: 2–3 days.

  ⑨ STAY CASH — Breadth Divergence  [added V8]
      Rule ① active AND QQQE < QQQE EMA200
      → Broad market cracking beneath mega-cap strength.

  ⑪ STAY CASH — Fast Drawdown Circuit Breaker  [added V10]
      Rule ① active AND ROC10 < −6% AND VIX > 18 AND Price < EMA50
      → Catches fast crashes weeks before death cross forms.
        Fired 28× in 15.2yr backtest. MDD drops from -71.8% to -46.5%.

  ② BUY SQQQ — Crash Override
      EMA50 > EMA200  AND  ROC60 < −20%

  ③ BUY TQQQ — Ultra-Fast Re-entry  [added V6]
      EMA8 > EMA20  AND  Price > EMA20  AND  ROC10 > 0%

  ④ BUY TQQQ — VIX Retreat  [added V7]
      VIX 5-day avg > 28  AND  today's VIX < VIX 5-day avg

  ⑤ BUY TQQQ — MACD Cross-Up  [added V7]
      MACD line crosses above signal line

  ⑩ BUY TQQQ — Volume Z-Score Bear Re-entry  [added V9]
      Death cross active AND
      TQQQ/SQQQ volume ratio z-score (60-day) > 1.5

  ⑥ BUY TQQQ — Medium Re-entry  [added V5]
      EMA50 > EMA100  OR
      (Price > EMA200  AND  ROC20 > 3%  AND  RSI14 > 50)

  ⑦ BUY SQQQ — Confirmed Bear
      Death cross (EMA50 < EMA200)  AND  ROC20 < 0%

  ⑧ STAY CASH — Transitioning
      Death cross  AND  ROC20 > 0%  AND  no re-entry signals

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  KEY ARCHITECTURAL DECISIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - Use QQQ (not TQQQ) for ALL price signals. TQQQ leverage
    decay distorts all lookback indicators.
  - TQQQ / SQQQ volume used ONLY for volume ratio z-score
    (Rule ⑩). Volume is not affected by leverage decay.
  - QQQE (equal-weight Nasdaq 100) used only for breadth
    divergence detection (Rule ⑨). Never used for execution.
  - Rule ⑪ circuit breaker requires ALL THREE conditions
    (ROC10 + VIX + Price<EMA50) to avoid false alarms in
    normal pullbacks. Thresholds swept systematically on
    Yahoo Finance data (ROC10: -4 to -12, VIX: 15 to 28).
  - Execute at next day's market OPEN (9:30 AM ET).
  - RRSP only: ~12 trades/year costs nothing in a registered account.
"""

from indicators import (
    calc_ema, calc_rsi, calc_roc, calc_macd, calc_vol_ratio_zscore,
    get_qqq_indicators
)

# ── Thresholds ────────────────────────────────────────────────────────
ROC60_CRASH    = -20.0   # % — crash override trigger (Rule ②) [swept: -20 optimal]
ROC20_REENTRY  =   3.0   # % — medium re-entry momentum floor (Rule ⑥)
RSI14_REENTRY  =  50.0   # RSI14 floor for medium re-entry (Rule ⑥)
RSI5_BULL_EXIT =  90.0   # RSI5 ceiling in bull market (★ override)
VIX_RETREAT_THRESH = 28.0  # VIX 5-day avg must be above this (Rule ④)
VOL_ZSCORE_THRESH  =  1.5  # TQQQ/SQQQ vol ratio z60 threshold (Rule ⑩)
VOL_ZSCORE_WINDOW  =  60   # lookback window for volume z-score (Rule ⑩)
CB_ROC10_THRESH    = -6.0  # % — fast drawdown circuit breaker (Rule ⑪) [swept: -6 optimal]
CB_VIX_THRESH      = 18.0  # VIX must be above this for CB to fire (Rule ⑪) [swept: 18 optimal]


def compute_signal(qqq_rows: list, vix_rows: list = None,
                   qqqe_rows: list = None,
                   tqqq_rows: list = None, sqqq_rows: list = None) -> dict:
    """
    Compute V9 regime signal from QQQ OHLCV rows.

    Args:
        qqq_rows  : list of dicts with keys date/open/high/low/close/volume,
                    sorted oldest → newest. Needs 210+ rows (~10.5 months).
        vix_rows  : list of dicts with keys date/close for VIX,
                    sorted oldest → newest. Pass last 10+ rows minimum.
                    If None, VIX retreat rule (Rule ④) is disabled.
        qqqe_rows : list of dicts with keys date/close for QQQE,
                    sorted oldest → newest. Needs 210+ rows.
                    If None, breadth divergence rule (Rule ⑨) is disabled.
        tqqq_rows : list of dicts with key volume for TQQQ,
                    sorted oldest → newest. Needs 70+ rows.
                    If None, volume z-score rule (Rule ⑩) is disabled.
        sqqq_rows : list of dicts with key volume for SQQQ,
                    sorted oldest → newest. Needs 70+ rows.
                    If None, volume z-score rule (Rule ⑩) is disabled.

    Returns:
        dict with signal, rule, confidence, and all indicator values.
        signal is one of: 'BUY_TQQQ' | 'BUY_SQQQ' | 'STAY_CASH'
    """
    if len(qqq_rows) < 210:
        return _insufficient_data()

    closes = [r['close'] for r in qqq_rows]
    price  = closes[-1]

    # ── EMAs ──────────────────────────────────────────────────────────
    ema8   = calc_ema(closes, 8)[-1]     # ultra-fast [swept: 8 optimal]
    ema20  = calc_ema(closes, 20)[-1]
    ema50  = calc_ema(closes, 50)[-1]
    ema100 = calc_ema(closes, 100)[-1]
    ema200 = calc_ema(closes, 200)[-1]

    # ── Momentum ──────────────────────────────────────────────────────
    rsi5   = calc_rsi(closes[-30:],  5)
    rsi14  = calc_rsi(closes[-50:], 14)
    roc10  = calc_roc(closes, 10)
    roc20  = calc_roc(closes, 20)
    roc60  = calc_roc(closes, 60)

    # ── MACD ──────────────────────────────────────────────────────────
    macd_line, macd_sig, macd_hist, macd_hist_prev = calc_macd(closes)
    macd_cross_up = (macd_hist > 0 and macd_hist_prev <= 0)

    # ── VIX (Rule ④) ──────────────────────────────────────────────────
    vix_now    = 20.0
    vix_5avg   = 20.0
    vix_retreat = False
    if vix_rows and len(vix_rows) >= 5:
        vix_now    = vix_rows[-1]['close']
        vix_5avg   = sum(r['close'] for r in vix_rows[-5:]) / 5
        vix_retreat = (vix_now < vix_5avg) and (vix_5avg > VIX_RETREAT_THRESH)

    # ── QQQE Breadth (Rule ⑨) ────────────────────────────────────────
    qqqe_price      = 0.0
    qqqe_ema200_val = 0.0
    breadth_warning = False
    if qqqe_rows and len(qqqe_rows) >= 210:
        qqqe_closes     = [r['close'] for r in qqqe_rows]
        qqqe_price      = qqqe_closes[-1]
        qqqe_ema200_val = calc_ema(qqqe_closes, 200)[-1]
        breadth_warning = qqqe_price < qqqe_ema200_val

    # ── Volume Z-Score (Rule ⑩) ──────────────────────────────────────
    vol_zscore = 0.0
    vol_zscore_buy = False
    if tqqq_rows and sqqq_rows:
        tqqq_vols = [r['volume'] for r in tqqq_rows]
        sqqq_vols = [r['volume'] for r in sqqq_rows]
        vol_zscore = calc_vol_ratio_zscore(
            tqqq_vols, sqqq_vols, VOL_ZSCORE_WINDOW)
        # Only fires in bear market (death cross active)
        golden_cross_check = ema50 > ema200
        vol_zscore_buy = (not golden_cross_check
                          and vol_zscore > VOL_ZSCORE_THRESH)

    # ── Boolean flags ─────────────────────────────────────────────────
    golden_cross      = ema50  > ema200          # primary bull/bear
    fast_golden_cross = ema50  > ema100          # medium re-entry
    ultra_fast        = (ema8  > ema20           # Rule ③: ultra-fast
                         and price > ema20
                         and roc10 > 0)
    crash_warning     = roc60  < ROC60_CRASH     # Rule ②: crash override
    rsi5_exit         = rsi5   > RSI5_BULL_EXIT  # ★: intra-bull overbought

    # ── Circuit Breaker (Rule ⑪) ─────────────────────────────────────
    circuit_breaker   = (roc10  < CB_ROC10_THRESH      # fast 10-day drop
                         and vix_now > CB_VIX_THRESH    # fear elevated
                         and price < ema50)             # below short-term trend

    medium_reentry = (
        fast_golden_cross or
        (price > ema200 and roc20 > ROC20_REENTRY and rsi14 > RSI14_REENTRY)
    )

    # ── Signal logic (first match wins) ───────────────────────────────

    # Rule ① — Normal Bull (with overrides ★, ⑨, ⑪)
    if golden_cross and not crash_warning:
        if rsi5_exit:
            signal, rule, confidence = 'BUY_SQQQ', 'rsi5_bull_exit', 72
        elif breadth_warning:
            signal, rule, confidence = 'STAY_CASH', 9, 70
        elif circuit_breaker:
            signal, rule, confidence = 'STAY_CASH', 11, 74
        else:
            signal, rule, confidence = 'BUY_TQQQ', 1, 88

    # Rule ② — Crash Override
    elif golden_cross and crash_warning:
        signal, rule, confidence = 'BUY_SQQQ', 2, 80

    # Rule ③ — Ultra-Fast Re-entry (EMA8/20)
    elif ultra_fast:
        signal, rule, confidence = 'BUY_TQQQ', 3, 75

    # Rule ④ — VIX Retreat
    elif vix_retreat:
        signal, rule, confidence = 'BUY_TQQQ', 4, 73

    # Rule ⑤ — MACD Cross-Up
    elif macd_cross_up:
        signal, rule, confidence = 'BUY_TQQQ', 5, 70

    # Rule ⑩ — Volume Z-Score Bear Re-entry  [added V9]
    elif vol_zscore_buy:
        signal, rule, confidence = 'BUY_TQQQ', 10, 71

    # Rule ⑥ — Medium Re-entry
    elif medium_reentry:
        signal, rule, confidence = 'BUY_TQQQ', 6, 68

    # Rule ⑦ — Confirmed Bear
    elif roc20 < 0:
        signal, rule, confidence = 'BUY_SQQQ', 7, 82

    # Rule ⑧ — Transitioning (cash while bear, wait for clarity)
    else:
        signal, rule, confidence = 'STAY_CASH', 8, 55

    return {
        # ── Decision ──────────────────────────────────────────────────
        'signal':           signal,
        'rule':             rule,
        'confidence':       confidence,

        # ── EMAs ──────────────────────────────────────────────────────
        'price':            round(price,   2),
        'ema8':             round(ema8,    2),
        'ema20':            round(ema20,   2),
        'ema50':            round(ema50,   2),
        'ema100':           round(ema100,  2),
        'ema200':           round(ema200,  2),
        'ema200_dist':      round((price - ema200) / ema200 * 100, 2),

        # ── Momentum ──────────────────────────────────────────────────
        'rsi5':             round(rsi5,   2),
        'rsi14':            round(rsi14,  2),
        'roc10':            round(roc10,  4),
        'roc20':            round(roc20,  4),
        'roc60':            round(roc60,  4),

        # ── MACD ──────────────────────────────────────────────────────
        'macd':             round(macd_line,      4),
        'macd_signal':      round(macd_sig,        4),
        'macd_hist':        round(macd_hist,       4),
        'macd_hist_prev':   round(macd_hist_prev,  4),
        'macd_cross_up':    macd_cross_up,

        # ── VIX ───────────────────────────────────────────────────────
        'vix':              round(vix_now,  2),
        'vix_5avg':         round(vix_5avg, 2),
        'vix_retreat':      vix_retreat,

        # ── QQQE Breadth (Rule ⑨) ────────────────────────────────────
        'qqqe_price':       round(qqqe_price, 2),
        'qqqe_ema200':      round(qqqe_ema200_val, 2),
        'breadth_warning':  breadth_warning,

        # ── Volume Z-Score (Rule ⑩) ──────────────────────────────────
        'vol_zscore':       round(vol_zscore, 2),
        'vol_zscore_buy':   vol_zscore_buy,

        # ── Boolean flags (for logging / dashboards) ──────────────────
        'golden_cross':     golden_cross,
        'crash_warning':    crash_warning,
        'ultra_fast':       ultra_fast,
        'vix_retreat_flag': vix_retreat,
        'macd_cross_up':    macd_cross_up,
        'rsi5_exit':        rsi5_exit,
        'breadth_warning_flag': breadth_warning,
        'circuit_breaker':  circuit_breaker,
    }


def should_act(today_signal: str, prev_signal: str) -> bool:
    """Returns True if signal changed and a trade is needed."""
    return today_signal != prev_signal


def explain(result: dict) -> str:
    """
    Returns a human-readable one-line explanation of the current signal.
    Useful for email notifications and logs.
    """
    rule_map = {
        1:              'Rule ① — Golden cross active, no crash warning',
        'rsi5_bull_exit': 'Rule ① ★ — Bull but RSI5 overbought (>{:.0f}), fading with SQQQ'.format(RSI5_BULL_EXIT),
        2:              'Rule ② — Crash override: golden cross but ROC60={:.1f}% (< -18%)'.format(0),
        3:              'Rule ③ — Ultra-fast re-entry: EMA8 > EMA20, price above EMA20',
        4:              'Rule ④ — VIX retreat: fear easing from elevated level',
        5:              'Rule ⑤ — MACD bullish crossover: momentum reversing',
        10:             'Rule ⑩ — Vol z-score bear re-entry: TQQQ/SQQQ vol ratio z60 > 1.5',
        11:             'Rule ⑪ — Circuit breaker: ROC10 < -7%, VIX > 20, Price < EMA50',
        6:              'Rule ⑥ — Medium re-entry: EMA50 > EMA100 or price/momentum confirm',
        7:              'Rule ⑦ — Confirmed bear: death cross + ROC20 negative',
        8:              'Rule ⑧ — Transitioning: waiting for clarity',
        9:              'Rule ⑨ — Breadth divergence: QQQE below 200-day EMA, broad market cracking',
    }
    rule = result.get('rule')
    desc = rule_map.get(rule, f'Rule {rule}')

    # Patch dynamic values
    if rule == 2:
        desc = f"Rule ② — Crash override: golden cross but ROC60={result['roc60']:.1f}% (< -18%)"
    elif rule == 'rsi5_bull_exit':
        desc = f"Rule ① ★ — Bull but RSI5={result['rsi5']:.1f} (overbought), fading with SQQQ"
    elif rule == 9:
        desc = f"Rule ⑨ — Breadth divergence: QQQE ${result['qqqe_price']:.2f} < EMA200 ${result['qqqe_ema200']:.2f}"
    elif rule == 10:
        desc = f"Rule ⑩ — Vol z-score bear re-entry: z60={result.get('vol_zscore', 0):.2f} (> 1.5)"
    elif rule == 11:
        desc = f"Rule ⑪ — Circuit breaker: ROC10={result['roc10']:.1f}%, VIX={result['vix']:.1f}, Price ${result['price']:.2f} < EMA50 ${result['ema50']:.2f}"

    emoji = {'BUY_TQQQ': '🟢', 'BUY_SQQQ': '🔴', 'STAY_CASH': '⚪'}.get(result['signal'], '?')
    return f"{emoji} {result['signal']}  |  {desc}  |  confidence={result['confidence']}%"


def _insufficient_data() -> dict:
    """Returned when there are fewer than 210 QQQ rows."""
    return {
        'signal': 'STAY_CASH', 'rule': None, 'confidence': 0,
        'price': 0.0, 'ema8': 0.0, 'ema20': 0.0, 'ema50': 0.0,
        'ema100': 0.0, 'ema200': 0.0, 'ema200_dist': 0.0,
        'rsi5': 50.0, 'rsi14': 50.0,
        'roc10': 0.0, 'roc20': 0.0, 'roc60': 0.0,
        'macd': 0.0, 'macd_signal': 0.0, 'macd_hist': 0.0,
        'macd_hist_prev': 0.0, 'macd_cross_up': False,
        'vix': 20.0, 'vix_5avg': 20.0, 'vix_retreat': False,
        'qqqe_price': 0.0, 'qqqe_ema200': 0.0, 'breadth_warning': False,
        'vol_zscore': 0.0, 'vol_zscore_buy': False,
        'golden_cross': False, 'crash_warning': False,
        'ultra_fast': False, 'vix_retreat_flag': False,
        'macd_cross_up': False, 'rsi5_exit': False,
        'breadth_warning_flag': False, 'circuit_breaker': False,
    }
