"""API路由模块

包含所有API端点的路由定义。
"""

from fastapi import APIRouter

# 导入现有路由
from .arbitrage import router as arbitrage_router
from .deposit_withdrawal import router as deposit_withdrawal_router
from .strategy import router as strategy_router
from .user import router as user_router
from .market_data import router as market_data_router
from .websocket import router as websocket_router
from .unified_transfer import router as unified_transfer_router

# 创建主路由器
api_router = APIRouter(prefix="/api/v1")

# 注册所有子路由
api_router.include_router(
    arbitrage_router,
    prefix="/arbitrage",
    tags=["套利机会"]
)

api_router.include_router(
    deposit_withdrawal_router,
    prefix="/deposit-withdrawal",
    tags=["充提管理"]
)

api_router.include_router(
    strategy_router,
    prefix="/strategy",
    tags=["策略管理"]
)

api_router.include_router(
    user_router,
    prefix="/user",
    tags=["用户管理"]
)

api_router.include_router(
    market_data_router,
    prefix="/market-data",
    tags=["市场数据"]
)

api_router.include_router(
    websocket_router,
    tags=["WebSocket"]
)

api_router.include_router(
    unified_transfer_router,
    prefix="/unified-transfer",
    tags=["统一转账"]
)

__all__ = [
    "api_router",
    "arbitrage_router",
    "deposit_withdrawal_router",
    "strategy_router",
    "user_router",
    "market_data_router",
    "websocket_router",
    "unified_transfer_router"
]