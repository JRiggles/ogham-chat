from fastapi import APIRouter

router = APIRouter()


@router.get('/')
async def root() -> dict[str, str]:
    """Return service metadata for basic API reachability checks."""
    return {'service': 'ogham-chat-api', 'status': 'ok'}


@router.get('/health')
async def health() -> dict[str, str]:
    """Return a lightweight health status for liveness checks."""
    return {'status': 'healthy'}
