#!/usr/bin/env python3
"""
setup_env.py - Prompt for Bit24 API credentials and store in .env file.
Usage: python setup_env.py
"""

import os

ENV_FILE = ".env"


def get_user_input(prompt, is_secret=False):
    """Get input from user, optionally masking secret."""
    import getpass
    if is_secret:
        return getpass.getpass(prompt)
    return input(prompt)


def write_env(api_key, secret_key):
    """Write credentials to .env file."""
    content = f"""# Bit24 API credentials
BIT24_API_KEY={api_key}
BIT24_SECRET_KEY={secret_key}
"""
    with open(ENV_FILE, "w") as f:
        f.write(content)
    print(f"✅ Credentials saved to {ENV_FILE}")


def main():
    print("🔑 Bit24 API Credential Setup")
    print("Please enter your API credentials from your Bit24 account.")
    print("You can find them in the API management section of your profile.\n")

    api_key = get_user_input("Enter your API key (X-BIT24-APIKEY): ").strip()
    while not api_key:
        api_key = get_user_input("API key cannot be empty. Enter API key: ").strip()

    secret_key = get_user_input("Enter your secret key (used for signing POST requests): ", is_secret=True).strip()
    while not secret_key:
        secret_key = get_user_input("Secret key cannot be empty. Enter secret key: ", is_secret=True).strip()

    # Confirm before overwriting existing .env
    if os.path.exists(ENV_FILE):
        overwrite = input(f"{ENV_FILE} already exists. Overwrite? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("Aborted.")
            return

    write_env(api_key, secret_key)
    print("\nYou can now load these credentials in your code using python-dotenv or os.getenv.")


if __name__ == "__main__":
    main()