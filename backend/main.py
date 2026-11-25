"""KAI backend. Run from backend/:  uvicorn main:app --reload   (docs at http://127.0.0.1:8000/docs)"""

import threading

from fastapi import FastAPI

from api import Query_Chroma, Query_Lite, Search_Chroma, conversations
from api.pipeline import retrieve, store

# Load the agent's embedding model in the background so the first question doesn't wait for it.
threading.Thread(target=Search_Chroma.warm_up, daemon=True).start()

app = FastAPI(title="KAI backend")
app.include_router(retrieve.router)
app.include_router(store.router)
app.include_router(Query_Chroma.router)
app.include_router(Search_Chroma.router)
app.include_router(conversations.router)
app.include_router(Query_Lite.router)
