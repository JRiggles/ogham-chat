import os
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.routes.health import router as health_router
from backend.routes.messages import create_messages_router
from backend.routes.ws import create_ws_router
from backend.store.base import MessageStoreProtocol
from backend.store.memory import MemoryMessageStore
from backend.store.sql import SQLMessageStore
from backend.ws.manager import ConnectionManager

limiter = Limiter(key_func=get_remote_address, default_limits=['120/minute'])
app = FastAPI(title='Ogham Chat API', version='0.1.0')
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # type: ignore[arg-type]
)
v1 = APIRouter(prefix='/api/v1', tags=['v1'])

database_url = os.getenv('DATABASE_URL')
store: MessageStoreProtocol
store = SQLMessageStore(database_url) if database_url else MemoryMessageStore()
ws_manager = ConnectionManager()

v1.include_router(health_router)
v1.include_router(create_messages_router(ws_manager, store))
v1.include_router(create_ws_router(ws_manager, store))

app.include_router(v1)

_LANDING_PATH = Path(__file__).resolve().parent / 'backend' / 'static' / 'landing.html'
_LANDING_HTML = _LANDING_PATH.read_text(encoding='utf-8')


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
async def landing_page() -> str:
    """Serve the landing page at the application root."""
    return _LANDING_HTML
