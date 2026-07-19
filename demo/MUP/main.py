#!/usr/bin/env python3
"""
Grid Trading Bot with:
- Real‑time dashboard (Rich)
- JSON persistence (auto‑save)
- On exit: limit sell order at avg buy + 1.5%
- On exit: portfolio chart (PNG)
- On exit: HTML trade report
"""

import requests
import time
import sys
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import threading

# Rich for the dashboard
try:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.console import Console
    from rich import box
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("This script requires the 'rich' library for the dashboard.")
    print("Install it with: pip install rich")
    sys.exit(1)

# Try to import matplotlib for charting
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("matplotlib not installed – chart will be skipped. Install with: pip install matplotlib")

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
BASE_URL = "http://localhost:3001"
DROP_THRESHOLD = 0.005               # 0.5% drop to reset
STATE_DIR = "grid_bot_states"
HISTORY_INTERVAL = 30                # seconds between portfolio snapshots

os.makedirs(STATE_DIR, exist_ok=True)

# ------------------------------------------------------------
# API Functions
# ------------------------------------------------------------
def get_price(symbol: str) -> float:
    url = f"{BASE_URL}/api/stats/{symbol}"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    return float(data['last_price'])

def get_balance(token: str) -> Dict:
    url = f"{BASE_URL}/api/user/{token}/balance"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def buy_market(symbol: str, usdt_amount: float, token: str) -> float:
    before = get_balance(token)
    before_coin = before['coins'].get(symbol, 0.0)
    url = f"{BASE_URL}/api/user/{token}/spot/buy/market/{symbol}?amount={usdt_amount}"
    resp = requests.post(url)
    resp.raise_for_status()
    after = get_balance(token)
    after_coin = after['coins'].get(symbol, 0.0)
    filled = after_coin - before_coin
    if filled < 0:
        print(f"Warning: balance decreased? before={before_coin}, after={after_coin}")
        filled = 0.0
    return filled

def sell_market(symbol: str, coin_amount: float, token: str) -> None:
    url = f"{BASE_URL}/api/user/{token}/spot/sell/market/{symbol}?amount={coin_amount}"
    resp = requests.post(url)
    resp.raise_for_status()

def place_limit_sell(symbol: str, price: float, coin_amount: float, token: str) -> None:
    """Place a limit sell order at the given price for the given coin amount."""
    url = f"{BASE_URL}/api/user/{token}/spot/custom/sell/{price}/{symbol}?amount={coin_amount}"
    resp = requests.post(url)
    resp.raise_for_status()
    print(f"Limit sell order placed: {coin_amount:.6f} {symbol} @ {price:.2f}")

# ------------------------------------------------------------
# Persistence Helpers
# ------------------------------------------------------------
def get_state_filename(token: str, symbol: str) -> str:
    safe_token = token.replace("/", "_").replace("\\", "_")
    safe_symbol = symbol.replace("/", "_")
    return os.path.join(STATE_DIR, f"grid_bot_{safe_token}_{safe_symbol}.json")

def save_state(state: 'GridState', phase: str, max_price: Optional[float],
               history: List[Dict]):
    data = {
        'symbol': state.symbol,
        'grids': state.grids,
        'grid_percent': state.grid_percent,
        'amount_per_buy': state.amount_per_buy,
        'middle_index': state.middle_index,
        'all_levels': state.all_levels,
        'buy_levels': state.buy_levels,
        'sell_levels': state.sell_levels,
        'middle_level': state.middle_level,
        'buy_done': state.buy_done,
        'buy_quantities': state.buy_quantities,
        'buy_prices': state.buy_prices,
        'sell_done': state.sell_done,
        'sell_prices': state.sell_prices,
        'trades': state.trades,
        'phase': phase,
        'max_price_since_completion': max_price,
        'history': history,  # save history too
        'last_updated': datetime.now().isoformat()
    }
    filename = get_state_filename(state.token, state.symbol)
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def load_state(token: str, symbol: str) -> Optional[Dict]:
    filename = get_state_filename(token, symbol)
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return None

