"""Query_Lite: plain storage in SQLite (data/database/sqllite/kai.db), separate from the research pipeline.

Saves conversations: each one's title and the messages between the user and the agent.
"""

import json
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "database" / "sqllite" / "kai.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,                       -- id chosen by the UI (a UUID)
    title       TEXT,                                   -- NULL until the agent names it
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'agent')),
    content          TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    retrievals       TEXT                                    -- JSON: the agent's vector-database searches; NULL if none
);

CREATE INDEX IF NOT EXISTS messages_by_conversation ON messages (conversation_id, id);
"""

router = APIRouter()


def _connect():
    """Open kai.db (creating the tables if needed); rows behave like dicts."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    if "retrievals" not in [row["name"] for row in conn.execute("PRAGMA table_info(messages)")]:
        conn.execute("ALTER TABLE messages ADD COLUMN retrievals TEXT")  # kai.db created before retrieval existed
    return conn


def _message(row):
    """A message row as a dict, with its retrievals decoded (and left out when the agent didn't search)."""
    message = dict(row)
    retrievals = message.pop("retrievals", None)
    return {**message, "retrievals": json.loads(retrievals)} if retrievals else message


def _get_conversation(conn, conversation_id):
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Conversation {conversation_id} not found")
    return dict(row)


# ---- Helpers used by the chat flow (Redis <-> SQLite) ----

def read_messages(conversation_id):
    """Saved messages of a conversation, oldest first (empty if it has none or doesn't exist)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, retrievals FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
    return [_message(row) for row in rows]


def replace_messages(conversation_id, messages):
    """Save a conversation's full message list (the dump from Redis), replacing what was stored before."""
    new_rows = [(m["role"], m["content"], json.dumps(m["retrievals"]) if m.get("retrievals") else None)
                for m in messages]
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO conversations (id) VALUES (?)", (conversation_id,))
        old_rows = [tuple(row) for row in conn.execute(
            "SELECT role, content, retrievals FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))]
        if old_rows == new_rows:
            return  # nothing new; keep its place in the sidebar
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.executemany(
            "INSERT INTO messages (conversation_id, role, content, retrievals) VALUES (?, ?, ?, ?)",
            [(conversation_id, *row) for row in new_rows],
        )
        conn.execute("UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conversation_id,))


# ---- Routes ----

class NewConversation(BaseModel):
    id: str = Field(min_length=1)
    title: str | None = None


class TitleUpdate(BaseModel):
    title: str = Field(min_length=1)


class NewMessage(BaseModel):
    role: Literal["user", "agent"]
    content: str = Field(min_length=1)


@router.get("/conversations")
def list_conversations():
    """All saved conversations, most recently active first."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC, created_at DESC").fetchall()
    return [dict(row) for row in rows]


@router.post("/conversations", status_code=201)
def create_conversation(body: NewConversation):
    """Save a new conversation (title may be empty until the agent names it)."""
    with _connect() as conn:
        try:
            conn.execute("INSERT INTO conversations (id, title) VALUES (?, ?)", (body.id, body.title))
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, f"Conversation {body.id} already exists") from error
        return _get_conversation(conn, body.id)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, body: TitleUpdate):
    """Save the conversation's title (e.g. once the agent has named it)."""
    with _connect() as conn:
        _get_conversation(conn, conversation_id)
        conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (body.title, conversation_id))
        return _get_conversation(conn, conversation_id)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """One conversation with all its messages, in the order they were sent."""
    with _connect() as conn:
        conversation = _get_conversation(conn, conversation_id)
        rows = conn.execute(
            "SELECT id, role, content, created_at, retrievals FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return {**conversation, "messages": [_message(row) for row in rows]}


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def add_message(conversation_id: str, body: NewMessage):
    """Save one message from the user or the agent."""
    with _connect() as conn:
        _get_conversation(conn, conversation_id)
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, body.role, body.content),
        )
        conn.execute("UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conversation_id,))
        row = conn.execute("SELECT id, role, content, created_at FROM messages WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    return dict(row)
