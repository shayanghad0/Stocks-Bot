import requests
import time
import sys

# ------------------------------------------------------------
# API endpoints (assumes server runs at localhost:3001)
# ------------------------------------------------------------
BASE_URL = "http://localhost:3001"

def get_price(symbol):
    """Fetch the last price for the given symbol."""
    url = f"{BASE_URL}/api/stats/{symbol}"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    return float(data['last_price'])

def buy_market(symbol, amount_usdt, token):
    """Place a market buy order for the given USDT amount."""
    url = f"{BASE_URL}/api/user/{token}/spot/buy/market/{symbol}?amount={amount_usdt}"
    resp = requests.post(url)
    resp.raise_for_status()
    return resp.json()

def get_balance(token):
    """Get the current balances (USDT and coins)."""
    url = f"{BASE_URL}/api/user/{token}/balance"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

# ------------------------------------------------------------
# User inputs
# ------------------------------------------------------------
token = input("Enter your API token: ").strip()
if not token:
    print("Token cannot be empty.")
    sys.exit(1)

symbol = input("Enter symbol (e.g., BTC): ").strip().upper()
if not symbol:
    print("Symbol cannot be empty.")
    sys.exit(1)

grids = int(input("Input how many grids you want (must be odd): "))
if grids % 2 == 0:
    print("Number of grids must be odd. Please restart the program.")
    sys.exit(1)

grid_percent = float(input("Input grid %: "))
amount_per_buy = float(input("Enter USDT amount for each buy: "))

# ------------------------------------------------------------
# Calculate grid levels
# ------------------------------------------------------------
try:
    price = get_price(symbol)
except Exception as e:
    print(f"Error fetching price: {e}")
    sys.exit(1)

step = price * (grid_percent / 100.0)
middle_index = grids // 2   # 0‑based index of the middle grid

all_levels = [price + i * step for i in range(grids)]
buy_levels = all_levels[:middle_index]      # buy levels (grid 1 .. middle_index)
middle_level = all_levels[middle_index]     # stop level

# Display grid information
print("\n--- Grid Levels ---")
for i, level in enumerate(all_levels, start=1):
    if i - 1 < middle_index:
        label = "BUY"
    elif i - 1 == middle_index:
        label = "no buy or sell"
    else:
        label = "SELL"
    if level.is_integer():
        print(f"grid {i} : {int(level)} ({label})")
    else:
        print(f"grid {i} : {level:.2f} ({label})")
print("--------------------\n")

# ------------------------------------------------------------
# Initial buy at grid 1 (current price)
# ------------------------------------------------------------
print(f"Initial buy at current price {price:.2f} ...")
try:
    buy_market(symbol, amount_per_buy, token)
except Exception as e:
    print(f"Initial buy failed: {e}")
    sys.exit(1)

# Update and show balance after initial buy
balance = get_balance(token)
print(f"Balance after initial buy: {balance}")

bought_flags = [False] * len(buy_levels)
bought_flags[0] = True   # grid 1 already bought

# ------------------------------------------------------------
# Main monitoring loop with live price display
# ------------------------------------------------------------
print("\nStarting price monitoring (check every 1 second)...")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        current_price = get_price(symbol)

        # Determine the next un‑bought buy level (if any)
        next_buy = None
        for idx, level in enumerate(buy_levels):
            if not bought_flags[idx]:
                next_buy = level
                break

        # Terminal output – show current price and next target
        status = f"Current price: {current_price:.2f}"
        if next_buy is not None:
            status += f" | Next buy at: {next_buy:.2f}"
        else:
            status += " | All buy levels reached, waiting for middle grid..."
        print(f"\r{status}", end="")   # overwrite the same line

        # Check if we reached the middle grid (stop condition)
        if current_price >= middle_level:
            print(f"\nPrice reached middle grid at {middle_level:.2f}. Stopping.")
            break

        # Check each buy level in order (lowest to highest)
        for idx, level in enumerate(buy_levels):
            if not bought_flags[idx] and current_price >= level:
                # Print a new line so the buy message is not overwritten
                print(f"\nPrice {current_price:.2f} reached buy level {level:.2f} → buying ...")
                try:
                    buy_market(symbol, amount_per_buy, token)
                    bought_flags[idx] = True
                    balance = get_balance(token)
                    print(f"Updated balance: {balance}")
                except Exception as e:
                    print(f"Buy failed at level {level:.2f}: {e}")

        time.sleep(1)

except KeyboardInterrupt:
    print("\nMonitoring stopped by user.")
except Exception as e:
    print(f"\nUnexpected error: {e}")

print("Program ended.")