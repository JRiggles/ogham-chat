import os

from fastapi import APIRouter, FastAPI

from backend.routes.health import router as health_router
from backend.routes.messages import create_messages_router
from backend.routes.ws import create_ws_router
from backend.store.base import MessageStoreProtocol
from backend.store.memory import MemoryMessageStore
from backend.store.sql import SQLMessageStore
from backend.ws.manager import ConnectionManager

app = FastAPI(title="Ogham Chat API", version="0.1.0")
v1 = APIRouter(prefix="/api/v1", tags=["v1"])

database_url = os.getenv("DATABASE_URL")
store: MessageStoreProtocol
store = SQLMessageStore(database_url) if database_url else MemoryMessageStore()
ws_manager = ConnectionManager()

v1.include_router(health_router)
v1.include_router(create_messages_router(ws_manager, store))
v1.include_router(create_ws_router(ws_manager, store))

app.include_router(v1)
