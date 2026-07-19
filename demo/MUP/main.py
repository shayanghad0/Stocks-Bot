import requests
import sys
import time
import os

# ---------------------------
# 1. User inputs
# ---------------------------
symbol = input("Enter symbol (e.g., BTC): ").upper()
grids = int(input("Input how many grids you want (odd number): "))
grid_percent = float(input("Input grid %: "))
amount_usdt = float(input("Input amount in USDT per buy order (e.g., 15): "))
api_token = input("Enter your API token: ")

if grids % 2 == 0:
    print("Number of grids must be odd. Please restart.")
    sys.exit(1)

# ---------------------------
# 2. Fetch current price
# ---------------------------
def get_current_price():
    try:
        resp = requests.get(f"http://localhost:3001/api/stats/{symbol}")
        resp.raise_for_status()
        data = resp.json()
        price = data.get('last_price')
        if price is None:
            raise ValueError("'last_price' missing in response")
        return float(price)
    except Exception as e:
        print(f"Error fetching price: {e}")
        sys.exit(1)

price = get_current_price()
print(f"Current {symbol} price: {price}\n")

# ---------------------------
# 3. Build grid levels
# ---------------------------
step = price * (grid_percent / 100)
middle_index = grids // 2

grids_info = []   # each element: (level, label, triggered_flag)
for i in range(1, grids + 1):
    level = price + (i - 1) * step
    if i - 1 < middle_index:
        label = "BUY"
    elif i - 1 == middle_index:
        label = "NO TRADE"
    else:
        label = "SELL"
    grids_info.append({
        'level': level,
        'label': label,
        'triggered': False
    })

# ---------------------------
# 4. API helper functions
# ---------------------------
def place_market_buy(amount):
    """Execute a market buy order."""
    url = f"http://localhost:3001/api/user/{api_token}/spot/buy/market/{symbol}"
    params = {"amount": amount}
    try:
        resp = requests.post(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"BUY order failed: {e}")
        return None

def get_balances():
    """Fetch current balances."""
    url = f"http://localhost:3001/api/user/{api_token}/balance"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Balance fetch failed: {e}")
        return None

# ---------------------------
# 5. Monitoring loop with auto‑update
# ---------------------------
previous_price = price
balances = get_balances()

try:
    while True:
        # Clear screen for live update
        os.system('cls' if os.name == 'nt' else 'clear')

        # Fetch fresh price
        current_price = get_current_price()

        # --- Check for crossings and execute orders ---
        for g in grids_info:
            level = g['level']
            label = g['label']
            triggered = g['triggered']

            # BUY: price crosses DOWN through the level
            if label == "BUY" and not triggered:
                if previous_price > level and current_price <= level:
                    print(f"🔽 Price crossed BUY level {level:.2f} → placing BUY order")
                    order_resp = place_market_buy(amount_usdt)
                    if order_resp:
                        g['triggered'] = True
                        balances = get_balances()   # refresh after order
                    else:
                        print("Order failed, will retry on next cycle.")
                    time.sleep(0.5)

            # SELL: placeholder for crossing UP
            elif label == "SELL" and not triggered:
                if previous_price < level and current_price >= level:
                    print(f"🔼 Price crossed SELL level {level:.2f} → would SELL here")
                    # Uncomment and implement sell endpoint if available
                    # g['triggered'] = True   # uncomment to avoid repeated messages

        # --- Refresh balances periodically ---
        if balances is None:
            balances = get_balances()

        # --- Build the dashboard ---
        print(f"⚡ GRID TRADING DASHBOARD  |  {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Symbol: {symbol}  |  Current Price: {current_price:.4f}  |  Grid %: {grid_percent}%\n")

        # Grid table
        print(f"{'Grid':<6} {'Level':<12} {'Type':<10} {'Status'}")
        print("-" * 45)
        for idx, g in enumerate(grids_info, start=1):
            level_str = f"{int(g['level'])}" if g['level'].is_integer() else f"{g['level']:.2f}"
            status = "✔ TRIGGERED" if g['triggered'] else "⏳ waiting"
            print(f"{idx:<6} {level_str:<12} {g['label']:<10} {status}")

        # Balances
        if balances:
            usdt = balances.get('USDT', 0)
            coin_balance = balances.get('coins', {}).get(symbol, 0)
            print(f"\n💰 USDT: {usdt:.2f}  |  {symbol}: {coin_balance:.6f}")
        else:
            print("\n⚠️ Unable to fetch balances")

        # --- Update previous price for next iteration ---
        previous_price = current_price

        # Wait before next poll
        time.sleep(5)

except KeyboardInterrupt:
    print("\n\nMonitoring stopped by user.")
    final_bal = get_balances()
    if final_bal:
        print("Final balances:", final_bal)