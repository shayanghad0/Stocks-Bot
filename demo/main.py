import requests
import time
import json
import sys
import os
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
import base64
from io import BytesIO

BASE_URL = "http://localhost:3001"
TRADE_FILE = "trade.json"

BUY_AMOUNT_USDT = 15
PUMP_BUY_AMOUNT_USDT = 7.5
PROFIT_THRESHOLD = 0.0175   # 1.75%
DROP_THRESHOLD = 0.005      # 0.5%
PUMP_THRESHOLD = 0.0025     # 0.25%
FEE_RATE = 0.0055           # 0.55%
BALANCE_RECORD_INTERVAL = 5

balance_history = []
start_time = time.time()
end_time = None
total_trades = 0
total_fees_usdt = 0.0

def api_request(method, endpoint, token=None, params=None, data=None):
    url = BASE_URL + endpoint
    if token:
        url = url.replace("{YOUR_TOKEN}", token)
    headers = {"Content-Type": "application/json"}
    try:
        if method.upper() == "GET":
            resp = requests.get(url, params=params, headers=headers)
        elif method.upper() == "POST":
            resp = requests.post(url, params=params, json=data, headers=headers)
        else:
            raise ValueError("Unsupported HTTP method")
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

def get_next_id():
    if os.path.exists(TRADE_FILE):
        with open(TRADE_FILE, 'r', encoding='utf-8') as f:
            try:
                trades = json.load(f)
                if not isinstance(trades, list) or not trades:
                    return 1
                max_id = max((t.get("ID", 0) for t in trades), default=0)
                return max_id + 1
            except:
                return 1
    return 1

def save_order(order_data):
    global total_trades
    trades = []
    if os.path.exists(TRADE_FILE):
        with open(TRADE_FILE, 'r', encoding='utf-8') as f:
            try:
                trades = json.load(f)
                if not isinstance(trades, list):
                    trades = []
            except:
                trades = []
    order_data["ID"] = get_next_id()
    trades.append(order_data)
    with open(TRADE_FILE, 'w', encoding='utf-8') as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)
    total_trades += 1
    print(f"Order saved to {TRADE_FILE} with ID {order_data['ID']}")

def update_sell_status(order_id, new_status):
    if not os.path.exists(TRADE_FILE):
        return
    with open(TRADE_FILE, 'r', encoding='utf-8') as f:
        trades = json.load(f)
        if not isinstance(trades, list):
            return
    for trade in trades:
        if trade.get("orderId") == order_id:
            trade["sell-status"] = new_status
            break
    with open(TRADE_FILE, 'w', encoding='utf-8') as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)
    print(f"Updated sell-status to '{new_status}' for order {order_id}")

def market_buy(token, symbol, amount_usdt):
    endpoint = f"/api/user/{{YOUR_TOKEN}}/spot/buy/market/{symbol}"
    params = {"amount": amount_usdt}
    return api_request("POST", endpoint, token=token, params=params)

def market_sell(token, symbol, amount_coin):
    endpoint = f"/api/user/{{YOUR_TOKEN}}/spot/sell/market/{symbol}"
    params = {"amount": amount_coin}
    return api_request("POST", endpoint, token=token, params=params)

def limit_sell(token, symbol, price, amount_coin):
    endpoint = f"/api/user/{{YOUR_TOKEN}}/spot/custom/sell/{price}/{symbol}"
    params = {"amount": amount_coin}
    return api_request("POST", endpoint, token=token, params=params)

def get_balance(token):
    endpoint = "/api/user/{YOUR_TOKEN}/balance"
    return api_request("GET", endpoint, token=token)

def get_price(symbol):
    stats = api_request("GET", f"/api/stats/{symbol}")
    return stats.get("last_price")

def get_total_balance_usdt(token, symbol):
    try:
        bal = get_balance(token)
        usdt = bal.get("USDT", 0.0)
        coins = bal.get("coins", {})
        coin_bal = coins.get(symbol, 0.0)
        price = get_price(symbol)
        if price is None:
            return None
        return usdt + (coin_bal * price)
    except:
        return None