# ------------------------------------------------------------
# Grid State Management
# ------------------------------------------------------------
class GridState:
    def __init__(self, current_price: float, symbol: str, grids: int,
                 grid_percent: float, amount_per_buy: float, token: str,
                 loaded_state: Optional[Dict] = None):
        self.symbol = symbol
        self.token = token
        self.grids = grids
        self.grid_percent = grid_percent
        self.amount_per_buy = amount_per_buy
        self.middle_index = grids // 2

        if loaded_state:
            self.all_levels = loaded_state['all_levels']
            self.buy_levels = loaded_state['buy_levels']
            self.sell_levels = loaded_state['sell_levels']
            self.middle_level = loaded_state['middle_level']
            self.buy_done = loaded_state['buy_done']
            self.buy_quantities = loaded_state['buy_quantities']
            self.buy_prices = loaded_state['buy_prices']
            self.sell_done = loaded_state['sell_done']
            self.sell_prices = loaded_state['sell_prices']
            self.trades = loaded_state['trades']
            self.num_buys = len(self.buy_levels)
            self.num_sells = len(self.sell_levels)
            print(f"[LOAD] Resumed from saved state with {len(self.trades)} trades.")
        else:
            step = current_price * (grid_percent / 100.0)
            self.all_levels = [current_price + i * step for i in range(grids)]
            self.buy_levels = self.all_levels[:self.middle_index]
            self.middle_level = self.all_levels[self.middle_index]
            self.sell_levels = self.all_levels[self.middle_index + 1:]

            self.num_buys = len(self.buy_levels)
            self.num_sells = len(self.sell_levels)

            self.buy_done = [False] * self.num_buys
            self.buy_quantities = [None] * self.num_buys
            self.buy_prices = [None] * self.num_buys
            self.sell_done = [False] * self.num_sells
            self.sell_prices = [None] * self.num_sells
            self.trades = []

            self._initial_buy(current_price)

    def _initial_buy(self, price: float):
        print(f"\n[INIT] Buying at current price {price:.2f} ...")
        qty = buy_market(self.symbol, self.amount_per_buy, self.token)
        self.buy_quantities[0] = qty
        self.buy_prices[0] = price
        self.buy_done[0] = True
        self.trades.append({
            'type': 'buy',
            'price': price,
            'quantity': qty,
            'grid_idx': 0,
            'timestamp': datetime.now().isoformat()
        })
        print(f"Bought {qty:.8f} {self.symbol}")

    def reset(self, current_price: float):
        return GridState(current_price, self.symbol, self.grids,
                         self.grid_percent, self.amount_per_buy, self.token)

    def buy_at(self, grid_idx: int, price: float) -> bool:
        if self.buy_done[grid_idx]:
            return False
        try:
            qty = buy_market(self.symbol, self.amount_per_buy, self.token)
            self.buy_quantities[grid_idx] = qty
            self.buy_prices[grid_idx] = price
            self.buy_done[grid_idx] = True
            self.trades.append({
                'type': 'buy',
                'price': price,
                'quantity': qty,
                'grid_idx': grid_idx,
                'timestamp': datetime.now().isoformat()
            })
            return True
        except Exception as e:
            print(f"Buy failed at grid {grid_idx}: {e}")
            return False

    def sell_at(self, grid_idx: int, price: float) -> bool:
        if self.sell_done[grid_idx]:
            return False
        buy_idx = self.middle_index - 1 - grid_idx
        if buy_idx < 0 or self.buy_quantities[buy_idx] is None or self.buy_quantities[buy_idx] <= 0:
            return False
        qty = self.buy_quantities[buy_idx]
        try:
            sell_market(self.symbol, qty, self.token)
            self.sell_done[grid_idx] = True
            self.sell_prices[grid_idx] = price
            self.trades.append({
                'type': 'sell',
                'price': price,
                'quantity': qty,
                'grid_idx': grid_idx,
                'timestamp': datetime.now().isoformat()
            })
            return True
        except Exception as e:
            print(f"Sell failed at grid {grid_idx}: {e}")
            return False

    @property
    def all_actions_done(self) -> bool:
        return all(self.buy_done) and all(self.sell_done)

    def get_next_buy(self) -> Optional[int]:
        for i, done in enumerate(self.buy_done):
            if not done:
                return i
        return None

    def get_next_sell(self) -> Optional[int]:
        for i, done in enumerate(self.sell_done):
            if not done:
                buy_idx = self.middle_index - 1 - i
                if buy_idx >= 0 and self.buy_quantities[buy_idx] is not None and self.buy_quantities[buy_idx] > 0:
                    return i
        return None

    def compute_pnl(self) -> Tuple[float, float]:
        realized_pnl = 0.0
        for sell_trade in self.trades:
            if sell_trade['type'] == 'sell':
                sell_price = sell_trade['price']
                qty = sell_trade['quantity']
                sell_idx = sell_trade['grid_idx']
                buy_idx = self.middle_index - 1 - sell_idx
                buy_trade = None
                for t in self.trades:
                    if t['type'] == 'buy' and t['grid_idx'] == buy_idx:
                        buy_trade = t
                        break
                if buy_trade:
                    buy_price = buy_trade['price']
                    realized_pnl += (sell_price - buy_price) * qty
        balance = get_balance(self.token)
        usdt = balance.get('USDT', 0.0)
        coin = balance['coins'].get(self.symbol, 0.0)
        current_price = get_price(self.symbol)
        total_value = usdt + coin * current_price
        return realized_pnl, total_value

    def get_average_buy_price(self) -> float:
        """Compute weighted average buy price from all buy trades."""
        total_qty = 0.0
        total_cost = 0.0
        for t in self.trades:
            if t['type'] == 'buy':
                qty = t['quantity']
                price = t['price']
                total_qty += qty
                total_cost += qty * price
        if total_qty > 0:
            return total_cost / total_qty
        return 0.0

