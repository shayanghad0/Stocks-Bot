import requests
import sys
import time

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

# Display the grid
print("Grid levels:")
for idx, g in enumerate(grids_info, start=1):
    level_str = f"{int(g['level'])}" if g['level'].is_integer() else f"{g['level']:.2f}"
    print(f"grid {idx} : {level_str} ({g['label']})")
print("\nStarting price monitoring... (Press Ctrl+C to stop)\n")

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
# 5. Main monitoring loop
# ---------------------------
# Keep track of which buy grid levels have been triggered
# (We only place one buy per grid level)
triggered_buy_levels = set()

try:
    while True:
        current_price = get_current_price()
        print(f"[{time.strftime('%H:%M:%S')}] Current price: {current_price:.2f}")

        # Check each grid level
        for idx, g in enumerate(grids_info):
            level = g['level']
            label = g['label']
            triggered = g['triggered']

            # ---------- BUY logic ----------
            if label == "BUY" and not triggered:
                # If price falls to or below the BUY level, execute market buy
                if current_price <= level:
                    print(f"🔽 Price {current_price:.2f} <= BUY level {level:.2f} → placing BUY order")
                    order_resp = place_market_buy(amount_usdt)
                    if order_resp:
                        # Mark this grid as triggered
                        g['triggered'] = True
                        triggered_buy_levels.add(level)
                        # Show updated balances
                        balances = get_balances()
                        if balances:
                            print("Updated balances:", balances)
                    else:
                        print("Order failed, will retry on next cycle.")
                    # Small delay to avoid flooding
                    time.sleep(1)

            # ---------- SELL logic (placeholder) ----------
            elif label == "SELL" and not triggered:
                # We don't have a sell endpoint, but we can print a suggestion
                if current_price >= level:
                    print(f"🔼 Price {current_price:.2f} >= SELL level {level:.2f} → would SELL here (implement sell endpoint)")
                    # Optionally mark as triggered to avoid repeated messages
                    g['triggered'] = True  # comment out if you want to keep seeing it

        # Wait before next poll
        time.sleep(5)

except KeyboardInterrupt:
    print("\nMonitoring stopped by user.")
    # Show final balances
    bal = get_balances()
    if bal:
        print("Final balances:", bal)