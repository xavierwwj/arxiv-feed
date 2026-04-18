"""
Download new PDFs from Google Drive and ingest into LightRAG.
Tracks already-ingested files in lightrag_ingested.json to avoid duplicates.
Usage: python ingest_papers.py
"""

import asyncio
import json
import os
import tempfile

import fitz  # pymupdf
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

from lightrag_config import get_rag, LIGHTRAG_DIR

GDRIVE_FOLDER_ID   = os.getenv("GDRIVE_FOLDER_ID", "")
LIGHTRAG_DIR  = os.getenv("LIGHTRAG_DIR", "/lightrag-db")
INGESTED_LOG  = os.path.join(LIGHTRAG_DIR, "lightrag_ingested.json")


def drive_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GDRIVE_REFRESH_TOKEN"],
        client_id=os.environ["GDRIVE_CLIENT_ID"],
        client_secret=os.environ["GDRIVE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("drive", "v3", credentials=creds)


def list_drive_pdfs(svc) -> list[dict]:
    q = f"'{GDRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false"
    results = []
    page_token = None
    while True:
        resp = svc.files().list(
            q=q,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def download_pdf(svc, file_id: str) -> bytes:
    request = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def extract_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def load_ingested() -> set:
    if os.path.exists(INGESTED_LOG):
        with open(INGESTED_LOG) as f:
            return set(json.load(f))
    return set()


def save_ingested(ingested: set):
    with open(INGESTED_LOG, "w") as f:
        json.dump(sorted(ingested), f, indent=2)


async def main():
    ingested = load_ingested()
    svc = drive_service()
    rag = get_rag()
    await rag.initialize_storages()

    pdfs = list_drive_pdfs(svc)
    print(f"Found {len(pdfs)} PDF(s) in Drive folder.")
    for p in pdfs:
        print(f"  - {p['name']} ({p['id']})")
    def already_ingested(pdf):
        # match by Drive file ID or by arXiv ID extracted from filename
        arxiv_id = pdf["name"].split(" - ")[0]  # e.g. "1610.09550v1"
        return pdf["id"] in ingested or f"manual:{arxiv_id}" in ingested

    new_pdfs = [p for p in pdfs if not already_ingested(p)]

    if not new_pdfs:
        print("No new papers to ingest.")
        return

    print(f"Found {len(new_pdfs)} new paper(s) to ingest.")

    for pdf in new_pdfs:
        print(f"  Ingesting: {pdf['name']}")
        try:
            pdf_bytes = download_pdf(svc, pdf["id"])
            text = extract_text(pdf_bytes)
            if len(text.strip()) < 100:
                print(f"  Skipping {pdf['name']} — could not extract text.")
                continue
            await rag.ainsert(text)
            ingested.add(pdf["id"])
            save_ingested(ingested)
            print(f"  Done: {pdf['name']}")
        except Exception as e:
            print(f"  Error ingesting {pdf['name']}: {e}")

    print(f"\nIngestion complete. Total ingested: {len(ingested)} papers.")


if __name__ == "__main__":
    # load .env if running locally
    if os.path.exists(".env"):
        for line in open(".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
    asyncio.run(main())
