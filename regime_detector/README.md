# TQQQ/SQQQ Regime Detector

Daily signal generator: **BUY TQQQ** | **BUY SQQQ** | **STAY CASH**

Backtested Jan 2020 – Mar 2026 on real Google Finance data.

---

## Model Architecture

### Layer 1 — Master Market Regime (QQQ vs EMA200)
| QQQ position | Regime | Bias |
|---|---|---|
| >1% above EMA200 | 🟢 BULL | Default to TQQQ |
| >1% below EMA200 | 🔴 BEAR | Default to SQQQ |
| Within ±1% of EMA200 | 🟡 CHOP | Need strong confirmation |

### Layer 2 — Entry Timing Score
Indicators scored from QQQ (not TQQQ — avoids leverage decay):
- EMA20 vs EMA50 (weighted ×2)
- Price vs EMA20
- MACD histogram (weighted ×2)
- MACD line vs signal
- RSI (14)
- Bollinger %B (20)
- Williams %R (14)
- VIX (regime-aware interpretation)
- OBV slope
- Volume ratio vs 20-day avg

### Signal Rules
```
BULL market + score >= 0  → BUY_TQQQ
BULL market + score < 0   → STAY_CASH  (never short in bull)
BEAR market + score <= 0  → BUY_SQQQ
BEAR market + score > 0   → STAY_CASH  (never long in bear)
CHOP + score >= +4        → BUY_TQQQ
CHOP + score <= -4        → BUY_SQQQ
CHOP otherwise            → STAY_CASH
```

### Confirmation Filter
Signal must persist for **2 consecutive closes** before action is taken.
Eliminates whipsawing on single volatile days.

---

## Backtest Results (Jan 2020 – Mar 2026)

| Metric | V1 (TQQQ signals) | V3 (QQQ 2-layer) |
|---|---|---|
| Win Rate | 50.9% | **58.8%** |
| Avg Return/Trade | +3.71% | **+6.58%** |
| Sharpe Ratio | 0.37 | **0.51** |
| Total Trades | 159 | **85** |
| Worst Loss | -21% | **-6.6%** |

---

## Daily Workflow

```
4:00 PM ET  Market closes
4:30 PM ET  GitHub Actions fetches data, runs model, logs signal
            → If signal changed and confirmed 2 days: sends notification
9:30 AM ET  Execute at market open (next day)
```

---

## Setup

### 1. Add initial CSV data
Copy your Google Finance CSVs into `regime_detector/data/`:
```
regime_detector/data/QQQ.csv
regime_detector/data/TQQQ.csv
regime_detector/data/SQQQ.csv
regime_detector/data/VIX.csv
```
After first run, Yahoo Finance keeps them updated automatically.

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run manually
```bash
python regime_detector/main.py
```

### 4. Configure GitHub Actions
The workflow runs automatically Mon–Fri at 4:30 PM ET.

**Optional: email notifications**
Add these in GitHub repo Settings → Secrets → Actions:
```
SMTP_HOST      smtp.gmail.com
SMTP_PORT      587
SMTP_USER      your@gmail.com
SMTP_PASSWORD  your-app-password
NOTIFY_TO      your@gmail.com
```
If not set, signals are logged to CSV and visible in the Actions run log.

---

## File Structure
```
regime_detector/
├── main.py          Entry point — run daily after close
├── indicators.py    EMA, RSI, MACD, BB, Williams %R, OBV calculations
├── regime.py        2-layer signal model + confirmation logic
├── fetch.py         Yahoo Finance updater
├── notify.py        Signal logger + email notifications
├── data/
│   ├── QQQ.csv      Historical + daily updated OHLCV
│   ├── TQQQ.csv
│   ├── SQQQ.csv
│   ├── VIX.csv
│   └── signal_log.csv  ← generated on first run
└── .github/workflows/
    └── regime_detector.yml
```

---

> ⚠️ For educational purposes only. Not financial advice.
