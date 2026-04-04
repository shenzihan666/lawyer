from .chat import router as chat_router
from .documents import router as router
from .search import router as search_router

__all__ = ["router", "chat_router", "search_router"]
