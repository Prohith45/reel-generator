#!/usr/bin/env python3
"""
YouTube OAuth2 Token Generator
==============================
Opens a browser for Google OAuth consent and obtains a refresh_token.
Automatically saves it to .env if the file exists.

Usage:
    python get_youtube_token.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
CLIENT_SECRETS = PROJECT_ROOT / "client_secret.json"

def main():
    # ── Validate prerequisites ──
    if not CLIENT_SECRETS.exists():
        print(f"[FATAL] client_secret.json not found at: {CLIENT_SECRETS}")
        print("Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[FATAL] google-auth-oauthlib is not installed.")
        print("Run: pip install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS),
        SCOPES
    )

    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent"
    )

    refresh_token = credentials.refresh_token
    client_id = credentials.client_id
    client_secret = credentials.client_secret

    print("\n" + "=" * 60)
    print("  YOUTUBE OAUTH2 CREDENTIALS")
    print("=" * 60)
    print(f"  Client ID     : {client_id}")
    print(f"  Client Secret : {client_secret}")
    print(f"  Refresh Token : {refresh_token}")
    print("=" * 60)

    # ── Auto-save to .env ──
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        env_text = env_path.read_text(encoding="utf-8")
        updated = False

        replacements = {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REFRESH_TOKEN": refresh_token,
        }

        for key, value in replacements.items():
            # Replace empty or placeholder values
            import re
            pattern = rf"^{key}=.*$"
            new_line = f"{key}={value}"
            if re.search(pattern, env_text, re.MULTILINE):
                env_text = re.sub(pattern, new_line, env_text, flags=re.MULTILINE)
                updated = True
            else:
                env_text += f"\n{new_line}"
                updated = True

        if updated:
            env_path.write_text(env_text, encoding="utf-8")
            print("\n[OK] Credentials saved to .env")
    else:
        print("\n[INFO] .env not found. Copy the values above into your .env file manually.")

    print("\n[DONE] You can now run the automation pipeline.")


if __name__ == "__main__":
    main()