# Bit24 Trading Bot

Automated trading bot for the Bit24 exchange. Buys and sells coins in a loop based on profit targets and price triggers.

## Requirements

```
pip install requests python-dotenv jdatetime matplotlib
```

## Setup

1. Copy `.env.example` to `.env`
2. Add your Bit24 API credentials:
   ```
   BIT24_API_KEY=your_key
   BIT24_SECRET_KEY=your_secret
   ```
3. Run:
   ```
   python main.py
   ```

## How It Works

```
Buy (initial)
    |
    v
Monitor --> Price +2.75% --> Sell
    |
    v
Wait --> Price +0.5% (pump) --> Buy again
Wait --> Price -0.5% (drop) --> Buy again
    |
    v
Monitor --> Price +2.75% --> Sell
    ...loops forever
```

## Outputs

| File | Description |
|------|-------------|
| `trade-YYYY-MM-DD.json` | All trade records (Iranian date) |
| `trade-YYYY-MM-DD.html` | Styled HTML report (on Ctrl+C) |
| `trade-YYYY-MM-DD.png` | Balance chart (on Ctrl+C) |

## Controls

- **Ctrl+C** — Sells held coins, exports HTML + PNG, exits
