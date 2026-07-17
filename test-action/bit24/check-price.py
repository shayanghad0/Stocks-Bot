import requests
import time
import sys
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("BIT24_API_KEY", "").strip()
BASE_URL = "https://rest.bit24.cash"
ENDPOINT = "/pro/capi/v1/markets"
BASE_COIN = input("Please Input your Symbol (BTC | ADA | ETH | TRX | ... ) : >._.< : ")
QUOTE_COIN = input("Please Input your currency (IRT | USDT) : >._.< : ")
INTERVAL = 1.0
REQUEST_TIMEOUT = 10


def get_price(session):
    url = f"{BASE_URL}{ENDPOINT}"
    headers = {"Accept": "application/json", "X-BIT24-APIKEY": API_KEY}
    try:
        resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return None
        for m in data["data"]["results"]:
            if m["base_coin_symbol"].upper() == BASE_COIN and m["quote_coin_symbol"].upper() == QUOTE_COIN:
                return float(m["each_price"])
    except Exception as e:
        print(f"Error: {e}")
    return None


def main():
    if not API_KEY:
        print("BIT24_API_KEY not set in .env")
        return

    session = requests.Session()
    last_price = None
    counter = 0

    print(f"Tracking {BASE_COIN}/{QUOTE_COIN} every {int(INTERVAL)}s. Ctrl+C to stop.\n")

    while True:
        price = get_price(session)
        counter += 1

        if price is not None:
            if last_price is not None:
                change = ((price - last_price) / last_price) * 100
                print(f"[{counter}] {price} | change: {change:+.4f}%")
            else:
                print(f"[{counter}] {price} | first reading")
            last_price = price
        else:
            print(f"[{counter}] failed to get price")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
