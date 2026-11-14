"""Conversations: the agent's chat flow and sidebar tasks.

The open conversation lives in Redis (Query_Redis), which is where the agent reads it from.
Switching conversations dumps the current one to SQLite (Query_Lite) and loads the next one
from SQLite into Redis.
"""

import anthropic
import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent import chat, name_conversation
from api import Query_Lite, Query_Redis

router = APIRouter()


class TitleRequest(BaseModel):
    question: str = Field(min_length=1)
    context: str | None = None


class OpenRequest(BaseModel):
    previous_id: str | None = None  # the conversation being left; it gets dumped to SQLite


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)


def _dump(conversation_id):
    """Save a conversation from Redis to SQLite and remove it from Redis."""
    if Query_Redis.is_loaded(conversation_id):
        Query_Lite.replace_messages(conversation_id, Query_Redis.get_messages(conversation_id))
        Query_Redis.drop(conversation_id)


def _redis_errors(handler):
    """Turn 'Redis is not running' into a clear 503 instead of a stack trace."""
    try:
        return handler()
    except redis.ConnectionError as error:
        raise HTTPException(503, "Redis is not running (start it with: docker run -d -p 6379:6379 redis)") from error


@router.post("/conversations/title")
def conversation_title(request: TitleRequest):
    """Ask the agent for a short title for a conversation, based on its first question."""
    try:
        return {"title": name_conversation(request.question, request.context)}
    except anthropic.APIError as error:
        raise HTTPException(502, f"Agent could not name the conversation: {error}") from error


@router.post("/conversations/{conversation_id}/open")
def open_conversation(conversation_id: str, request: OpenRequest):
    """Move to a conversation: dump the one being left, then load this one's history into Redis."""
    def run():
        if request.previous_id and request.previous_id != conversation_id:
            _dump(request.previous_id)
        messages = Query_Lite.read_messages(conversation_id)
        Query_Redis.load(conversation_id, messages)
        return {"id": conversation_id, "messages": messages}
    return _redis_errors(run)


@router.post("/conversations/{conversation_id}/dump")
def dump_conversation(conversation_id: str):
    """Leave a conversation without opening another (e.g. 'New chat'): save it to SQLite and clear Redis."""
    def run():
        _dump(conversation_id)
        return {"id": conversation_id, "dumped": True}
    return _redis_errors(run)


@router.post("/conversations/{conversation_id}/chat")
def send_message(conversation_id: str, request: ChatRequest):
    """Send the user's message to the agent. The agent reads the conversation so far from Redis.
    The reply includes `retrievals`: every vector-database search the agent chose to run for it."""
    def run():
        if not Query_Redis.is_loaded(conversation_id):  # e.g. after a backend restart
            Query_Redis.load(conversation_id, Query_Lite.read_messages(conversation_id))
        Query_Redis.append_message(conversation_id, "user", request.content)
        try:
            reply = chat(Query_Redis.get_messages(conversation_id))
        except (anthropic.APIError, RuntimeError) as error:
            Query_Redis.remove_last(conversation_id)  # don't keep a question with no answer
            raise HTTPException(502, f"Agent could not reply: {error}") from error
        Query_Redis.append_message(conversation_id, "agent", reply["content"], reply["retrievals"])
        return {"role": "agent", **reply}
    return _redis_errors(run)
