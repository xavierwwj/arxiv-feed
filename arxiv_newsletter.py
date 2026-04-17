"""
Daily arXiv newsletter for physics.atom-ph → Telegram.
Prioritises quantum-sensing papers, summarises with Claude,
fetches citation counts from Semantic Scholar.
"""

import os
import time
import textwrap
from datetime import datetime, timedelta, timezone

import arxiv
import anthropic
import requests

# ── config (override via environment variables) ────────────────────────────
CATEGORY        = os.getenv("ARXIV_CATEGORY", "physics.atom-ph")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
LOOKBACK_HOURS  = int(os.getenv("LOOKBACK_HOURS", "24"))
MAX_PAPERS      = int(os.getenv("MAX_PAPERS", "10"))   # cap to avoid huge messages

QUANTUM_SENSING_TERMS = [
    "quantum sens", "quantum sensor", "atomic sensor", "atomic clock",
    "optical clock", "atom interferom", "matter-wave interferom",
    "magnetomet", "electromet", "gravimeter", "gradiometer", "acceleromet", "gyroscop",
    "spin squeezing", "squeezed state", "entanglement-enhanced",
    "heisenberg limit", "standard quantum limit", "shot noise",
    "rydberg sensor", "rydberg atom", "rydberg rf", "optical lattice clock",
    "fountain clock", "ramsey spectroscop", "ramsey interferom",
    "optically pumped magnetom", "optically-pumped magnetom", "opm magnetom",
    "atom beam", "atomic beam",
    "nitrogen-vacancy", "nv center", "nv centre", "nv diamond",
    "diamond magnetom", "diamond sensor",
    "nmr gyro", "nuclear magnetic resonance gyro",
    "photonic integrated circuit", "integrated photonic",
    "photonic chip", "on-chip laser", "on-chip atomic",
]

# ── helpers ────────────────────────────────────────────────────────────────

def is_quantum_sensing(paper: arxiv.Result) -> bool:
    text = (paper.title + " " + paper.summary).lower()
    return any(t in text for t in QUANTUM_SENSING_TERMS)


def fetch_papers() -> list[arxiv.Result]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    client = arxiv.Client(page_size=100, delay_seconds=1)
    search = arxiv.Search(
        query=f"cat:{CATEGORY}",
        max_results=200,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    papers = []
    for r in client.results(search):
        if r.published < cutoff:
            break
        papers.append(r)
    # quantum-sensing papers first, then the rest; cap total
    qs   = [p for p in papers if is_quantum_sensing(p)]
    rest = [p for p in papers if not is_quantum_sensing(p)]
    return (qs + rest)[:MAX_PAPERS], len(qs), len(papers)


def first_and_last_authors(paper: arxiv.Result) -> str:
    names = [a.name for a in paper.authors]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{names[0]} … {names[-1]}"


def summarise_paper(paper: arxiv.Result, client: anthropic.Anthropic) -> str:
    authors = first_and_last_authors(paper)

    prompt = textwrap.dedent(f"""
        You are summarising an academic physics paper for a researcher who follows
        atomic physics and quantum sensing. Be concise but precise — use proper
        technical terminology. Structure your reply with exactly these four lines,
        each starting with the label shown:

        KEY RESULT: one sentence on the main finding or demonstration.
        NOVELTY: one sentence on what is new compared to prior work.
        TECHNIQUE: one sentence on the core method, apparatus, or theoretical tool.
        SENSING RELEVANCE: one sentence on relevance to quantum sensing (write "N/A" if none).

        Title: {paper.title}
        Authors: {authors}
        Abstract: {paper.summary.strip()}
    """).strip()

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip(), authors


def format_paper_block(
    idx: int,
    paper: arxiv.Result,
    summary: str,
    authors: str,
    is_qs: bool,
) -> str:
    tag      = "🔬 " if is_qs else ""
    arxiv_id = paper.get_short_id()
    url      = f"https://arxiv.org/abs/{arxiv_id}"
    pdf      = f"https://arxiv.org/pdf/{arxiv_id}"

    block = (
        f"{tag}*{idx}. {paper.title}*\n"
        f"👤 {authors}\n"
        f"📅 {paper.published.strftime('%Y-%m-%d')}\n"
        f"🔗 [Abstract]({url})  |  [PDF]({pdf})\n\n"
        f"{summary}"
    )
    return block


def send_telegram(text: str, token: str, chat_id: str) -> None:
    """Send markdown message; splits if >4096 chars (Telegram limit)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        time.sleep(0.5)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    assert TELEGRAM_TOKEN, "Set TELEGRAM_BOT_TOKEN env var"
    assert TELEGRAM_CHAT,  "Set TELEGRAM_CHAT_ID env var"
    assert ANTHROPIC_KEY,  "Set ANTHROPIC_API_KEY env var"

    claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    print("Fetching papers…")
    papers, qs_count, total = fetch_papers()
    print(f"  {total} new papers total, {qs_count} quantum-sensing, showing {len(papers)}")

    date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
    header = (
        f"📡 *arXiv Daily · {CATEGORY}*\n"
        f"📆 {date_str} — past {LOOKBACK_HOURS}h\n"
        f"📄 {total} new papers | 🔬 {qs_count} quantum-sensing highlighted\n"
        f"{'─'*35}"
    )
    send_telegram(header, TELEGRAM_TOKEN, TELEGRAM_CHAT)

    qs_set = {p.get_short_id() for p in papers if is_quantum_sensing(p)}

    for idx, paper in enumerate(papers, 1):
        print(f"  [{idx}/{len(papers)}] {paper.title[:60]}…")
        try:
            summary, authors = summarise_paper(paper, claude)
        except Exception as e:
            summary, authors = f"(summary error: {e})", "unknown"

        is_qs  = paper.get_short_id() in qs_set
        block  = format_paper_block(idx, paper, summary, authors, is_qs)
        send_telegram(block, TELEGRAM_TOKEN, TELEGRAM_CHAT)
        time.sleep(0.3)

    footer = f"─────\n✅ End of digest · {len(papers)} papers sent"
    send_telegram(footer, TELEGRAM_TOKEN, TELEGRAM_CHAT)
    print("Done.")


if __name__ == "__main__":
    main()
