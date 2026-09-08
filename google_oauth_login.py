"""
google_oauth_login.py - 1-Click Google Account Sign-in
Prompts user to authorize the app once in their browser and saves token.json.
Uses your personal Gmail account's 15 GB storage for uploading laptop reports & photos!
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'client_secret.json')
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token.json')

def login():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        print("[OK] Already logged in to Google Drive with valid token!")
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as token_f:
                token_f.write(creds.to_json())
            print("[OK] Successfully refreshed Google Drive token!")
            return creds
        except Exception as e:
            print(f"[!] Token refresh failed ({e}), starting new login flow...")

    print("=" * 65, flush=True)
    print("    GOOGLE DRIVE ACCOUNT LOGIN (1-TIME SETUP)", flush=True)
    print("=" * 65, flush=True)
    print("Opening your browser to sign in with your Google account...", flush=True)

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    print("\nIf browser did not open automatically, copy & paste this URL:", flush=True)
    print(auth_url, flush=True)
    print("=" * 65, flush=True)

    creds = flow.run_local_server(port=8090, prompt='consent')

    with open(TOKEN_FILE, 'w') as token_f:
        token_f.write(creds.to_json())

    print("\n[SUCCESS] Google Drive authenticated! Token saved to token.json.", flush=True)
    return creds

if __name__ == '__main__':
    login()
