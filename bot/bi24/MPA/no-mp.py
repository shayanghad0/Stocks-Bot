import os
import hmac
import hashlib
import time
import sys
import itertools
import json
from datetime import datetime

import requests
from dotenv import load_dotenv
import jdatetime


load_dotenv()

API_KEY = os.getenv("BIT24_API_KEY")
SECRET_KEY = os.getenv("BIT24_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    raise ValueError("API_KEY and SECRET_KEY must be set in .env file")

BASE_URL = "https://rest.bit24.cash"
PROFIT_THRESHOLD = 0.0275
TRIGGER_THRESHOLD = 0.005

# Shared state for Ctrl+C handler
_bot_state = {}


# ---------- Ctrl+C exports ----------
def export_html(filename):
    iran_date = get_iran_date()
    trade_file = f"trade-{iran_date}.json"
    if not os.path.exists(trade_file):
        print("  No trade file found for HTML export.")
        return None

    with open(trade_file, "r", encoding="utf-8") as f:
        trades = json.load(f)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Report - {iran_date}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 20px; }}
  h1 {{ text-align: center; color: #00e676; margin-bottom: 8px; font-size: 28px; }}
  .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 14px; }}
  .summary {{ display: flex; justify-content: center; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }}
  .card {{ background: #1a1a2e; border-radius: 12px; padding: 18px 28px; text-align: center; min-width: 160px; border: 1px solid #333; }}
  .card .label {{ color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 6px; }}
  .card .value {{ font-size: 24px; font-weight: bold; }}
  .card .value.green {{ color: #00e676; }}
  .card .value.red {{ color: #ff5252; }}
  .card .value.blue {{ color: #42a5f5; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th {{ background: #1a1a2e; color: #00e676; padding: 12px 10px; text-align: left; font-size: 12px; text-transform: uppercase; border-bottom: 2px solid #333; }}
  td {{ padding: 10px; border-bottom: 1px solid #222; font-size: 13px; }}
  tr:hover {{ background: #1a1a2e; }}
  .status-buy {{ color: #00e676; font-weight: bold; }}
  .status-sell {{ color: #ff5252; font-weight: bold; }}
  .status-hold {{ color: #ffc107; font-weight: bold; }}
  .pnl-pos {{ color: #00e676; }}
  .pnl-neg {{ color: #ff5252; }}
  .footer {{ text-align: center; color: #555; margin-top: 30px; font-size: 12px; }}
</style>
</head>
<body>
<h1>Trading Report</h1>
<p class="subtitle">{iran_date} | Generated at {datetime.now().strftime("%H:%M:%S")}</p>
"""

    total_buys = 0
    total_sells = 0
    total_fee = 0
    total_pnl = 0
    for t in trades:
        total_buys += t.get("amount_currency", 0)
        total_fee += t.get("fee", 0) + t.get("sell_fee", 0)
        if t.get("sell-status") == "sell":
            total_sells += t.get("coinReceived", 0) * t.get("sell_price", 0)
            pnl = (t.get("sell_price", 0) - t.get("price", 0)) * t.get("coinReceived", 0)
            total_pnl += pnl - t.get("fee", 0) - t.get("sell_fee", 0)

    end_balance = _bot_state.get("end_balance", 0)
    start_balance = _bot_state.get("start_balance", 0)

    html += f"""<div class="summary">
  <div class="card"><div class="label">Total Trades</div><div class="value blue">{len(trades)}</div></div>
  <div class="card"><div class="label">Total Bought</div><div class="value blue">{total_buys:.2f}</div></div>
  <div class="card"><div class="label">Total Fees</div><div class="value red">{total_fee:.2f}</div></div>
  <div class="card"><div class="label">Total P&L</div><div class="value {'green' if total_pnl >= 0 else 'red'}">{total_pnl:+.2f}</div></div>
  <div class="card"><div class="label">End Balance</div><div class="value blue">{end_balance:.2f}</div></div>
</div>
"""

    html += """<table>
<tr>
  <th>#</th><th>Symbol</th><th>Side</th><th>Trigger</th>
  <th>Buy Price</th><th>Sell Price</th><th>Coin</th>
  <th>Spent</th><th>Received</th><th>Buy Fee</th><th>Sell Fee</th>
  <th>P&L</th><th>Status</th><th>Time</th>
</tr>
"""
    for t in trades:
        sell_p = t.get("sell_price")
        buy_fee = t.get("fee", 0)
        sell_fee = t.get("sell_fee", 0)
        coin = t.get("coinReceived", 0)
        spent = t.get("received_currency", 0)
        sell_status = t.get("sell-status", "?")
        trigger = t.get("buy_trigger", "?")

        if sell_p:
            pnl = (sell_p - t["price"]) * coin - buy_fee - sell_fee
            pnl_cls = "pnl-pos" if pnl >= 0 else "pnl-neg"
            pnl_str = f"{pnl:+.2f}"
        else:
            pnl_cls = ""
            pnl_str = "---"

        side_cls = "status-sell" if sell_status == "sell" else "status-hold"
        side_text = "SELL" if sell_status == "sell" else "HOLD"

        ts = t.get("timestamp", 0)
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "---"

        html += f"""<tr>
  <td>{t.get('ID','')}</td>
  <td>{t.get('symbol','')}</td>
  <td class="{side_cls}">{side_text}</td>
  <td>{trigger}</td>
  <td>{t.get('price',0):.8f}</td>
  <td>{sell_p:.8f if sell_p else '---'}</td>
  <td>{coin:.2f}</td>
  <td>{spent:.2f}</td>
  <td>{(coin * sell_p):.2f if sell_p else '---'}</td>
  <td>{buy_fee:.2f}</td>
  <td>{sell_fee:.2f}</td>
  <td class="{pnl_cls}">{pnl_str}</td>
  <td class="{side_cls}">{sell_status}</td>
  <td>{time_str}</td>
</tr>
"""
    html += """</table>
<p class="footer">Generated by Trading Bot | Bit24</p>
</body></html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML report saved: {filename}")
    return filename


# ---------- Animation helpers ----------
def animated_input(prompt_text, frames=[">._.<", ">__.__<", ">._.<", ">.__.<"], cycles=8, delay=0.08):
    spinner = itertools.cycle(frames)
    sys.stdout.write(prompt_text)
    sys.stdout.flush()
    for _ in range(cycles):
        sys.stdout.write("\r" + prompt_text + next(spinner) + " ")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\r" + prompt_text + ">._.< : ")
    sys.stdout.flush()
    return input()


def spinner(text, duration=1.0, frames=None):
    if frames is None:
        frames = ["|", "/", "-", "\\"]
    cycle = itertools.cycle(frames)
    end = time.time() + duration
    while time.time() < end:
        sys.stdout.write(f"\r{text} {next(cycle)}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * (len(text) + 4) + "\r")


# ---------- Bit24 API helpers ----------
def generate_signature(params: dict, secret: str) -> str:
    filtered = {k: v for k, v in params.items() if v is not None}
    sorted_items = sorted(filtered.items())
    query_string = "&".join(f"{k}={v}" for k, v in sorted_items)
    signature = hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature


def get_asset(symbol: str) -> dict:
    url = f"{BASE_URL}/asset/capi/v1/wallet/assets"
    headers = {"Accept": "application/json", "X-BIT24-APIKEY": API_KEY}
    params = {"name": symbol}
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    if not data.get("success"):
        raise Exception(f"Asset API {resp.status_code}: {data.get('error', {}).get('message', 'Unknown')}")
    return data["data"]


def get_asset_balance(symbol: str) -> str:
    data = get_asset(symbol)
    assets = data.get("asset", [])
    if not assets:
        raise ValueError(f"Asset {symbol} not found")
    return assets[0].get("balance", "0")


def get_available_balance(symbol: str) -> float:
    """Get the available (tradeable) balance from exchange API, not the local estimate."""
    data = get_asset(symbol)
    assets = data.get("asset", [])
    if not assets:
        return 0.0
    return float(assets[0].get("available_balance", "0"))


def check_market(symbol: str, quote: str) -> bool:
    data = get_asset(symbol)
    assets = data.get("asset", [])
    if not assets:
        return False
    markets = assets[0].get("markets", [])
    for m in markets:
        if m.get("base_coin_symbol") == symbol and m.get("quote_coin_symbol") == quote:
            return True
    return False


def submit_order(base_symbol: str, quote_symbol: str, side: int, order_type: int,
                 amount: str, amount_coin_symbol: str = None) -> dict:
    url = f"{BASE_URL}/pro/capi/v2/spot-orders/submit"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-BIT24-APIKEY": API_KEY,
    }
    params = {
        "base_coin_symbol": base_symbol,
        "quote_coin_symbol": quote_symbol,
        "side": side,
        "type": order_type,
        "amount": amount,
    }
    if order_type == 1 and amount_coin_symbol:
        params["amount_coin_symbol"] = amount_coin_symbol

    # اگر سفارش لیمیت باشد، قیمت باید ارسال شود (در کد فعلی از مارکت استفاده می‌کنیم)
    # اما برای کامل شدن، می‌توان price را هم اضافه کرد.

    signature = generate_signature(params, SECRET_KEY)
    params["signature"] = signature

    resp = requests.post(url, headers=headers, data=params)
    data = resp.json()
    if not data.get("success"):
        error_msg = data.get("error", {}).get("message", "Unknown error")
        raise Exception(f"API {resp.status_code}: {error_msg}")
    return data["data"]


def get_current_price(base_symbol: str, quote_symbol: str, session=None) -> float:
    if session is None:
        session = requests.Session()
    url = f"{BASE_URL}/pro/capi/v1/markets"
    headers = {"Accept": "application/json", "X-BIT24-APIKEY": API_KEY}
    try:
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json()
        if not data.get("success"):
            return None
        for m in data["data"]["results"]:
            if m["base_coin_symbol"].upper() == base_symbol.upper() and m["quote_coin_symbol"].upper() == quote_symbol.upper():
                return float(m["each_price"])
    except Exception:
        return None
    return None


# ---------- Trade saving helpers ----------
def get_iran_date():
    return jdatetime.datetime.now().strftime("%Y-%m-%d")


def get_next_id(trades):
    if not trades:
        return 1
    return max(trade.get("ID", 0) for trade in trades) + 1


def save_trade_record(symbol, quote, order_id, buy_price, coin_received, amount_currency, fee, buy_trigger="initial"):
    iran_date = get_iran_date()
    filename = f"trade-{iran_date}.json"

    trades = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                trades = json.load(f)
            except json.JSONDecodeError:
                trades = []

    new_id = get_next_id(trades)
    timestamp = int(time.time())
    received_currency = amount_currency - fee

    record = {
        "ID": new_id,
        "symbol": symbol,
        "timestamp": timestamp,
        "orderId": order_id,
        "price": buy_price,
        "coinReceived": coin_received,
        "amount_currency": amount_currency,
        "fee": fee,
        "received_currency": received_currency,
        "exchange-status": "completed",
        "sell-status": "?",
        "buy_trigger": buy_trigger
    }
    trades.append(record)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)

    print(f"Trade saved to {filename}")
    return filename


def update_sell_status(order_id, symbol, quote, sell_status, sell_price, sell_fee):
    iran_date = get_iran_date()
    filename = f"trade-{iran_date}.json"

    if not os.path.exists(filename):
        return False

    with open(filename, "r", encoding="utf-8") as f:
        try:
            trades = json.load(f)
        except json.JSONDecodeError:
            return False

    updated = False
    for trade in trades:
        if trade.get("orderId") == order_id and trade.get("symbol") == symbol:
            trade["sell-status"] = sell_status
            trade["sell_price"] = sell_price
            trade["sell_fee"] = sell_fee
            updated = True
            break

    if updated:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)

    return updated


def get_trade_count():
    iran_date = get_iran_date()
    filename = f"trade-{iran_date}.json"
    if not os.path.exists(filename):
        return 0
    with open(filename, "r", encoding="utf-8") as f:
        try:
            trades = json.load(f)
            return len(trades)
        except (json.JSONDecodeError, ValueError):
            return 0


def do_buy(symbol, quote, amount, buy_price, fee_rate, trigger_type, amount_str=None):
    fee = amount * fee_rate
    received_currency = amount - fee

    if amount_str is None:
        amount_str = str(int(amount)) if amount == int(amount) else str(amount)

    result = submit_order(
        base_symbol=symbol,
        quote_symbol=quote,
        side=1,          # خرید
        order_type=1,    # مارکت
        amount=amount_str,
        amount_coin_symbol=quote
    )
    order_data = result.get("spot_order", {})
    order_id = order_data.get("id")
    if not order_id:
        return None

    # Wait for exchange to settle the order, then fetch real balance
    print("  Waiting 10s for balance to settle...")
    time.sleep(10)
    real_balance = get_available_balance(symbol)
    print(f"  Real balance from exchange: {real_balance} {symbol}")

    save_trade_record(symbol, quote, order_id, buy_price, real_balance, amount, fee, trigger_type)
    return {
        "order_id": order_id,
        "buy_price": buy_price,
        "coin_received": real_balance,
        "amount": amount,
        "fee": fee,
        "received_currency": received_currency
    }


def do_sell(symbol, quote, coin_received, sell_price, fee_rate):
    # Fetch real balance from exchange — don't trust local estimate
    real_balance = get_available_balance(symbol)
    if real_balance <= 0:
        raise Exception(f"Insufficient balance: {real_balance} {symbol}")

    sell_fee = real_balance * sell_price * fee_rate
    coin_to_sell = str(real_balance)

    # 🔥 FIX: side باید 0 باشد برای فروش (نه 2)
    result = submit_order(
        base_symbol=symbol,
        quote_symbol=quote,
        side=0,          # فروش
        order_type=1,    # مارکت
        amount=coin_to_sell,
        amount_coin_symbol=symbol
    )
    order_data = result.get("spot_order", {})
    sell_order_id = order_data.get("id", "unknown")

    return {
        "sell_order_id": sell_order_id,
        "sell_price": sell_price,
        "sell_fee": sell_fee,
        "real_balance_sold": real_balance
    }


# ---------- Price monitor display ----------
def build_display(counter, current_price, trade, reference_price, mode,
                   start_time, spinner_frame, symbol, quote, high_price, low_price,
                   total_trades):
    elapsed = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    hrs, mins = divmod(mins, 60)

    green = "\033[92m"
    red = "\033[91m"
    gray = "\033[90m"
    yellow = "\033[93m"
    cyan = "\033[96m"
    magenta = "\033[95m"
    bold = "\033[1m"
    reset = "\033[0m"

    buy_price = trade["buy_price"] if trade else None
    coin_received = trade["coin_received"] if trade else 0
    fee = trade["fee"] if trade else 0
    received_currency = trade["received_currency"] if trade else 0
    amount = trade["amount"] if trade else 0

    lines = []
    lines.append(f" {bold}{symbol}/{quote} TRADING BOT{reset}  {magenta}[{mode.upper()}]{reset}  {cyan}Trades: {total_trades}{reset}")
    lines.append("")

    # Price section
    lines.append(f"  Buy Price   : {buy_price:.8f}" if buy_price else "  Buy Price   : ---")
    lines.append(f"  Current     : {current_price:.8f}" if current_price else "  Current     : ---")

    # P&L from buy
    if current_price and buy_price:
        change = ((current_price - buy_price) / buy_price) * 100
        direction = "\u25b2" if change > 0 else "\u25bc" if change < 0 else "\u2500"
        color = green if change > 0 else red if change < 0 else gray
        lines.append(f"  P&L %       : {color}{direction} {change:+.4f}%{reset}")
        pnl = (current_price - buy_price) * coin_received
        pnl_color = green if pnl > 0 else red if pnl < 0 else gray
        lines.append(f"  P&L {quote}    : {pnl_color}{pnl:+.2f} {quote}{reset}")
    else:
        lines.append("  P&L %       : ---")
        lines.append(f"  P&L {quote}    : ---")

    lines.append("")

    # Holdings
    lines.append(f"  {yellow}--- Holdings ---{reset}")
    lines.append(f"  Coin Held   : {coin_received:.2f} {symbol}" if coin_received else f"  Coin Held   : 0.00 {symbol}")
    if current_price and coin_received:
        current_value = coin_received * current_price
        lines.append(f"  Value Now   : {current_value:.2f} {quote}")
    else:
        lines.append(f"  Value Now   : ---")
    lines.append(f"  Spent       : {received_currency:.2f} {quote}" if received_currency else f"  Spent       : 0.00 {quote}")
    lines.append(f"  Fee (0.25%) : {fee:.2f} {quote}" if fee else f"  Fee (0.25%) : 0.00 {quote}")
    lines.append("")

    # Reference price and triggers
    lines.append(f"  {cyan}--- Targets ---{reset}")
    if reference_price:
        lines.append(f"  Sell Ref    : {reference_price:.8f}")
        pump_trigger = reference_price * (1 + TRIGGER_THRESHOLD)
        drop_trigger = reference_price * (1 - TRIGGER_THRESHOLD)
        lines.append(f"  Pump Buy >  : {pump_trigger:.8f} (+0.5%)")
        lines.append(f"  Drop Buy <  : {drop_trigger:.8f} (-0.5%)")
    if buy_price:
        tp_price = buy_price * (1 + PROFIT_THRESHOLD)
        lines.append(f"  TP Price    : {tp_price:.8f} (+{PROFIT_THRESHOLD*100:.2f}%)")
    if not reference_price and not buy_price:
        lines.append(f"  Waiting     : after sell...")
    lines.append("")

    # Session
    lines.append(f"  {magenta}--- Session ---{reset}")
    if high_price:
        lines.append(f"  High        : {high_price:.8f}")
    else:
        lines.append(f"  High        : ---")
    if low_price:
        lines.append(f"  Low         : {low_price:.8f}")
    else:
        lines.append(f"  Low         : ---")
    if high_price and low_price and high_price > 0:
        volatility = ((high_price - low_price) / high_price) * 100
        lines.append(f"  Volatility  : {volatility:.4f}%")

    lines.append("")
    lines.append(f"  Requests    : {counter}")
    lines.append(f"  Uptime      : {hrs:02d}:{mins:02d}:{secs:02d}")
    lines.append("")
    lines.append(f"  Status      : {spinner_frame}  {mode}")
    lines.append("")
    lines.append("  Press Ctrl+C to stop")
    return lines


def render(lines, width=60):
    top = "\u2554" + "\u2550" * (width - 2) + "\u2557"
    bot = "\u255a" + "\u2550" * (width - 2) + "\u255d"
    output = [top]
    for line in lines:
        stripped = line.replace("\033[0m", "").replace("\033[92m", "").replace("\033[91m", "").replace("\033[90m", "").replace("\033[93m", "").replace("\033[96m", "").replace("\033[1m", "")
        pad = width - 4 - len(stripped)
        if pad < 0:
            pad = 0
        output.append("\u2551 " + line + " " * pad + " \u2551")
    output.append(bot)
    return "\n".join(output)


# ---------- Main ----------
def main():
    symbol = animated_input(
        "Please Input your Symbol (BTC | ADA | ETH | TRX | ... ) : ",
        frames=[">._.<", ">__.__<", ">._.<", ">.__.<"], cycles=8, delay=0.07
    ).strip().upper()

    quote = animated_input(
        "Please Input your currency (IRT | USDT) : ",
        frames=[">._.<", ">__.__<", ">._.<", ">.__.<"], cycles=8, delay=0.07
    ).strip().upper()

    amount_str = animated_input(
        "Please Input How Much You want to buy (min buy is 50000 IRT Or 5 USDT) : ",
        frames=[">._.<", ">__.__<", ">._.<", ">.__.<"], cycles=8, delay=0.07
    ).strip()

    try:
        amount = float(amount_str)
    except ValueError:
        print("Invalid amount. Please enter a number.")
        return

    if quote == "IRT" and amount < 50000:
        print("Minimum buy for IRT is 50000.")
        return
    elif quote == "USDT" and amount < 5:
        print("Minimum buy for USDT is 5.")
        return
    elif quote not in ["IRT", "USDT"]:
        print("Currency must be IRT or USDT.")
        return

    print(f"Checking market {symbol}/{quote}...")
    spinner("Checking", duration=1.0)
    try:
        market_exists = check_market(symbol, quote)
    except Exception as e:
        print(f"Failed to check market: {e}")
        return

    if not market_exists:
        print(f"Market {symbol}/{quote} does not exist.")
        return

    FEE_RATE = 0.0025

    # Store state for Ctrl+C handler
    _bot_state["symbol"] = symbol
    _bot_state["quote"] = quote
    _bot_state["amount"] = amount
    _bot_state["start_balance"] = amount
    _bot_state["fee_rate"] = FEE_RATE

    # ---- Initial buy ----
    print(f"Market {symbol}/{quote} exists. Placing initial buy...")
    buy_price = get_current_price(symbol, quote)
    if buy_price is None:
        print("Could not fetch current price. Aborting.")
        return

    trade = do_buy(symbol, quote, amount, buy_price, FEE_RATE, "initial", amount_str)
    if not trade:
        print("Buy order failed.")
        return

    _bot_state["trade"] = trade
    total_trades = get_trade_count()

    print("\nOrder placed successfully!")
    print(f"   Order ID     : {trade['order_id']}")
    print(f"   Buy Price    : {trade['buy_price']}")
    print(f"   Fee (0.25%)  : {trade['fee']:.2f} {quote}")
    print(f"   Coin Received: {trade['coin_received']}")
    print(f"\nStarting trading bot. Press Ctrl+C to stop.\n")
    time.sleep(1)
    os.system("cls" if os.name == "nt" else "clear")

    session = requests.Session()
    counter = 0
    start_time = time.time()
    high_price = None
    low_price = None
    reference_price = None
    mode = "monitoring_sell"
    spinner_frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    spinner_cycle = itertools.cycle(spinner_frames)

    while True:
        current_price = get_current_price(symbol, quote, session)
        counter += 1
        current_spinner = next(spinner_cycle)

        if current_price is not None:
            if high_price is None or current_price > high_price:
                high_price = current_price
            if low_price is None or current_price < low_price:
                low_price = current_price

        # --- MODE: monitoring_sell - wait for +2.75% to sell ---
        if mode == "monitoring_sell" and current_price and trade:
            buy_p = trade["buy_price"]
            pnl_pct = ((current_price - buy_p) / buy_p) * 100

            if pnl_pct >= PROFIT_THRESHOLD * 100:
                sys.stdout.write("\033[H")
                sys.stdout.write(render(build_display(
                    counter, current_price, trade, reference_price, mode,
                    start_time, current_spinner, symbol, quote, high_price, low_price,
                    total_trades
                )))
                sys.stdout.flush()

                spinner("SELLING - Profit target reached!", duration=1.5)
                try:
                    sell = do_sell(symbol, quote, trade["coin_received"], current_price, FEE_RATE)
                    update_sell_status(trade["order_id"], symbol, quote, "sell",
                                       sell["sell_price"], sell["sell_fee"])

                    os.system("cls" if os.name == "nt" else "clear")
                    green = "\033[92m"
                    bold = "\033[1m"
                    reset = "\033[0m"
                    print(f"\n{green}{bold}  AUTO SELL TRIGGERED!{reset}")
                    print(f"  {green}Profit target: +{PROFIT_THRESHOLD*100:.2f}% reached{reset}")
                    print(f"")
                    print(f"  Buy Price     : {trade['buy_price']:.8f}")
                    print(f"  Sell Price    : {sell['sell_price']:.8f}")
                    print(f"  Coin Sold     : {sell['real_balance_sold']:.2f} {symbol}")
                    print(f"  Sell Fee      : {sell['sell_fee']:.2f} {quote}")
                    print(f"  Sell Order ID : {sell['sell_order_id']}")
                    print(f"  sell-status   : sell")
                    print(f"")
                    print(f"  Now waiting for pump/drop trigger to buy again...")
                    print(f"")

                    reference_price = sell["sell_price"]
                    trade = None
                    _bot_state["trade"] = None
                    mode = "waiting_trigger"
                    high_price = None
                    low_price = None
                    time.sleep(1)
                    os.system("cls" if os.name == "nt" else "clear")
                    continue
                except Exception as e:
                    print(f"\n  SELL ORDER FAILED: {e}")
                    print(f"  Continuing to monitor...\n")

        # --- MODE: waiting_trigger - after sell, wait for +0.5% or -0.5% ---
        if mode == "waiting_trigger" and current_price and reference_price:
            pump_level = reference_price * (1 + TRIGGER_THRESHOLD)
            drop_level = reference_price * (1 - TRIGGER_THRESHOLD)

            triggered = None
            if current_price >= pump_level:
                triggered = "pump"
            elif current_price <= drop_level:
                triggered = "drop"

            if triggered:
                sys.stdout.write("\033[H")
                sys.stdout.write(render(build_display(
                    counter, current_price, trade, reference_price, mode,
                    start_time, current_spinner, symbol, quote, high_price, low_price,
                    total_trades
                )))
                sys.stdout.flush()

                trigger_label = "PUMP +0.5%" if triggered == "pump" else "DROP -0.5%"
                spinner(f"BUYING - {trigger_label} detected!", duration=1.5)
                try:
                    new_trade = do_buy(symbol, quote, amount, current_price, FEE_RATE, triggered, amount_str)
                    if new_trade:
                        total_trades = get_trade_count()
                        os.system("cls" if os.name == "nt" else "clear")
                        green = "\033[92m"
                        yellow = "\033[93m"
                        bold = "\033[1m"
                        reset = "\033[0m"
                        print(f"\n{yellow}{bold}  AUTO BUY TRIGGERED!{reset}")
                        print(f"  {yellow}{trigger_label}{reset}")
                        print(f"")
                        print(f"  Reference     : {reference_price:.8f}")
                        print(f"  Buy Price     : {new_trade['buy_price']:.8f}")
                        print(f"  Coin Received : {new_trade['coin_received']:.2f} {symbol}")
                        print(f"  Fee           : {new_trade['fee']:.2f} {quote}")
                        print(f"  Order ID      : {new_trade['order_id']}")
                        print(f"  Total Trades  : {total_trades}")
                        print(f"")
                        print(f"  Now waiting for +2.75% to sell...")
                        print(f"")

                        trade = new_trade
                        _bot_state["trade"] = new_trade
                        reference_price = None
                        mode = "monitoring_sell"
                        high_price = None
                        low_price = None
                        time.sleep(1)
                        os.system("cls" if os.name == "nt" else "clear")
                        continue
                except Exception as e:
                    print(f"\n  BUY ORDER FAILED: {e}")
                    print(f"  Continuing to wait...\n")

        lines = build_display(
            counter, current_price, trade, reference_price, mode,
            start_time, current_spinner, symbol, quote, high_price, low_price,
            total_trades
        )
        display = render(lines)

        sys.stdout.write("\033[H")
        sys.stdout.write(display)
        sys.stdout.flush()

        time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\033[0m")
        print("\n  Ctrl+C pressed. Shutting down...\n")

        symbol = _bot_state.get("symbol")
        quote = _bot_state.get("quote")
        trade = _bot_state.get("trade")
        amount = _bot_state.get("amount", 0)
        fee_rate = _bot_state.get("fee_rate", 0.0025)

        # --- 1. If holding coin, sell at current price ---
        if trade and symbol and quote:
            print("  [1/3] Selling held coins at current price...")
            current = get_current_price(symbol, quote)
            if current:
                try:
                    sell = do_sell(symbol, quote, trade["coin_received"], current, fee_rate)
                    update_sell_status(trade["order_id"], symbol, quote, "sell",
                                       sell["sell_price"], sell["sell_fee"])
                    print(f"        Sold {sell['real_balance_sold']:.2f} {symbol} at {current:.8f}")
                    print(f"        Sell Fee: {sell['sell_fee']:.2f} {quote}")
                except Exception as e:
                    print(f"        Sell failed: {e}")
            else:
                print("        Could not fetch current price. Sell skipped.")
        else:
            print("  [1/3] No coin held. Nothing to sell.")

        # --- 2. Export HTML ---
        print("\n  [2/3] Generating HTML report...")
        iran_date = get_iran_date()
        html_file = f"trade-{iran_date}.html"
        export_html(html_file)

        # --- 3. Save end balance ---
        if quote:
            try:
                balance = get_asset_balance(quote)
                _bot_state["end_balance"] = float(balance)
                print(f"  [3/3] End balance: {balance} {quote}")
            except Exception as e:
                print(f"  [3/3] Could not fetch balance: {e}")

        print(f"\n  Done. Goodbye!\n")