def record_balance(token, symbol, force=False):
    global balance_history
    now = time.time()
    if not force and balance_history and (now - balance_history[-1][0]) < BALANCE_RECORD_INTERVAL:
        return
    total = get_total_balance_usdt(token, symbol)
    if total is not None:
        balance_history.append((now, total))

def wait_for_price_condition(token, symbol, reference_price, condition, condition_name):
    while True:
        current_price = get_price(symbol)
        if current_price is None:
            print("Failed to fetch price, retrying...")
            time.sleep(1)
            continue
        record_balance(token, symbol)
        if condition(current_price, reference_price):
            return current_price
        clear_screen()
        print(f"[{format_time(time.time())}] {symbol} price: {current_price:.6f}")
        print(f"Reference: {reference_price:.6f}  {condition_name}")
        time.sleep(1)

def wait_for_buy_condition(token, symbol, sell_price):
    drop_target = sell_price * (1 - DROP_THRESHOLD)
    pump_target = sell_price * (1 + PUMP_THRESHOLD)
    print(f"\nWaiting for buy trigger:")
    print(f"  Drop 0.5% to <= {drop_target:.6f} -> buy 15 USDT")
    print(f"  Pump 0.25% to >= {pump_target:.6f} -> buy 7.5 USDT")
    print("(Only the first trigger will execute)\n")
    
    while True:
        current_price = get_price(symbol)
        if current_price is None:
            print("Failed to fetch price, retrying...")
            time.sleep(1)
            continue
        record_balance(token, symbol)
        if current_price <= drop_target:
            clear_screen()
            print(f"[{format_time(time.time())}] Price dropped to {current_price:.6f} (target {drop_target:.6f})")
            return 'drop', current_price, BUY_AMOUNT_USDT
        elif current_price >= pump_target:
            clear_screen()
            print(f"[{format_time(time.time())}] Price pumped to {current_price:.6f} (target {pump_target:.6f})")
            return 'pump', current_price, PUMP_BUY_AMOUNT_USDT
        
        clear_screen()
        print(f"[{format_time(time.time())}] {symbol} price: {current_price:.6f}")
        print(f"Sell price: {sell_price:.6f}")
        print(f"Drop target: {drop_target:.6f} (need {current_price - drop_target:.6f} more)")
        print(f"Pump target: {pump_target:.6f} (need {pump_target - current_price:.6f} more)")
        time.sleep(1)

