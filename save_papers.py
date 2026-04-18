"""
Download arXiv PDFs by index number and upload to Google Drive.
Usage: python save_papers.py 1 3 5
Reads papers_today.json for the index → arXiv ID mapping.
"""

import json
import os
import sys
import tempfile

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "1PL3p2kAc4kUIDzdv7DDYn4wQjI8jya6l")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")


def drive_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GDRIVE_REFRESH_TOKEN"],
        client_id=os.environ["GDRIVE_CLIENT_ID"],
        client_secret=os.environ["GDRIVE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("drive", "v3", credentials=creds)


def file_exists_in_drive(service, filename: str) -> str | None:
    """Return webViewLink if file already exists in the folder, else None."""
    q = (f"name='{filename}' and '{GDRIVE_FOLDER_ID}' in parents "
         f"and trashed=false")
    res = service.files().list(q=q, fields="files(id,webViewLink)").execute()
    files = res.get("files", [])
    return files[0].get("webViewLink") if files else None


def upload_pdf(service, pdf_path: str, filename: str) -> str:
    meta = {"name": filename, "parents": [GDRIVE_FOLDER_ID]}
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    f = service.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
    return f.get("webViewLink", "")


def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "Markdown",
              "disable_web_page_preview": True},
        timeout=15,
    )


def main(indices: list[str]):
    with open("papers_today.json") as f:
        cache = json.load(f)

    svc = drive_service()

    for idx in indices:
        entry = cache.get(str(idx))
        if not entry:
            print(f"  [{idx}] not found in today's papers")
            send_telegram(f"⚠️ Paper {idx} not found in today's list.")
            continue

        arxiv_id = entry["arxiv_id"]
        title    = entry["title"]
        filename = f"{arxiv_id} - {title[:80]}.pdf".replace("/", "-")

        existing = file_exists_in_drive(svc, filename)
        if existing:
            print(f"  [{idx}] Already in Drive, skipping.")
            send_telegram(f"⚠️ *{title}* is already in Drive.\n[Open]({existing})")
            continue

        print(f"  [{idx}] Downloading {arxiv_id}…")
        r = requests.get(entry["pdf_url"], timeout=60)
        r.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name

        print(f"  [{idx}] Uploading to Drive…")
        link = upload_pdf(svc, tmp_path, filename)
        os.unlink(tmp_path)

        print(f"  [{idx}] Done: {link}")
        send_telegram(f"✅ Saved *{title}*\n[Open in Drive]({link})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python save_papers.py 1 3 5")
        sys.exit(1)
    main(sys.argv[1:])
