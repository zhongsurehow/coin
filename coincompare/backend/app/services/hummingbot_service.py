"""Hummingbot集成服务

提供与Hummingbot的集成功能，包括策略管理、交易执行、状态监控等。
"""

import asyncio
import json
import websockets
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..database import get_async_session
from ..models import Strategy, Trade, ArbitrageOpportunity, Exchange, TradingPair
from ..config import settings
from .logging_service import logger
from .exchange_service import ExchangeService
from .risk_service import RiskService


class HummingbotService:
    """Hummingbot集成服务类"""
    
    def __init__(self):
        self.base_url = settings.HUMMINGBOT_API_URL
        self.username = settings.HUMMINGBOT_USERNAME
        self.password = settings.HUMMINGBOT_PASSWORD
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection: Optional[websockets.WebSocketServerProtocol] = None
        self.is_connected = False
        self.exchange_service = ExchangeService()
        self.risk_service = RiskService()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
    
    async def connect(self) -> bool:
        """连接到Hummingbot"""
        try:
            if not settings.HUMMINGBOT_ENABLED:
                logger.warning("Hummingbot集成未启用")
                return False
            
            # 创建HTTP会话
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # 认证
            auth_success = await self._authenticate()
            if not auth_success:
                logger.error("Hummingbot认证失败")
                return False
            
            # 建立WebSocket连接
            ws_success = await self._connect_websocket()
            if not ws_success:
                logger.warning("Hummingbot WebSocket连接失败，将使用HTTP轮询")
            
            self.is_connected = True
            logger.info("Hummingbot连接成功")
            return True
            
        except Exception as e:
            logger.error(f"连接Hummingbot失败: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self):
        """断开Hummingbot连接"""
        try:
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            if self.session:
                await self.session.close()
                self.session = None
            
            self.is_connected = False
            logger.info("Hummingbot连接已断开")
            
        except Exception as e:
            logger.error(f"断开Hummingbot连接时出错: {e}")
    
    async def _authenticate(self) -> bool:
        """认证到Hummingbot"""
        try:
            auth_data = {
                "username": self.username,
                "password": self.password
            }
            
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json=auth_data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    token = result.get("access_token")
                    if token:
                        self.session.headers.update({
                            "Authorization": f"Bearer {token}"
                        })
                        return True
                
                logger.error(f"认证失败，状态码: {response.status}")
                return False
                
        except Exception as e:
            logger.error(f"认证过程中出错: {e}")
            return False
    
    async def _connect_websocket(self) -> bool:
        """建立WebSocket连接"""
        try:
            ws_url = f"{self.base_url.replace('http', 'ws')}/ws"
            self.ws_connection = await websockets.connect(
                ws_url,
                extra_headers=self.session.headers
            )
            
            # 启动消息监听任务
            asyncio.create_task(self._listen_websocket())
            return True
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False
    
    async def _listen_websocket(self):
        """监听WebSocket消息"""
        try:
            async for message in self.ws_connection:
                data = json.loads(message)
                await self._handle_websocket_message(data)
                
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket连接已关闭")
        except Exception as e:
            logger.error(f"WebSocket监听出错: {e}")
    
    async def _handle_websocket_message(self, data: Dict[str, Any]):
        """处理WebSocket消息"""
        try:
            message_type = data.get("type")
            
            if message_type == "trade_update":
                await self._handle_trade_update(data)
            elif message_type == "strategy_update":
                await self._handle_strategy_update(data)
            elif message_type == "error":
                await self._handle_error_message(data)
            else:
                logger.debug(f"未知消息类型: {message_type}")
                
        except Exception as e:
            logger.error(f"处理WebSocket消息失败: {e}")
    
    async def _handle_trade_update(self, data: Dict[str, Any]):
        """处理交易更新消息"""
        try:
            trade_data = data.get("data", {})
            trade_id = trade_data.get("trade_id")
            
            if trade_id:
                async with get_async_session() as session:
                    # 更新交易记录
                    await session.execute(
                        update(Trade)
                        .where(Trade.external_id == trade_id)
                        .values(
                            status=trade_data.get("status"),
                            executed_price=Decimal(str(trade_data.get("price", 0))),
                            executed_quantity=Decimal(str(trade_data.get("quantity", 0))),
                            updated_at=datetime.utcnow()
                        )
                    )
                    await session.commit()
                    
                logger.info(f"交易更新: {trade_id} - {trade_data.get('status')}")
                
        except Exception as e:
            logger.error(f"处理交易更新失败: {e}")
    
    async def _handle_strategy_update(self, data: Dict[str, Any]):
        """处理策略更新消息"""
        try:
            strategy_data = data.get("data", {})
            strategy_id = strategy_data.get("strategy_id")
            
            if strategy_id:
                async with get_async_session() as session:
                    # 更新策略状态
                    await session.execute(
                        update(Strategy)
                        .where(Strategy.external_id == strategy_id)
                        .values(
                            status=strategy_data.get("status"),
                            updated_at=datetime.utcnow()
                        )
                    )
                    await session.commit()
                    
                logger.info(f"策略更新: {strategy_id} - {strategy_data.get('status')}")
                
        except Exception as e:
            logger.error(f"处理策略更新失败: {e}")
    
    async def _handle_error_message(self, data: Dict[str, Any]):
        """处理错误消息"""
        error_data = data.get("data", {})
        error_message = error_data.get("message", "未知错误")
        logger.error(f"Hummingbot错误: {error_message}")
    
    async def create_strategy(self, strategy_config: Dict[str, Any]) -> Optional[str]:
        """创建交易策略"""
        try:
            if not self.is_connected:
                await self.connect()
            
            async with self.session.post(
                f"{self.base_url}/strategies",
                json=strategy_config
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    strategy_id = result.get("strategy_id")
                    logger.info(f"策略创建成功: {strategy_id}")
                    return strategy_id
                else:
                    logger.error(f"策略创建失败，状态码: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return None
    
    async def start_strategy(self, strategy_id: str) -> bool:
        """启动策略"""
        try:
            async with self.session.post(
                f"{self.base_url}/strategies/{strategy_id}/start"
            ) as response:
                if response.status == 200:
                    logger.info(f"策略启动成功: {strategy_id}")
                    return True
                else:
                    logger.error(f"策略启动失败，状态码: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            return False
    
    async def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        try:
            async with self.session.post(
                f"{self.base_url}/strategies/{strategy_id}/stop"
            ) as response:
                if response.status == 200:
                    logger.info(f"策略停止成功: {strategy_id}")
                    return True
                else:
                    logger.error(f"策略停止失败，状态码: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return False
    
    async def get_strategy_status(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取策略状态"""
        try:
            async with self.session.get(
                f"{self.base_url}/strategies/{strategy_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取策略状态失败，状态码: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取策略状态失败: {e}")
            return None
    
    async def execute_arbitrage_strategy(self, opportunity: ArbitrageOpportunity) -> Optional[str]:
        """执行套利策略"""
        try:
            # 风险检查
            risk_check = await self.risk_service.check_arbitrage_risk(opportunity)
            if not risk_check["approved"]:
                logger.warning(f"套利机会风险检查未通过: {risk_check['reason']}")
                return None
            
            # 构建策略配置
            strategy_config = {
                "strategy_type": "arbitrage",
                "buy_exchange": opportunity.buy_exchange,
                "sell_exchange": opportunity.sell_exchange,
                "trading_pair": opportunity.trading_pair,
                "buy_price": float(opportunity.buy_price),
                "sell_price": float(opportunity.sell_price),
                "quantity": float(opportunity.quantity),
                "expected_profit": float(opportunity.profit_amount),
                "max_slippage": 0.001,  # 0.1% 滑点
                "timeout": 30  # 30秒超时
            }
            
            # 创建并启动策略
            strategy_id = await self.create_strategy(strategy_config)
            if strategy_id:
                success = await self.start_strategy(strategy_id)
                if success:
                    # 记录到数据库
                    await self._record_arbitrage_execution(opportunity, strategy_id)
                    return strategy_id
            
            return None
            
        except Exception as e:
            logger.error(f"执行套利策略失败: {e}")
            return None
    
    async def _record_arbitrage_execution(self, opportunity: ArbitrageOpportunity, strategy_id: str):
        """记录套利执行"""
        try:
            async with get_async_session() as session:
                # 创建交易记录
                trade = Trade(
                    user_id=1,  # 系统用户
                    strategy_id=opportunity.strategy_id,
                    exchange_id=opportunity.buy_exchange_id,
                    trading_pair_id=opportunity.trading_pair_id,
                    trade_type="arbitrage",
                    side="buy",
                    quantity=opportunity.quantity,
                    price=opportunity.buy_price,
                    status="pending",
                    external_id=strategy_id
                )
                session.add(trade)
                
                # 更新套利机会状态
                await session.execute(
                    update(ArbitrageOpportunity)
                    .where(ArbitrageOpportunity.id == opportunity.id)
                    .values(
                        status="executing",
                        updated_at=datetime.utcnow()
                    )
                )
                
                await session.commit()
                logger.info(f"套利执行记录已保存: {strategy_id}")
                
        except Exception as e:
            logger.error(f"记录套利执行失败: {e}")
    
    async def get_active_strategies(self) -> List[Dict[str, Any]]:
        """获取活跃策略列表"""
        try:
            async with self.session.get(
                f"{self.base_url}/strategies",
                params={"status": "active"}
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取活跃策略失败，状态码: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取活跃策略失败: {e}")
            return []
    
    async def get_portfolio_balance(self) -> Optional[Dict[str, Any]]:
        """获取投资组合余额"""
        try:
            async with self.session.get(
                f"{self.base_url}/portfolio/balance"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取投资组合余额失败，状态码: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取投资组合余额失败: {e}")
            return None
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self.is_connected:
                return False
            
            async with self.session.get(
                f"{self.base_url}/health"
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"Hummingbot健康检查失败: {e}")
            return False
    
    async def sync_strategies_from_db(self):
        """从数据库同步策略到Hummingbot"""
        try:
            async with get_async_session() as session:
                # 获取需要同步的策略
                result = await session.execute(
                    select(Strategy)
                    .where(Strategy.status == "pending")
                    .where(Strategy.external_id.is_(None))
                )
                strategies = result.scalars().all()
                
                for strategy in strategies:
                    # 构建策略配置
                    config = json.loads(strategy.config)
                    
                    # 创建策略
                    external_id = await self.create_strategy(config)
                    if external_id:
                        # 更新数据库中的外部ID
                        await session.execute(
                            update(Strategy)
                            .where(Strategy.id == strategy.id)
                            .values(
                                external_id=external_id,
                                status="created",
                                updated_at=datetime.utcnow()
                            )
                        )
                        
                        # 如果策略应该立即启动
                        if strategy.auto_start:
                            await self.start_strategy(external_id)
                            await session.execute(
                                update(Strategy)
                                .where(Strategy.id == strategy.id)
                                .values(
                                    status="active",
                                    updated_at=datetime.utcnow()
                                )
                            )
                
                await session.commit()
                logger.info(f"同步了 {len(strategies)} 个策略到Hummingbot")
                
        except Exception as e:
            logger.error(f"同步策略失败: {e}")


# 全局Hummingbot服务实例
hummingbot_service = HummingbotService()