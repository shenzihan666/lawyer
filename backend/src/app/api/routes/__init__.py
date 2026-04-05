from .chat import router as chat_router
from .contract_review import router as contract_review_router
from .documents import router as router
from .search import router as search_router

__all__ = ["router", "chat_router", "contract_review_router", "search_router"]
