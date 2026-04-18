"""
MCP server exposing LightRAG as a tool for Claude Desktop.
Tools:
  - query_papers: search your paper database
  - add_paper: add a paper by arXiv ID to Drive + LightRAG
"""

import asyncio
import json
import os
import tempfile

import fitz
import requests
import arxiv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from lightrag_config import get_rag

server = Server("lightrag-papers")

_rag = None


async def get_initialized_rag():
    global _rag
    if _rag is None:
        _rag = get_rag()
        await _rag.initialize_storages()
    return _rag


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_papers",
            description=(
                "Search your personal curated database of atomic physics and quantum sensing "
                "research papers. Use this tool whenever the user asks about topics that may "
                "be covered in their saved papers — experiments, techniques, instruments, "
                "results, or authors. Returns relevant excerpts and knowledge graph context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The research question or topic to search for.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["hybrid", "local", "global", "naive"],
                        "default": "hybrid",
                        "description": "Search mode: hybrid (recommended), local (entity-focused), global (theme-focused), naive (plain vector search).",
                    },
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="add_paper",
            description=(
                "Add a research paper to the user's Google Drive folder and LightRAG database "
                "by arXiv ID. Use this when the user asks to save or add a paper they found "
                "or that was referenced in a conversation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "arxiv_id": {
                        "type": "string",
                        "description": "The arXiv paper ID, e.g. '1311.7829' or '2604.11785'.",
                    }
                },
                "required": ["arxiv_id"],
            },
        ),
    ]


async def _ingest_background(short_id: str, drive_id: str, ingested_log: str):
    try:
        r    = requests.get(f"https://arxiv.org/pdf/{short_id}", timeout=60)
        doc  = fitz.open(stream=r.content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        rag  = await get_initialized_rag()
        await rag.ainsert(text)
        ingested = set(json.load(open(ingested_log))) if os.path.exists(ingested_log) else set()
        ingested.add(drive_id)
        with open(ingested_log, "w") as f:
            json.dump(sorted(ingested), f, indent=2)
        print(f"Background ingestion complete: {short_id}", flush=True)
    except Exception as e:
        print(f"Background ingestion failed for {short_id}: {e}", flush=True)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "query_papers":
        from lightrag import QueryParam
        question = arguments["question"]
        mode     = arguments.get("mode", "hybrid")
        rag      = await get_initialized_rag()
        context  = await rag.aquery(question, param=QueryParam(mode=mode, only_need_context=True))
        if not context or not context.strip():
            return [TextContent(type="text", text="No relevant context found in paper database.")]
        return [TextContent(type="text", text=context)]

    if name == "add_paper":
        arxiv_id = arguments["arxiv_id"]

        # fetch metadata
        client  = arxiv.Client()
        results = list(client.results(arxiv.Search(id_list=[arxiv_id])))
        if not results:
            return [TextContent(type="text", text=f"Paper {arxiv_id} not found on arXiv.")]

        paper    = results[0]
        short_id = paper.get_short_id()
        filename = f"{short_id} - {paper.title[:80]}.pdf".replace("/", "-")

        # google drive upload
        creds = Credentials(
            token=None,
            refresh_token=os.environ["GDRIVE_REFRESH_TOKEN"],
            client_id=os.environ["GDRIVE_CLIENT_ID"],
            client_secret=os.environ["GDRIVE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
        )
        svc    = build("drive", "v3", credentials=creds)
        folder = os.environ.get("GDRIVE_FOLDER_ID", "")
        q      = f"name='{filename}' and '{folder}' in parents and trashed=false"
        exists = svc.files().list(q=q, fields="files(webViewLink)").execute().get("files", [])

        if not exists:
            r = requests.get(f"https://arxiv.org/pdf/{short_id}", timeout=60)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = tmp.name
            meta  = {"name": filename, "parents": [folder]}
            media = MediaFileUpload(tmp_path, mimetype="application/pdf")
            svc.files().create(body=meta, media_body=media, fields="id").execute()
            os.unlink(tmp_path)

        # lightrag ingestion — run in background so we return immediately
        lightrag_dir = os.environ.get("LIGHTRAG_DIR", "/lightrag-db")
        ingested_log = os.path.join(lightrag_dir, "lightrag_ingested.json")
        ingested     = set(json.load(open(ingested_log))) if os.path.exists(ingested_log) else set()
        drive_id     = f"manual:{short_id}"

        if drive_id not in ingested:
            asyncio.create_task(_ingest_background(short_id, drive_id, ingested_log))
            ingest_status = "LightRAG ingestion started in background."
        else:
            ingest_status = "Already in LightRAG."

        status = "already in Drive" if exists else "saved to Drive"
        return [TextContent(type="text", text=f"✅ *{paper.title}* — {status}. {ingest_status}")]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
