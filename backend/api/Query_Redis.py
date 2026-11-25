"""Query_Redis: the agent's working memory — the messages of the conversation currently open.

Each conversation lives under one Redis list while it is open. When the user moves to another
conversation it is dumped to SQLite (Query_Lite) and removed from Redis.
Set REDIS_URL in .env to point elsewhere (default: a local Redis on port 6379).
"""

import json
import os

import redis

_redis = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)


def _key(conversation_id):
    return f"conversation:{conversation_id}:messages"


def is_loaded(conversation_id):
    """True if the conversation is currently held in Redis."""
    return bool(_redis.exists(_key(conversation_id)))


def _encode(role, content, retrievals=None):
    """One stored message; `retrievals` (the agent's vector-database searches) only when there were any."""
    return json.dumps({"role": role, "content": content, **({"retrievals": retrievals} if retrievals else {})})


def get_messages(conversation_id):
    """The conversation's messages, oldest first:
    [{"role": "user"|"agent", "content": str, "retrievals"?: [...]}, ...]."""
    return [json.loads(item) for item in _redis.lrange(_key(conversation_id), 0, -1)]


def append_message(conversation_id, role, content, retrievals=None):
    _redis.rpush(_key(conversation_id), _encode(role, content, retrievals))


def remove_last(conversation_id):
    """Undo the latest message (used when the agent fails to reply)."""
    _redis.rpop(_key(conversation_id))


def load(conversation_id, messages):
    """Replace whatever Redis holds for this conversation with `messages`."""
    key = _key(conversation_id)
    with _redis.pipeline() as pipe:
        pipe.delete(key)
        if messages:
            pipe.rpush(key, *(_encode(m["role"], m["content"], m.get("retrievals")) for m in messages))
        pipe.execute()


def drop(conversation_id):
    """Remove the conversation from Redis (after it has been dumped to SQLite)."""
    _redis.delete(_key(conversation_id))