def generate_report(balance_history, symbol, start_time, end_time, total_trades, total_fees_usdt):
    if not balance_history:
        print("No balance data to plot.")
        return
    
    # Convert timestamps to datetime objects
    dates = [datetime.fromtimestamp(t) for t, _ in balance_history]
    values = [v for _, v in balance_history]
    
    start_val = values[0]
    end_val = values[-1]
    profit = end_val - start_val
    profit_pct = (profit / start_val * 100) if start_val != 0 else 0

    plt.figure(figsize=(12, 6))
    # Removed markers (dots) – now a clean line only
    plt.plot(dates, values, marker='', linestyle='-', linewidth=2)
    plt.title(f'Account Balance (USDT) over time - {symbol}')
    plt.xlabel('Time')
    plt.ylabel('Total Value (USDT)')
    plt.grid(True)
    plt.xticks(rotation=45)
    
    # Format x-axis as time
    plt.gca().xaxis.set_major_formatter(DateFormatter('%H:%M:%S'))
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.tight_layout()
    
    # Save to PNG in memory
    img_data = BytesIO()
    plt.savefig(img_data, format='png', dpi=100)
    img_data.seek(0)
    plt.close()
    
    img_b64 = base64.b64encode(img_data.read()).decode('utf-8')
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Trade Report - {symbol}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; }}
        .stats {{ display: flex; flex-wrap: wrap; gap: 20px; margin: 20px 0; }}
        .stat-box {{ background: #e8f0fe; padding: 15px; border-radius: 5px; flex: 1; min-width: 120px; }}
        .stat-box .label {{ font-size: 14px; color: #555; }}
        .stat-box .value {{ font-size: 22px; font-weight: bold; }}
        .profit {{ color: green; }}
        .loss {{ color: red; }}
        img {{ max-width: 100%; height: auto; margin-top: 20px; border: 1px solid #ddd; border-radius: 4px; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Trade Report: {symbol}</h1>
    <div class="stats">
        <div class="stat-box"><span class="label">Start Balance</span><div class="value">{start_val:.2f} USDT</div></div>
        <div class="stat-box"><span class="label">End Balance</span><div class="value">{end_val:.2f} USDT</div></div>
        <div class="stat-box"><span class="label">Profit / Loss</span>
            <div class="value { 'profit' if profit >= 0 else 'loss' }">{profit:+.2f} USDT ({profit_pct:+.2f}%)</div>
        </div>
        <div class="stat-box"><span class="label">Total Trades</span><div class="value">{total_trades}</div></div>
        <div class="stat-box"><span class="label">Total Fees</span><div class="value">{total_fees_usdt:.2f} USDT</div></div>
    </div>
    <h2>Balance Chart</h2>
    <img src="data:image/png;base64,{img_b64}" alt="Balance Chart">
    <div class="footer">Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
</body>
</html>"""
    
    # Write HTML with UTF-8 encoding to handle emojis
    with open("trade_report.html", "w", encoding='utf-8') as f:
        f.write(html_content)
    with open("balance_chart.png", "wb") as f:
        f.write(base64.b64decode(img_b64))
    print("Report saved as trade_report.html (and balance_chart.png)")

def main():
    global total_fees_usdt, total_trades, start_time, end_time
    symbol = input("Enter symbol (e.g., BTC): ").strip().upper()
    token = input("Enter API token: ").strip()
    if not symbol or not token:
        print(json.dumps({"error": "Symbol and token are required"}))
        sys.exit(1)

    print("\nStarting perpetual bot...")
    print(f"Profit target: +{PROFIT_THRESHOLD*100:.2f}%")
    print(f"Buy triggers after sell: drop 0.5% (15 USDT) or pump 0.25% (7.5 USDT)")
    print(f"Trading fee: {FEE_RATE*100:.2f}% per trade")
    print("Press Ctrl+C at any time to exit (will place a limit sell if holding).\n")

    record_balance(token, symbol, force=True)

    holding = False
    current_order = None

    print("Placing initial buy order...")
    buy_resp = market_buy(token, symbol, BUY_AMOUNT_USDT)
    if not buy_resp.get("success"):
        print("Initial buy failed:", json.dumps(buy_resp, indent=2))
        sys.exit(1)

    coin_received = buy_resp["coinReceived"]
    buy_price = buy_resp["price"]
    order_id = buy_resp["orderId"]
    fee_usdt = BUY_AMOUNT_USDT * FEE_RATE
    total_fees_usdt += fee_usdt
    print(f"Buy done: {coin_received:.6f} {symbol} @ {buy_price:.6f}")
    print(f"Fee (0.55%): {fee_usdt:.6f} USDT, net spent: {BUY_AMOUNT_USDT - fee_usdt:.6f} USDT")
    save_order({
        "symbol": symbol,
        "timestamp": time.time(),
        "orderId": order_id,
        "price": buy_price,
        "coinReceived": coin_received,
        "amount_usdt": BUY_AMOUNT_USDT,
        "exchange-status": buy_resp.get("status"),
        "sell-status": "?",
        "buy_trigger": "initial"
    })
    holding = True
    current_order = {
        "buy_price": buy_price,
        "coin_received": coin_received,
        "order_id": order_id,
        "symbol": symbol,
        "token": token,
        "buy_amount": BUY_AMOUNT_USDT
    }

    try:
        while True:
            print(f"\nHolding {coin_received:.6f} {symbol}, waiting for +{PROFIT_THRESHOLD*100:.2f}% profit...")
            target_price = buy_price * (1 + PROFIT_THRESHOLD)
            sell_price = wait_for_price_condition(
                token, symbol, buy_price,
                lambda curr, ref: curr >= ref * (1 + PROFIT_THRESHOLD),
                f"price >= {target_price:.6f} (profit target)"
            )
            print(f"Profit target reached at {sell_price:.6f}!")

            print(f"Selling {coin_received:.6f} {symbol}...")
            sell_resp = market_sell(token, symbol, coin_received)
            if not sell_resp.get("success"):
                print("Sell failed:", json.dumps(sell_resp, indent=2))
                print("Exiting.")
                sys.exit(1)
            gross_usdt = coin_received * sell_price
            fee_usdt = gross_usdt * FEE_RATE
            total_fees_usdt += fee_usdt
            net_usdt = gross_usdt - fee_usdt
            print(f"Sell successful at {sell_price:.6f}")
            print(f"Gross: {gross_usdt:.6f} USDT, Fee: {fee_usdt:.6f} USDT, Net: {net_usdt:.6f} USDT")
            update_sell_status(order_id, "done")

            holding = False
            current_order = None
            actual_sell_price = sell_resp.get("price", sell_price)
            print(f"Executed sell price: {actual_sell_price:.6f}")

            trigger_type, trigger_price, buy_amount = wait_for_buy_condition(token, symbol, actual_sell_price)
            print(f"Triggered by {trigger_type} at {trigger_price:.6f} -> buying {buy_amount} USDT")

            buy_resp = market_buy(token, symbol, buy_amount)
            if not buy_resp.get("success"):
                print("Buy failed:", json.dumps(buy_resp, indent=2))
                print("Exiting.")
                sys.exit(1)

            coin_received = buy_resp["coinReceived"]
            buy_price = buy_resp["price"]
            order_id = buy_resp["orderId"]
            fee_usdt = buy_amount * FEE_RATE
            total_fees_usdt += fee_usdt
            print(f"Buy done: {coin_received:.6f} {symbol} @ {buy_price:.6f}")
            print(f"Fee (0.55%): {fee_usdt:.6f} USDT, net spent: {buy_amount - fee_usdt:.6f} USDT")
            save_order({
                "symbol": symbol,
                "timestamp": time.time(),
                "orderId": order_id,
                "price": buy_price,
                "coinReceived": coin_received,
                "amount_usdt": buy_amount,
                "exchange-status": buy_resp.get("status"),
                "sell-status": "?",
                "buy_trigger": trigger_type
            })
            holding = True
            current_order = {
                "buy_price": buy_price,
                "coin_received": coin_received,
                "order_id": order_id,
                "symbol": symbol,
                "token": token,
                "buy_amount": buy_amount
            }

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        record_balance(token, symbol, force=True)
        end_time = time.time()

        if holding and current_order is not None:
            print("Currently holding an open order. Placing a limit sell at target profit price...")
            target_price = current_order["buy_price"] * (1 + PROFIT_THRESHOLD)
            coin_amount = current_order["coin_received"]
            order_id = current_order["order_id"]
            print(f"Placing limit sell: {coin_amount:.6f} {symbol} @ {target_price:.6f}")
            limit_resp = limit_sell(token, symbol, target_price, coin_amount)
            if "orderId" in limit_resp and "status" in limit_resp:
                print("Limit sell order placed successfully.")
                print(json.dumps(limit_resp, indent=2))
                gross_usdt = coin_amount * target_price
                fee_usdt = gross_usdt * FEE_RATE
                total_fees_usdt += fee_usdt
                net_usdt = gross_usdt - fee_usdt
                print(f"Estimated fee: {fee_usdt:.6f} USDT, estimated net: {net_usdt:.6f} USDT")
                update_sell_status(order_id, "limit-sell-placed")
                print("Limit sell order is pending.")
            else:
                print("Failed to place limit sell order:", json.dumps(limit_resp, indent=2))
        else:
            print("No open order to sell.")

        print("\nGenerating report...")
        generate_report(balance_history, symbol, start_time, end_time, total_trades, total_fees_usdt)
        print("Report generated. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()