# ------------------------------------------------------------
# Dashboard Display
# ------------------------------------------------------------
def build_dashboard(state: GridState, current_price: float, phase: str,
                    max_price: Optional[float], drop_pct: Optional[float],
                    console: Console) -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
    )
    layout["main"].split_row(
        Layout(name="grids", ratio=2),
        Layout(name="info", ratio=1),
    )

    header_text = Text()
    header_text.append(f"Grid Trading Bot  ", style="bold cyan")
    header_text.append(f"|  Symbol: {state.symbol}  ", style="bold yellow")
    header_text.append(f"|  Grids: {state.grids}  ", style="bold green")
    header_text.append(f"|  Grid %: {state.grid_percent}%  ", style="bold green")
    header_text.append(f"|  Buy Amount: {state.amount_per_buy} USDT", style="bold magenta")
    layout["header"].update(Panel(header_text, border_style="bright_blue"))

    grid_table = Table(title="Grid Levels", box=box.ROUNDED, title_style="bold blue")
    grid_table.add_column("Grid", style="cyan", no_wrap=True)
    grid_table.add_column("Price", style="white")
    grid_table.add_column("Type", style="magenta")
    grid_table.add_column("Status", style="green")

    for i in range(state.grids):
        level = state.all_levels[i]
        if i < state.middle_index:
            typ = "BUY"
            done = state.buy_done[i]
            status = "DONE" if done else "PENDING"
            if done:
                qty = state.buy_quantities[i]
                status += f"\n{qty:.6f}"
        elif i == state.middle_index:
            typ = "MIDDLE"
            done = False
            status = "NO ACTION"
        else:
            typ = "SELL"
            sell_idx = i - state.middle_index - 1
            done = state.sell_done[sell_idx]
            status = "DONE" if done else "PENDING"
            if done:
                price = state.sell_prices[sell_idx]
                status += f"\n@{price:.2f}"

        price_str = f"{level:.2f}"
        if level < current_price:
            price_str = f"[red]{price_str}[/red]"
        elif level > current_price:
            price_str = f"[green]{price_str}[/green]"
        else:
            price_str = f"[bold yellow]{price_str}[/bold yellow]"

        row_style = ""
        if i < state.middle_index and state.buy_done[i]:
            row_style = "dim"
        elif i > state.middle_index and state.sell_done[i - state.middle_index - 1]:
            row_style = "dim"
        if i == state.middle_index:
            row_style = "bold"

        grid_table.add_row(
            f"{i+1}",
            price_str,
            typ,
            status,
            style=row_style
        )

    realized_pnl, total_value = state.compute_pnl()
    balance = get_balance(state.token)
    usdt = balance.get('USDT', 0.0)
    coin = balance['coins'].get(state.symbol, 0.0)

    next_buy_idx = state.get_next_buy()
    next_sell_idx = state.get_next_sell()
    next_buy_str = f"Grid {next_buy_idx+1} @ {state.buy_levels[next_buy_idx]:.2f}" if next_buy_idx is not None else "---"
    next_sell_str = f"Grid {next_sell_idx+state.middle_index+2} @ {state.sell_levels[next_sell_idx]:.2f}" if next_sell_idx is not None else "---"

    if phase == 'active':
        phase_str = "[bold green]ACTIVE[/bold green]"
    else:
        phase_str = f"[bold yellow]WAITING FOR DROP ({drop_pct*100:.2f}%)[/bold yellow]"

    info_table = Table(show_header=False, box=box.MINIMAL)
    info_table.add_row("Phase", phase_str)
    info_table.add_row("Current Price", f"{current_price:.2f}")
    info_table.add_row("USDT Balance", f"{usdt:.2f}")
    info_table.add_row(f"{state.symbol} Balance", f"{coin:.6f}")
    info_table.add_row("Realized P&L", f"{realized_pnl:+.2f} USDT")
    info_table.add_row("Total Equity", f"{total_value:.2f} USDT")
    info_table.add_row("Next Buy", next_buy_str)
    info_table.add_row("Next Sell", next_sell_str)

    last_trade = state.trades[-1] if state.trades else None
    if last_trade:
        last_type = last_trade['type'].upper()
        last_price = last_trade['price']
        last_qty = last_trade['quantity']
        last_grid = last_trade['grid_idx'] + (1 if last_trade['type'] == 'sell' else 0)
        last_str = f"{last_type} {last_qty:.6f} @ {last_price:.2f} (grid {last_grid})"
    else:
        last_str = "None"
    info_table.add_row("Last Trade", last_str)

    layout["info"].update(Panel(info_table, title="Info", border_style="bright_green"))
    layout["grids"].update(Panel(grid_table, title="Grid Status", border_style="bright_cyan"))

    return layout

