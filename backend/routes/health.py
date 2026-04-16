from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": "ogham-chat-api", "status": "ok"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
