#!/usr/bin/env python3
"""
test_connection.py - Test Bit24 API credentials from .env file.
Usage: python test_connection.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("BIT24_API_KEY")
SECRET_KEY = os.getenv("BIT24_SECRET_KEY")  # not used for GET, but we check it exists

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

    # If we reach here, connection is successful
    print("Work And Successfull Check")
    return True

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)