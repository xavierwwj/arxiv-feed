"""
One-time script to get a Google OAuth refresh token.
Run locally: python get_refresh_token.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

flow = InstalledAppFlow.from_client_secrets_file("oauth_client.json", SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== Copy these values into GitHub Secrets ===")
print(f"GDRIVE_CLIENT_ID:     {creds.client_id}")
print(f"GDRIVE_CLIENT_SECRET: {creds.client_secret}")
print(f"GDRIVE_REFRESH_TOKEN: {creds.refresh_token}")
