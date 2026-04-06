from fastapi import APIRouter

from app.api.routes.agent_chat import router as agent_chat_router
from app.api.routes.case_search_assets import router as case_search_assets_router
from app.api.routes.case_searches import router as case_searches_router
from app.api.routes.chat import router as chat_router
from app.api.routes.contract_review import router as contract_review_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.documents import router as documents_router
from app.api.routes.opponent_analyses import router as opponent_analyses_router
from app.api.routes.search import router as search_router

api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(agent_chat_router)
api_router.include_router(contract_review_router)
api_router.include_router(documents_router)
api_router.include_router(search_router)
api_router.include_router(case_searches_router)
api_router.include_router(case_search_assets_router)
api_router.include_router(opponent_analyses_router)