# ------------------------------------------------------------
# Exit Handlers (limit sell, chart, HTML report)
# ------------------------------------------------------------
def compute_portfolio_history(history: List[Dict]) -> Tuple[List[datetime], List[float]]:
    timestamps = [datetime.fromisoformat(h['timestamp']) for h in history]
    values = [h['total_value'] for h in history]
    return timestamps, values

def generate_chart(history: List[Dict], symbol: str, token: str):
    if not MATPLOTLIB_AVAILABLE:
        print("Skipping chart: matplotlib not installed.")
        return
    if not history:
        print("No history data to plot.")
        return
    timestamps, values = compute_portfolio_history(history)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(timestamps, values, marker='o', linestyle='-', linewidth=2, markersize=3)
    ax.set_title(f'Portfolio Value Over Time – {symbol}', fontsize=14)
    ax.set_xlabel('Time')
    ax.set_ylabel('Total Equity (USDT)')
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    # Save PNG
    filename = f"portfolio_{token}_{symbol}.png"
    fig.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Chart saved as {filename}")

def generate_html_report(state: GridState, token: str):
    trades = state.trades
    if not trades:
        print("No trades to report.")
        return
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Trade History – {state.symbol}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f7fa; }}
            h1 {{ color: #2c3e50; }}
            table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
            td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
            tr:hover {{ background: #ecf0f1; }}
            .buy {{ color: #27ae60; font-weight: bold; }}
            .sell {{ color: #e74c3c; font-weight: bold; }}
            .summary {{ margin: 20px 0; padding: 15px; background: white; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <h1>Trade Report – {state.symbol}</h1>
    <div class="summary">
        <strong>Total Trades:</strong> {len(trades)} &nbsp;|&nbsp;
        <strong>Grids:</strong> {state.grids} &nbsp;|&nbsp;
        <strong>Grid %:</strong> {state.grid_percent}% &nbsp;|&nbsp;
        <strong>Buy Amount:</strong> {state.amount_per_buy} USDT
    </div>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Type</th>
                <th>Price (USDT)</th>
                <th>Quantity</th>
                <th>Grid Index</th>
                <th>Timestamp</th>
            </tr>
        </thead>
        <tbody>
    """
    for idx, t in enumerate(trades, 1):
        typ = t['type']
        cls = "buy" if typ == "buy" else "sell"
        html += f"""
            <tr>
                <td>{idx}</td>
                <td class="{cls}">{typ.upper()}</td>
                <td>{t['price']:.2f}</td>
                <td>{t['quantity']:.6f}</td>
                <td>{t['grid_idx']}</td>
                <td>{t['timestamp']}</td>
            </tr>
        """
    html += """
        </tbody>
    </table>
</body>
</html>
"""
    filename = f"trade_report_{token}_{state.symbol}.html"
    with open(filename, 'w') as f:
        f.write(html)
    print(f"HTML report saved as {filename}")

def on_exit(state: GridState, phase: str, max_price: Optional[float],
            history: List[Dict], token: str, symbol: str):
    print("\n[EXIT] Performing cleanup...")
    # 1. Place limit sell order for all coins at avg buy + 1.5%
    try:
        avg_price = state.get_average_buy_price()
        if avg_price > 0:
            # Get current coin balance
            bal = get_balance(token)
            coin_balance = bal['coins'].get(symbol, 0.0)
            if coin_balance > 0.000001:  # minimum threshold
                sell_price = avg_price * 1.015
                place_limit_sell(symbol, sell_price, coin_balance, token)
                print(f"Limit sell order placed for {coin_balance:.6f} {symbol} @ {sell_price:.2f} USDT")
            else:
                print("No coin balance to sell.")
        else:
            print("No buys recorded, cannot compute average price.")
    except Exception as e:
        print(f"Failed to place limit sell order: {e}")

    # 2. Generate chart
    generate_chart(history, symbol, token)

    # 3. Generate HTML report
    generate_html_report(state, token)

    # Save final state (including history)
    save_state(state, phase, max_price, history)
    print("State saved. Exiting.")

# ------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------
def main():
    console = Console()

    token = input("Enter your API token: ").strip()
    if not token:
        print("Token cannot be empty.")
        sys.exit(1)

    symbol = input("Enter symbol (e.g., BTC): ").strip().upper()
    if not symbol:
        print("Symbol cannot be empty.")
        sys.exit(1)

    saved_state = load_state(token, symbol)
    history = []  # will hold portfolio snapshots
    if saved_state:
        print(f"[LOAD] Found saved state from {saved_state.get('last_updated', 'unknown')}")
        grids = saved_state['grids']
        grid_percent = saved_state['grid_percent']
        amount_per_buy = saved_state['amount_per_buy']
        state = GridState(
            current_price=0.0,
            symbol=symbol,
            grids=grids,
            grid_percent=grid_percent,
            amount_per_buy=amount_per_buy,
            token=token,
            loaded_state=saved_state
        )
        phase = saved_state.get('phase', 'active')
        max_price_since_completion = saved_state.get('max_price_since_completion', None)
        history = saved_state.get('history', [])
        print(f"Resumed with {len(state.trades)} trades.")
    else:
        grids = int(input("Input how many grids you want (must be odd): "))
        if grids % 2 == 0:
            print("Number of grids must be odd. Please restart.")
            sys.exit(1)
        grid_percent = float(input("Input grid %: "))
        amount_per_buy = float(input("Enter USDT amount for each buy: "))

        try:
            initial_price = get_price(symbol)
        except Exception as e:
            print(f"Error fetching initial price: {e}")
            sys.exit(1)

        state = GridState(initial_price, symbol, grids, grid_percent, amount_per_buy, token)
        phase = 'active'
        max_price_since_completion = None
        # Initial snapshot
        bal = get_balance(token)
        coin = bal['coins'].get(symbol, 0.0)
        usdt = bal.get('USDT', 0.0)
        history.append({
            'timestamp': datetime.now().isoformat(),
            'price': initial_price,
            'coin_balance': coin,
            'usdt_balance': usdt,
            'total_value': usdt + coin * initial_price
        })
        save_state(state, phase, max_price_since_completion, history)

    drop_pct = None
    if phase == 'waiting_drop' and max_price_since_completion is not None:
        current_price = get_price(symbol)
        drop_pct = (max_price_since_completion - current_price) / max_price_since_completion if max_price_since_completion else 0.0

    # Variables for history recording
    last_history_time = time.time()

    try:
        with Live(refresh_per_second=1, screen=True) as live:
            while True:
                current_price = get_price(symbol)

                # Record portfolio snapshot every HISTORY_INTERVAL seconds
                now = time.time()
                if now - last_history_time >= HISTORY_INTERVAL:
                    bal = get_balance(token)
                    coin = bal['coins'].get(symbol, 0.0)
                    usdt = bal.get('USDT', 0.0)
                    total = usdt + coin * current_price
                    history.append({
                        'timestamp': datetime.now().isoformat(),
                        'price': current_price,
                        'coin_balance': coin,
                        'usdt_balance': usdt,
                        'total_value': total
                    })
                    last_history_time = now
                    # Trim history to last 1000 points to avoid memory bloat
                    if len(history) > 1000:
                        history = history[-1000:]

                # Phase: WAITING FOR DROP
                if phase == 'waiting_drop':
                    if max_price_since_completion is None or current_price > max_price_since_completion:
                        max_price_since_completion = current_price
                    drop_pct = (max_price_since_completion - current_price) / max_price_since_completion

                    if drop_pct >= DROP_THRESHOLD:
                        state = state.reset(current_price)
                        phase = 'active'
                        max_price_since_completion = None
                        drop_pct = None
                        save_state(state, phase, max_price_since_completion, history)

                # Phase: ACTIVE
                if phase == 'active':
                    trade_made = False
                    # Buy
                    for idx, level in enumerate(state.buy_levels):
                        if not state.buy_done[idx] and current_price >= level:
                            if state.buy_at(idx, current_price):
                                trade_made = True
                    # Sell
                    for idx, level in enumerate(state.sell_levels):
                        if not state.sell_done[idx]:
                            buy_idx = state.middle_index - 1 - idx
                            if buy_idx >= 0 and state.buy_quantities[buy_idx] is not None and state.buy_quantities[buy_idx] > 0:
                                if current_price >= level:
                                    if state.sell_at(idx, current_price):
                                        trade_made = True
                    if trade_made:
                        save_state(state, phase, max_price_since_completion, history)

                    if state.all_actions_done:
                        phase = 'waiting_drop'
                        max_price_since_completion = current_price
                        drop_pct = 0.0
                        save_state(state, phase, max_price_since_completion, history)

                # Update dashboard
                dashboard = build_dashboard(state, current_price, phase,
                                            max_price_since_completion, drop_pct,
                                            console)
                live.update(dashboard)
                time.sleep(1)

    except KeyboardInterrupt:
        # Graceful exit: place limit sell, generate chart and HTML report
        on_exit(state, phase, max_price_since_completion, history, token, symbol)
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        save_state(state, phase, max_price_since_completion, history)
        time.sleep(1)

if __name__ == "__main__":
    main()