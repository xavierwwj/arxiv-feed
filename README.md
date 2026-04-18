# arXiv Feed

Daily atomic physics / quantum sensing paper pipeline:
- **Newsletter** via Telegram (GitHub Actions, 9am SGT)
- **Paper saving** to Google Drive via Telegram reply
- **RAG queries** via Claude Desktop using LightRAG + Voyage AI

---

## Architecture

```
arXiv API → GitHub Actions → Telegram newsletter
                                    ↓ (reply "save 1 3")
                         Cloudflare Worker → GitHub Actions → Google Drive PDF
                                                                      ↓
                                                    docker compose run ingest → LightRAG DB
                                                                      ↓
                                                          Claude Desktop (MCP) ← your queries
```

---

## Prerequisites

- Docker Desktop
- A free account on: GitHub, Cloudflare, Google Cloud, Voyage AI, Telegram
- Anthropic API key (separate from Claude Pro subscription)
- Claude Desktop installed

---

## Installation (single user)

### 1. Clone the repo

```bash
git clone https://github.com/xavierwwj/arxiv-feed.git
cd arxiv-feed
```

### 2. Create `.env`

```bash
cp .env.example .env   # then fill in the values
```

| Variable | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram → /newbot |
| `TELEGRAM_CHAT_ID` | Message your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `VOYAGE_API_KEY` | dash.voyageai.com → API Keys |
| `GDRIVE_FOLDER_ID` | Google Drive folder URL → the ID after `/folders/` |
| `GDRIVE_CLIENT_ID` | Google Cloud Console → OAuth 2.0 Client ID |
| `GDRIVE_CLIENT_SECRET` | same as above |
| `GDRIVE_REFRESH_TOKEN` | run `python get_refresh_token.py` (one-time) |
| `LIGHTRAG_DIR` | local path for LightRAG DB (e.g. inside Google Drive for Desktop sync) |

### 3. Get Google Drive OAuth refresh token

```bash
pip install google-auth-oauthlib
python get_refresh_token.py
```

Sign in with your Google account. Copy the printed `GDRIVE_REFRESH_TOKEN` into `.env`.

### 4. Add GitHub Secrets

In your GitHub repo → Settings → Secrets → Actions, add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY`
- `GDRIVE_FOLDER_ID`
- `GDRIVE_CLIENT_ID`
- `GDRIVE_CLIENT_SECRET`
- `GDRIVE_REFRESH_TOKEN`

### 5. Set up Cloudflare Worker

1. Create a free account at cloudflare.com
2. Workers & Pages → Create Worker → paste contents of `cloudflare_worker.js`
3. Add Worker secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_TOKEN` (PAT with `workflow` scope), `GITHUB_REPO` (e.g. `username/arxiv-feed`), `GITHUB_BRANCH` (`master`)
4. Point Telegram webhook to your Worker URL:
```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-worker.workers.dev"
```

### 6. Build Docker image

```bash
docker compose build
docker build -t arxiv-feed-mcp .
```

### 7. Configure Claude Desktop MCP

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lightrag-papers": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--env-file", "/absolute/path/to/arxiv-feed/.env",
        "-e", "LIGHTRAG_DIR=/lightrag-db",
        "-v", "/absolute/path/to/lightrag-db:/lightrag-db",
        "arxiv-feed-mcp",
        "python", "mcp_server.py"
      ]
    }
  }
}
```

Restart Claude Desktop.

### 8. Test

```bash
# Test newsletter (uses 1-week lookback)
LOOKBACK_HOURS=168 docker compose run newsletter

# Test ingestion
docker compose run ingest

# Test query
docker compose run query "What techniques are used in Rydberg electrometry?"
```

---

## Daily usage

| Task | How |
|---|---|
| Receive newsletter | Automatic at 9am SGT |
| Save a paper to Drive | Reply `save 1 3 5` to the Telegram bot |
| Ingest new papers into LightRAG | `docker compose run ingest` |
| Query your paper database | Ask in Claude Desktop — RAG is automatic |
| Add a specific paper by arXiv ID | Tell Claude Desktop: "add arXiv:1234.56789" |

---

## Adding more users

### Shared newsletter (Telegram group)

1. Create a Telegram group and add your bot
2. Get the group chat ID (negative number, e.g. `-1001234567890`) from `getUpdates`
3. Update `TELEGRAM_CHAT_ID` in GitHub Secrets to the group chat ID

### Shared paper saving

Each user needs their own Cloudflare Worker pointing to the shared GitHub repo.
Update the Worker's `TELEGRAM_CHAT_ID` to their personal chat ID.
All saved papers go to the same Google Drive folder.

### Per-user LightRAG

Each user:
1. Clones the repo
2. Fills in their own `.env` (they can reuse the shared `GDRIVE_*` credentials to access the same paper folder)
3. Runs `docker compose build && docker build -t arxiv-feed-mcp .`
4. Configures their own Claude Desktop MCP
5. Runs `docker compose run ingest` to build their local LightRAG DB from the shared Drive folder

---

## Cost estimate (per user/month)

| Service | Cost |
|---|---|
| Anthropic API (Haiku) — newsletter summaries | ~$0.10 |
| Anthropic API (Haiku) — LightRAG ingestion | ~$0.50–2.00 depending on papers saved |
| Voyage AI embeddings | Free (200M tokens/month) |
| GitHub Actions | Free |
| Cloudflare Workers | Free |
| Google Drive | Free (15GB) |
| **Total** | **~$0.60–2.10/month** |
