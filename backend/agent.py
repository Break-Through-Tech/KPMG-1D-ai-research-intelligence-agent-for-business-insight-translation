"""Minimal call to the Anthropic (Claude) API. Reads ANTHROPIC_API_KEY from the repo's .env.

Try it from backend/:  python agent.py "What is retrieval-augmented generation?"
"""

import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from api.Search_Chroma import TOP_K, search_passages

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = "claude-sonnet-5-5"
client = anthropic.Anthropic()


def _create(messages, system=None, **extra):
    """One call to Claude; returns the full response (text, tool calls, ...)."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        **({"system": system} if system else {}),
        messages=messages,
        # If a safety classifier declines, the API retries on a suitable fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        **extra,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to answer this request")
    return response


def _text(response):
    return "".join(block.text for block in response.content if block.type == "text")


def complete(messages, system=None):
    """Send a list of {"role": "user"|"assistant", "content": str} messages to Claude; return its text reply."""
    return _text(_create(messages, system=system))


def ask(prompt, system=None):
    """Send one prompt to Claude and return its text reply."""
    return complete([{"role": "user", "content": prompt}], system=system)


# ---- Agent tasks ----

TITLE_SYSTEM = (
    "You name conversations in a research assistant's sidebar. "
    "Reply with only a short title (at most 6 words) that captures the topic of the user's question. "
    "No quotes, no trailing punctuation."
)

CHAT_SYSTEM = (
    "You are KAI, KPMG's AI research assistant. You help business professionals understand recent AI research "
    "and what it means for their clients. Explain in plain language, be concise, and point out practical "
    "implications and risks. If you are unsure or lack evidence, say so instead of guessing.\n\n"
    "You have a search_papers tool over the research papers in KAI's database. When a question is about AI "
    "research (methods, results, trends, what papers found), search before answering and base your answer on "
    "the passages it returns, citing each claim as (paper title, p. N). If the passages don't cover the "
    "question, say the database doesn't cover it; you may add general background, but label it as not coming "
    "from the papers. Messages that don't need research evidence (greetings, rephrasing or clarifying your "
    "previous answer) don't need a search."
)

SEARCH_TOOL = {
    "name": "search_papers",
    "description": (
        "Semantic search over the passages of the recent arXiv AI research papers in KAI's database. "
        f"Returns the {TOP_K} passages most similar to the query, each with its paper title, arXiv id, page "
        "number and cosine similarity score. Write the query as a focused description of the information you "
        "need (e.g. 'methods to reduce inference cost of LLM agents'), not as a chat message. Call it again with "
        "a different query if the first results don't cover the question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to look for in the papers."}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}

MAX_SEARCH_ROUNDS = 3  # after this many rounds of searches, the agent must answer with what it has


def name_conversation(question, context=None):
    """Agent task: a short sidebar title for a new conversation, from its first question."""
    prompt = f"Question: {question}" + (f"\nContext: {context}" if context else "")
    title = ask(prompt, system=TITLE_SYSTEM).strip().strip("\"'").rstrip(".")
    return title[:80] or "Untitled chat"


def _format_passages(retrieval):
    """The search results as the agent reads them."""
    if not retrieval["passages"]:
        return "No passages found."
    return "\n\n".join(
        f"[{p['rank']}] similarity {p['score']:.3f} | \"{p['title']}\" (arXiv {p['paper_id']}), page {p['page_number']}\n"
        f"{' '.join(p['text'].split())}"
        for p in retrieval["passages"])


def _run_search(block, retrievals):
    """Run one search_papers call; record it in `retrievals` and return its tool_result block."""
    if block.name != SEARCH_TOOL["name"]:
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": f"Unknown tool {block.name}"}
    try:
        retrieval = search_passages(block.input["query"])
    except Exception as error:  # any failure (DB missing, model can't load) goes back to the agent to explain
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                "content": f"The paper database could not be searched: {error}"}
    retrievals.append(retrieval)
    return {"type": "tool_result", "tool_use_id": block.id, "content": _format_passages(retrieval)}


def chat(history):
    """Agent task: reply to the latest user message, given the whole conversation so far.
    `history` is a list of {"role": "user"|"agent", "content": str}, oldest first.

    The agent decides whether to search the vector database. Returns {"content": reply text,
    "retrievals": [one entry per search: the query, its embedding and the top passages with theirs]}."""
    messages = [{"role": "assistant" if m["role"] == "agent" else "user", "content": m["content"]} for m in history]
    retrievals = []
    for search_round in range(MAX_SEARCH_ROUNDS + 1):
        out_of_searches = search_round == MAX_SEARCH_ROUNDS
        response = _create(messages, system=CHAT_SYSTEM, tools=[SEARCH_TOOL],
                           tool_choice={"type": "none" if out_of_searches else "auto"})
        if response.stop_reason != "tool_use":
            return {"content": _text(response), "retrievals": retrievals}
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": [
            _run_search(block, retrievals) for block in response.content if block.type == "tool_use"]})


if __name__ == "__main__":
    print(ask(" ".join(sys.argv[1:]) or "Say hello in one sentence."))
