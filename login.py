"""
One-time Gmail OAuth login — generates token.json.
Run this before deploying; never processes your inbox.

Usage:
    uv run python login.py
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
_CREDENTIALS_PATH = "credentials.json"
_TOKEN_PATH = "token.json"

flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS_PATH, _SCOPES)
creds = flow.run_local_server(port=0)
Path(_TOKEN_PATH).write_text(creds.to_json())

print(f"Done — {_TOKEN_PATH} saved.")
