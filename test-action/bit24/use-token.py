#!/usr/bin/env python3
"""
test_connection.py - Test Bit24 API credentials from .env file.
With playful console animations.
Usage: python test_connection.py
"""

import os
import sys
import time
import itertools
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("BIT24_API_KEY")
SECRET_KEY = os.getenv("BIT24_SECRET_KEY")  # not used for GET, but we check it exists


def spinner_animation(duration_sec, text="Connecting"):
    """Show a spinning loader for a given duration (or until interrupted)."""
    frames = ["|", "/", "-", "\\"]
    cycle = itertools.cycle(frames)
    end_time = time.time() + duration_sec
    while time.time() < end_time:
        sys.stdout.write(f"\r{text} {next(cycle)}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * (len(text) + 4) + "\r")  # clear line


def test_connection():
    """Test if API key works by calling the assets endpoint."""
    if not API_KEY:
        print("❌ BIT24_API_KEY not found in .env file.")
        return False
    if not SECRET_KEY:
        print("⚠️  BIT24_SECRET_KEY is missing (not required for this test, but may be needed later).")

    url = "https://rest.bit24.cash/asset/capi/v1/wallet/assets"
    headers = {
        "Accept": "application/json",
        "X-BIT24-APIKEY": API_KEY,
    }

    # Start a spinner in parallel? We'll just show one before the request.
    # To make it look lively, we flash a quick "Connecting..." animation
    for _ in range(5):  # 0.5 second animation
        sys.stdout.write("\r🔗 Connecting to Bit24 " + "|/-\\"[ _ % 4 ])
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * 30 + "\r")  # clear

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return False

    # Check status and response
    if response.status_code != 200:
        print(f"❌ HTTP error {response.status_code}: {response.text}")
        return False

    data = response.json()
    if not data.get("success"):
        error_msg = data.get("error", {}).get("message", "Unknown error")
        print(f"❌ API error: {error_msg}")
        return False

    # Success! Show a little animated celebration
    sys.stdout.write("✅ Work")
    for _ in range(4):
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(0.15)
    print(" And Successful Check")
    return True


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)