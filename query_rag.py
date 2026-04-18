"""
RAG-augmented query: retrieves context from LightRAG then answers with Claude.
Usage: python query_rag.py "your question here"
       python query_rag.py "your question here" --mode hybrid
Modes: naive, local, global, hybrid (default: hybrid)
"""

import asyncio
import os
import sys

import anthropic
from lightrag import QueryParam

from lightrag_config import get_rag, LIGHTRAG_DIR

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


async def query(question: str, mode: str = "hybrid") -> str:
    rag = get_rag()
    await rag.initialize_storages()

    print(f"Retrieving context from LightRAG ({mode} mode)…")
    context = await rag.aquery(question, param=QueryParam(mode=mode, only_need_context=True))

    if not context or context.strip() == "":
        print("No relevant context found in paper database — answering from general knowledge.")
        system = "You are a helpful scientific assistant specialising in atomic physics and quantum sensing."
        user_content = question
    else:
        print(f"Context retrieved ({len(context)} chars). Querying Claude…\n")
        system = """You are a helpful scientific assistant specialising in atomic physics and quantum sensing.
You have been provided with context from a curated database of research papers.
Answer primarily based on this context, citing specific findings where relevant.
If the context does not cover the question, supplement with your general knowledge and say so."""
        user_content = f"""Context from paper database:
{context}

Question: {question}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def main():
    if os.path.exists(".env"):
        for line in open(".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

    if len(sys.argv) < 2:
        print('Usage: python query_rag.py "your question"')
        print('       python query_rag.py "your question" --mode hybrid|local|global|naive')
        sys.exit(1)

    question = sys.argv[1]
    mode = "hybrid"
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        mode = sys.argv[idx + 1]

    answer = asyncio.run(query(question, mode))
    print("\n" + "=" * 60)
    print(answer)


if __name__ == "__main__":
    main()
