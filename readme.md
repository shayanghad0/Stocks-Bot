# Bit24 Spot Trading Bot — Overview

> **This is a demo version.**  
> The real production code that connects to the Bit24 exchange lives in the **`real/`** folder.  
> The demo uses a mock API (`http://localhost:3001`) and is meant only to test the logic.

---

## What the Bot Does

This is a **perpetual spot trading bot** that automatically buys and sells a given cryptocurrency (e.g., BTC) on a spot market. Its goal is to capture small profits from price movements while managing risk with two different buy triggers after each sell.

### Core Strategy

1. **Initial Buy**  
   - Starts by buying **15 USDT** worth of the chosen coin (market order).

2. **Profit Target Sell**  
   - Holds the coin until its price rises by **1.75%** (profit threshold).  
   - Then sells **all** held coins (market order).

3. **Rebuy Trigger**  
   - After a sell, the bot waits for one of two conditions:
     - **Drop** – price falls by **0.5%** below the sell price → **buy 15 USDT**.
     - **Pump** – price rises by **0.25%** above the sell price → **buy 7.5 USDT**.  
   - The first trigger that occurs determines the next buy amount.

4. **Loop**  
   - After rebuying, the bot repeats from step 2 (sell at +1.75% profit).

### Key Parameters

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| Profit target | +1.75% | Sell when price rises this much. |
| Drop trigger | -0.5% | Buy 15 USDT if price drops this much after a sell. |
| Pump trigger | +0.25% | Buy 7.5 USDT if price pumps this much after a sell. |
| Trading fee | 0.55% | Estimated fee per trade (applied in calculations). |

---

## Example Scenario (simplified)

1. **Buy** 15 USDT of BTC at price 50,000 → receives 0.0003 BTC.
2. **Sell** when BTC reaches 50,875 (+1.75%) → earns ~15.26 USDT (minus fee).
3. After sell, price moves:
   - If it drops to 50,621 (-0.5%) → **buy 15 USDT** again.
   - If it pumps to 51,002 (+0.25%) → **buy 7.5 USDT** instead.
4. Loop continues indefinitely until stopped by user.

---

## Flowchart (Mermaid)

```mermaid
flowchart TD
    A([Start]) --> B[Initial Market Buy 15 USDT]
    B --> C[Hold & Wait for +1.75% Profit]

    C -->|Price reaches target| D[Market Sell All Coins]

    D --> E[Wait for Drop (-0.5%) or Pump (+0.25%)]

    E -->|Drop triggered| F[Buy 15 USDT]
    E -->|Pump triggered| G[Buy 7.5 USDT]

    F --> C
    G --> C

    D -.->|On user interrupt| H[Place Limit Sell at Target Price<br/>Generate Report]
    C -.->|On user interrupt| H
    E -.->|On user interrupt| H

    H --> I([End])
```

---

## Features

- **Trade Logging** – all orders are saved to `trade.json` with details (price, amount, trigger type, etc.).
- **Balance Tracking** – records total USDT balance every few seconds.
- **Report Generation** – on exit, produces:
  - `balance_chart.png` – chart of account value over time.
  - `trade_report.html` – summary with profit/loss, total trades, fees, and the chart.
- **Graceful Exit** – pressing `Ctrl+C` places a **limit sell** at the target profit price if holding, avoiding a loss.

---

## Demo vs. Real Code

| Aspect | Demo (this folder) | Real (folder `real/`) |
|--------|-------------------|------------------------|
| API endpoint | `http://localhost:3001` (mock) | Actual Bit24 exchange endpoints |
| Authentication | Token accepted but not validated | Real API keys with full authentication |
| Order execution | Simulated responses | Real market/limit orders on Bit24 |
| Purpose | Logic testing & demonstration | Production-ready trading |

---

## How to Run the Demo

1. Start the mock API server (not included, but you can simulate it).
2. Run the bot and enter a symbol (e.g., `BTC`) and any token.
3. Watch the price monitoring and simulated trades.
4. Stop with `Ctrl+C` to see the report.

---

**Important:**  
This bot is **not financial advice**. It is a demonstration of algorithmic trading logic. Always test thoroughly and understand risks before using with real funds.
