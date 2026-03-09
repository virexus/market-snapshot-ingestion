"""
notify.py
---------
Logs daily signals to CSV and sends notifications when actionable
signal changes occur (after 2-day confirmation).

Notification channels:
  - Console / GitHub Actions log (always)
  - Email via SMTP (optional — set env vars)

Environment variables (all optional):
  SMTP_HOST      : e.g. smtp.gmail.com
  SMTP_PORT      : e.g. 587
  SMTP_USER      : your email address
  SMTP_PASSWORD  : your app password
  NOTIFY_TO      : recipient email address
"""

import csv
import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

SIGNAL_LOG = Path(__file__).parent / 'data' / 'signal_log.csv'

SIGNAL_EMOJI = {
    'BUY_TQQQ':  '🟢',
    'BUY_SQQQ':  '🔴',
    'STAY_CASH': '🟡',
}

ACTION_MAP = {
    # (from_signal, to_signal) : action description
    ('BUY_TQQQ',  'BUY_SQQQ'):  'SELL TQQQ → BUY SQQQ at tomorrow open',
    ('BUY_TQQQ',  'STAY_CASH'): 'SELL TQQQ → HOLD CASH at tomorrow open',
    ('BUY_SQQQ',  'BUY_TQQQ'):  'SELL SQQQ → BUY TQQQ at tomorrow open',
    ('BUY_SQQQ',  'STAY_CASH'): 'SELL SQQQ → HOLD CASH at tomorrow open',
    ('STAY_CASH', 'BUY_TQQQ'):  'BUY TQQQ at tomorrow open',
    ('STAY_CASH', 'BUY_SQQQ'):  'BUY SQQQ at tomorrow open',
}


def load_signal_log() -> list[dict]:
    """Load historical signal log from CSV."""
    if not SIGNAL_LOG.exists():
        return []
    rows = []
    with open(SIGNAL_LOG, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def append_signal_log(date: str, signal: str, confidence: int,
                      master: str, score: int,
                      qqq_price: float, tqqq_price: float,
                      sqqq_price: float, vix: float,
                      action_required: bool) -> None:
    """Append today's signal to the CSV log."""
    SIGNAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    file_exists = SIGNAL_LOG.exists()
    with open(SIGNAL_LOG, 'a', newline='') as f:
        fieldnames = ['date', 'signal', 'confidence', 'master', 'score',
                      'qqq_price', 'tqqq_price', 'sqqq_price', 'vix', 'action_required']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'date': date, 'signal': signal, 'confidence': confidence,
            'master': master, 'score': score, 'qqq_price': qqq_price,
            'tqqq_price': tqqq_price, 'sqqq_price': sqqq_price,
            'vix': vix, 'action_required': action_required,
        })


def get_prev_signal(log: list[dict]) -> str:
    """Get the most recent signal from the log."""
    if not log:
        return 'STAY_CASH'
    return log[-1]['signal']


def get_last_alerted_signal(log: list[dict]) -> str:
    """Return the signal from the most recent row where action_required was True."""
    for row in reversed(log):
        if row.get('action_required', 'False') == 'True':
            return row['signal']
    return 'STAY_CASH'


def get_signal_history(log: list[dict], n: int = 5) -> list[str]:
    """Get last N signals from log as a list."""
    return [row['signal'] for row in log[-n:]]


def build_message(date: str, signal: str, confidence: int, master: str,
                  score: int, reasoning: str, qqq_price: float,
                  tqqq_price: float, sqqq_price: float, vix: float,
                  action: str | None, prev_signal: str) -> str:
    """Build the notification message body."""
    emoji = SIGNAL_EMOJI.get(signal, '⚪')
    master_emoji = {'BULL': '🟢', 'BEAR': '🔴', 'CHOP': '🟡'}.get(master, '⚪')
    lines = [
        f"TQQQ/SQQQ REGIME DETECTOR — {date}",
        "=" * 45,
        f"Signal:      {emoji} {signal}  ({confidence}% confidence)",
        f"Master:      {master_emoji} {master} MARKET",
        f"L2 Score:    {score:+d}",
        "",
        f"QQQ:  ${qqq_price:.2f}",
        f"TQQQ: ${tqqq_price:.2f}",
        f"SQQQ: ${sqqq_price:.2f}",
        f"VIX:  {vix:.2f}",
        "",
        f"Analysis: {reasoning}",
        "",
    ]
    if action:
        lines += [
            "⚡ ACTION REQUIRED",
            "-" * 45,
            f"Previous signal: {prev_signal}",
            f"New signal:      {signal}",
            f"Action:          {action}",
            "",
            "Execute at market open tomorrow (9:30 AM ET).",
            "Consider a limit order near prior close for better fill.",
        ]
    else:
        lines.append(f"No action needed. Holding {signal.replace('_', ' ')}.")

    lines += ["", "=" * 45,
              "⚠️ Educational only. Not financial advice."]
    return "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    """Send email notification. Returns True if successful."""
    host     = os.getenv('SMTP_HOST')
    port     = int(os.getenv('SMTP_PORT', 587))
    user     = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASSWORD')
    to_addr  = os.getenv('NOTIFY_TO')

    if not all([host, user, password, to_addr]):
        logger.info("Email not configured — skipping (set SMTP_HOST/USER/PASSWORD/NOTIFY_TO)")
        return False

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From']    = user
        msg['To']      = to_addr

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        logger.info(f"Email sent to {to_addr}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False


def notify(date: str, signal: str, confidence: int, master: str,
           score: int, reasoning: str, qqq_price: float,
           tqqq_price: float, sqqq_price: float, vix: float,
           prev_signal: str, action_required: bool) -> None:
    """
    Log signal and send notification if action is required.
    Always prints to console (visible in GitHub Actions log).
    """
    action = ACTION_MAP.get((prev_signal, signal)) if action_required else None

    msg = build_message(
        date=date, signal=signal, confidence=confidence,
        master=master, score=score, reasoning=reasoning,
        qqq_price=qqq_price, tqqq_price=tqqq_price,
        sqqq_price=sqqq_price, vix=vix,
        action=action, prev_signal=prev_signal,
    )

    # Always print — shows up in GitHub Actions run log
    print(msg)

    # Email if configured
    if action_required:
        subject = f"⚡ REGIME CHANGE: {prev_signal} → {signal} | {date}"
        send_email(subject, msg)
    else:
        subject = f"{SIGNAL_EMOJI.get(signal,'⚪')} Regime: {signal} ({confidence}%) | {date}"
        send_email(subject, msg)
