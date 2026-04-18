"""
Add a paper by arXiv ID to Google Drive and ingest into LightRAG.
Usage: python add_paper.py <arxiv_id>
Example: python add_paper.py 1311.7829
"""

import asyncio
import json
import os
import sys
import tempfile

import arxiv
import fitz
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from lightrag_config import get_rag, LIGHTRAG_DIR

GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")
INGESTED_LOG     = os.path.join(LIGHTRAG_DIR, "lightrag_ingested.json")


def drive_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GDRIVE_REFRESH_TOKEN"],
        client_id=os.environ["GDRIVE_CLIENT_ID"],
        client_secret=os.environ["GDRIVE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("drive", "v3", credentials=creds)


def file_exists_in_drive(svc, filename):
    q = f"name='{filename}' and '{GDRIVE_FOLDER_ID}' in parents and trashed=false"
    res = svc.files().list(q=q, fields="files(id,webViewLink)").execute()
    files = res.get("files", [])
    return files[0].get("webViewLink") if files else None


def upload_to_drive(svc, pdf_path, filename):
    meta  = {"name": filename, "parents": [GDRIVE_FOLDER_ID]}
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
    return f.get("webViewLink", "")


def load_ingested():
    if os.path.exists(INGESTED_LOG):
        with open(INGESTED_LOG) as f:
            return set(json.load(f))
    return set()


def save_ingested(ingested):
    with open(INGESTED_LOG, "w") as f:
        json.dump(sorted(ingested), f, indent=2)


async def main(arxiv_id: str):
    # fetch metadata
    client = arxiv.Client()
    search = arxiv.Search(id_list=[arxiv_id])
    results = list(client.results(search))
    if not results:
        print(f"Paper {arxiv_id} not found on arXiv.")
        sys.exit(1)

    paper   = results[0]
    short_id = paper.get_short_id()
    filename = f"{short_id} - {paper.title[:80]}.pdf".replace("/", "-")
    print(f"Found: {paper.title}")

    svc = drive_service()

    # check drive duplicate
    existing = file_exists_in_drive(svc, filename)
    if existing:
        print(f"Already in Drive: {existing}")
    else:
        print("Downloading PDF…")
        r = requests.get(f"https://arxiv.org/pdf/{short_id}", timeout=60)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name
        print("Uploading to Drive…")
        link = upload_to_drive(svc, tmp_path, filename)
        os.unlink(tmp_path)
        print(f"Saved to Drive: {link}")

    # check lightrag duplicate
    ingested = load_ingested()
    drive_id = f"manual:{short_id}"
    if drive_id in ingested:
        print("Already in LightRAG — done.")
        return

    print("Ingesting into LightRAG…")
    r = requests.get(f"https://arxiv.org/pdf/{short_id}", timeout=60)
    r.raise_for_status()
    doc  = fitz.open(stream=r.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)

    rag = get_rag()
    await rag.initialize_storages()
    await rag.ainsert(text)

    ingested.add(drive_id)
    save_ingested(ingested)
    print("Done — paper added to Drive and LightRAG.")


if __name__ == "__main__":
    if os.path.exists(".env"):
        for line in open(".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
    if len(sys.argv) < 2:
        print("Usage: python add_paper.py <arxiv_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
