from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging
import asyncio

from app.services.data_aggregator import get_data_aggregator, DataAggregator
from app.services.hummingbot_strategy_manager import get_strategy_manager, StrategyManager
from app.services.risk_manager import get_risk_manager, RiskManager, RiskAlert
from app.services.websocket_manager import get_websocket_manager, WebSocketManager, MessageType, WebSocketMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/arbitrage", tags=["arbitrage"])
security = HTTPBearer()

# Pydantic模型
class ArbitrageOpportunity(BaseModel):
    """套利机会模型"""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    profit: float
    profit_percentage: float
    timestamp: str
    volume_limit: Optional[float] = None
    estimated_fees: Optional[float] = None
    risk_score: Optional[float] = None

class TickerData(BaseModel):
    """行情数据模型"""
    exchange: str
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    change_24h: Optional[float] = None
    timestamp: str

class OrderBookData(BaseModel):
    """订单簿数据模型"""
    exchange: str
    symbol: str
    bids: List[List[float]]
    asks: List[List[float]]
    timestamp: str
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    spread_percentage: Optional[float] = None

class StrategyConfig(BaseModel):
    """策略配置模型"""
    strategy_name: str
    trading_pair: str
    exchanges: List[str]
    min_profit_percentage: float = Field(default=0.1, ge=0.01, le=10.0)
    max_position_size: float = Field(default=1000.0, gt=0)
    stop_loss_percentage: float = Field(default=2.0, ge=0.1, le=10.0)
    take_profit_percentage: float = Field(default=1.0, ge=0.1, le=10.0)
    risk_level: str = Field(default="medium", regex="^(low|medium|high)$")
    auto_execute: bool = False
    max_daily_trades: int = Field(default=10, ge=1, le=100)
    additional_params: Optional[Dict[str, Any]] = None

class StrategyStatus(BaseModel):
    """策略状态模型"""
    strategy_id: str
    status: str
    created_at: str
    updated_at: str
    total_trades: int
    successful_trades: int
    total_profit: float
    current_positions: List[Dict[str, Any]]
    performance_metrics: Dict[str, float]

