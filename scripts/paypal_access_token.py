"""Print a short-lived PayPal access token from the client id/secret in .env (for PayPal's MCP server).

    python scripts/paypal_access_token.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.paypal.adapter import get_client  # noqa: E402

if __name__ == "__main__":
    print(get_client()._access_token())