# API端点
@router.get("/opportunities", response_model=List[ArbitrageOpportunity])
async def get_arbitrage_opportunities(
    symbol: str = Query(..., description="交易对符号，如 BTCUSDT"),
    min_profit: float = Query(0.1, ge=0.01, le=10.0, description="最小利润百分比"),
    exchanges: Optional[str] = Query(None, description="指定交易所，用逗号分隔"),
    data_aggregator: DataAggregator = Depends(get_data_aggregator)
):
    """获取套利机会"""
    try:
        # 获取套利机会
        opportunities = await data_aggregator.get_arbitrage_opportunities(
            symbol=symbol.upper(),
            min_profit_percentage=min_profit
        )
        
        # 过滤指定交易所
        if exchanges:
            exchange_list = [ex.strip().lower() for ex in exchanges.split(',')]
            opportunities = [
                opp for opp in opportunities
                if opp['buy_exchange'].lower() in exchange_list or 
                   opp['sell_exchange'].lower() in exchange_list
            ]
        
        # 转换为响应模型
        result = []
        for opp in opportunities:
            result.append(ArbitrageOpportunity(
                symbol=opp['symbol'],
                buy_exchange=opp['buy_exchange'],
                sell_exchange=opp['sell_exchange'],
                buy_price=opp['buy_price'],
                sell_price=opp['sell_price'],
                profit=opp['profit'],
                profit_percentage=opp['profit_percentage'],
                timestamp=opp['timestamp']
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting arbitrage opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ticker/{exchange}/{symbol}", response_model=TickerData)
async def get_ticker(
    exchange: str,
    symbol: str,
    data_aggregator: DataAggregator = Depends(get_data_aggregator)
):
    """获取指定交易所的行情数据"""
    try:
        ticker = await data_aggregator.get_ticker(exchange.lower(), symbol.upper())
        
        if not ticker:
            raise HTTPException(status_code=404, detail="Ticker data not found")
        
        return TickerData(
            exchange=ticker.exchange,
            symbol=ticker.symbol,
            bid=float(ticker.bid),
            ask=float(ticker.ask),
            last=float(ticker.last),
            volume=float(ticker.volume),
            high_24h=float(ticker.high_24h) if ticker.high_24h else None,
            low_24h=float(ticker.low_24h) if ticker.low_24h else None,
            change_24h=float(ticker.change_24h) if ticker.change_24h else None,
            timestamp=ticker.timestamp.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ticker data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orderbook/{exchange}/{symbol}", response_model=OrderBookData)
async def get_orderbook(
    exchange: str,
    symbol: str,
    limit: int = Query(20, ge=5, le=100, description="订单簿深度"),
    data_aggregator: DataAggregator = Depends(get_data_aggregator)
):
    """获取指定交易所的订单簿数据"""
    try:
        orderbook = await data_aggregator.get_orderbook(exchange.lower(), symbol.upper(), limit)
        
        if not orderbook:
            raise HTTPException(status_code=404, detail="Orderbook data not found")
        
        return OrderBookData(
            exchange=orderbook.exchange,
            symbol=orderbook.symbol,
            bids=[[float(price), float(size)] for price, size in orderbook.bids],
            asks=[[float(price), float(size)] for price, size in orderbook.asks],
            timestamp=orderbook.timestamp.isoformat(),
            best_bid=float(orderbook.best_bid) if orderbook.best_bid else None,
            best_ask=float(orderbook.best_ask) if orderbook.best_ask else None,
            spread=float(orderbook.spread) if orderbook.spread else None,
            spread_percentage=float(orderbook.spread_percentage) if orderbook.spread_percentage else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting orderbook data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/exchanges/status")
async def get_exchange_status(
    data_aggregator: DataAggregator = Depends(get_data_aggregator)
):
    """获取所有交易所连接状态"""
    try:
        return {
            "exchanges": data_aggregator.get_exchange_status(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting exchange status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies", response_model=Dict[str, str])
async def create_strategy(
    config: StrategyConfig,
    strategy_manager: StrategyManager = Depends(get_strategy_manager)
):
    """创建套利策略"""
    try:
        strategy_id = await strategy_manager.create_strategy(
            strategy_name=config.strategy_name,
            trading_pair=config.trading_pair,
            exchanges=config.exchanges,
            config_params={
                "min_profit_percentage": config.min_profit_percentage,
                "max_position_size": config.max_position_size,
                "stop_loss_percentage": config.stop_loss_percentage,
                "take_profit_percentage": config.take_profit_percentage,
                "risk_level": config.risk_level,
                "auto_execute": config.auto_execute,
                "max_daily_trades": config.max_daily_trades,
                **(config.additional_params or {})
            }
        )
        
        return {
            "strategy_id": strategy_id,
            "status": "created",
            "message": "Strategy created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies", response_model=List[StrategyStatus])
async def list_strategies(
    status: Optional[str] = Query(None, description="过滤策略状态"),
    strategy_manager: StrategyManager = Depends(get_strategy_manager)
):
    """获取策略列表"""
    try:
        strategies = await strategy_manager.get_all_strategies()
        
        # 过滤状态
        if status:
            strategies = [s for s in strategies if s.get('status') == status]
        
        result = []
        for strategy in strategies:
            result.append(StrategyStatus(
                strategy_id=strategy['strategy_id'],
                status=strategy['status'],
                created_at=strategy['created_at'],
                updated_at=strategy['updated_at'],
                total_trades=strategy.get('total_trades', 0),
                successful_trades=strategy.get('successful_trades', 0),
                total_profit=strategy.get('total_profit', 0.0),
                current_positions=strategy.get('current_positions', []),
                performance_metrics=strategy.get('performance_metrics', {})
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies/{strategy_id}", response_model=StrategyStatus)
async def get_strategy(
    strategy_id: str,
    strategy_manager: StrategyManager = Depends(get_strategy_manager)
):
    """获取策略详情"""
    try:
        strategy = await strategy_manager.get_strategy_status(strategy_id)
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        return StrategyStatus(
            strategy_id=strategy['strategy_id'],
            status=strategy['status'],
            created_at=strategy['created_at'],
            updated_at=strategy['updated_at'],
            total_trades=strategy.get('total_trades', 0),
            successful_trades=strategy.get('successful_trades', 0),
            total_profit=strategy.get('total_profit', 0.0),
            current_positions=strategy.get('current_positions', []),
            performance_metrics=strategy.get('performance_metrics', {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies/{strategy_id}/start")
async def start_strategy(
    strategy_id: str,
    strategy_manager: StrategyManager = Depends(get_strategy_manager)
):
    """启动策略"""
    try:
        success = await strategy_manager.start_strategy(strategy_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start strategy")
        
        return {
            "strategy_id": strategy_id,
            "status": "started",
            "message": "Strategy started successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: str,
    strategy_manager: StrategyManager = Depends(get_strategy_manager)
):
    """停止策略"""
    try:
        success = await strategy_manager.stop_strategy(strategy_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to stop strategy")
        
        return {
            "strategy_id": strategy_id,
            "status": "stopped",
            "message": "Strategy stopped successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    strategy_manager: StrategyManager = Depends(get_strategy_manager)
):
    """删除策略"""
    try:
        success = await strategy_manager.delete_strategy(strategy_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete strategy")
        
        return {
            "strategy_id": strategy_id,
            "status": "deleted",
            "message": "Strategy deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/risk/summary")
async def get_risk_summary(
    risk_manager: RiskManager = Depends(get_risk_manager)
):
    """获取风险摘要"""
    try:
        return risk_manager.get_risk_summary()
    except Exception as e:
        logger.error(f"Error getting risk summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/risk/alerts")
async def get_risk_alerts(
    limit: int = Query(50, ge=1, le=200, description="返回的警报数量"),
    risk_level: Optional[str] = Query(None, description="过滤风险等级"),
    risk_manager: RiskManager = Depends(get_risk_manager)
):
    """获取风险警报"""
    try:
        alerts = risk_manager.alerts[-limit:]
        
        # 过滤风险等级
        if risk_level:
            alerts = [alert for alert in alerts if alert.risk_level.value == risk_level]
        
        return {
            "alerts": [
                {
                    "alert_type": alert.alert_type.value,
                    "risk_level": alert.risk_level.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "strategy_id": alert.strategy_id,
                    "exchange": alert.exchange,
                    "trading_pair": alert.trading_pair,
                    "current_value": alert.current_value,
                    "threshold_value": alert.threshold_value,
                    "recommended_action": alert.recommended_action
                }
                for alert in alerts
            ],
            "total_count": len(alerts)
        }
        
    except Exception as e:
        logger.error(f"Error getting risk alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/risk/check")
async def check_risks(
    risk_manager: RiskManager = Depends(get_risk_manager)
):
    """手动触发风险检查"""
    try:
        alerts = await risk_manager.check_all_risks()
        
        return {
            "alerts_generated": len(alerts),
            "emergency_stop_active": risk_manager.emergency_stop_triggered,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking risks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket端点
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """WebSocket连接端点"""
    client_id = None
    
    try:
        # 建立连接
        client_id = await websocket_manager.connect(websocket)
        
        # 保持连接
        while True:
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if client_id:
            await websocket_manager.disconnect(client_id)

@router.get("/ws/stats")
async def get_websocket_stats(
    websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """获取WebSocket连接统计"""
    try:
        return websocket_manager.get_connection_stats()
    except Exception as e:
        logger.error(f"Error getting WebSocket stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 健康检查端点
@router.get("/health")
async def health_check(
    data_aggregator: DataAggregator = Depends(get_data_aggregator),
    strategy_manager: StrategyManager = Depends(get_strategy_manager),
    risk_manager: RiskManager = Depends(get_risk_manager)
):
    """健康检查"""
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "data_aggregator": "running",
                "strategy_manager": "running",
                "risk_manager": "running",
                "exchanges": data_aggregator.get_exchange_status()
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# 系统信息端点
@router.get("/info")
async def get_system_info():
    """获取系统信息"""
    try:
        return {
            "name": "Arbitrage Trading System",
            "version": "1.0.0",
            "description": "Advanced cryptocurrency arbitrage trading platform",
            "features": [
                "Multi-exchange arbitrage detection",
                "Automated strategy execution",
                "Real-time risk management",
                "WebSocket data streaming",
                "Hummingbot integration"
            ],
            "supported_exchanges": ["binance", "okx", "huobi"],
            "api_version": "v1",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(status_code=500, detail=str(e))