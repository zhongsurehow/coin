from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import json

from ..models.strategy import Strategy, StrategyExecution, StrategyType, StrategyStatus, ExecutionStatus
from ..services.hummingbot_client import hummingbot_manager
from ..database import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)
security = HTTPBearer()

router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove disconnected connections
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Pydantic models for API
class StrategyCreateRequest(BaseModel):
    name: str = Field(..., description="Strategy name")
    strategy_type: str = Field(..., description="Strategy type")
    description: Optional[str] = Field(None, description="Strategy description")
    config: Dict[str, Any] = Field(..., description="Strategy configuration")
    risk_params: Dict[str, Any] = Field(default_factory=dict, description="Risk parameters")
    
    @validator('strategy_type')
    def validate_strategy_type(cls, v):
        valid_types = [t.value for t in StrategyType]
        if v not in valid_types:
            raise ValueError(f'Strategy type must be one of: {valid_types}')
        return v

class StrategyUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    config: Optional[Dict[str, Any]] = Field(None, description="Strategy configuration")
    risk_params: Optional[Dict[str, Any]] = Field(None, description="Risk parameters")
    status: Optional[str] = Field(None, description="Strategy status")
    
    @validator('status')
    def validate_status(cls, v):
        if v is not None:
            valid_statuses = [s.value for s in StrategyStatus]
            if v not in valid_statuses:
                raise ValueError(f'Status must be one of: {valid_statuses}')
        return v

class StrategyResponse(BaseModel):
    id: int
    name: str
    strategy_type: str
    description: Optional[str]
    config: Dict[str, Any]
    risk_params: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    total_profit: float
    total_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    is_active: bool

class StrategyExecutionRequest(BaseModel):
    strategy_id: int = Field(..., description="Strategy ID")
    execution_params: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    auto_restart: bool = Field(False, description="Auto restart on failure")
    max_runtime: Optional[int] = Field(None, description="Maximum runtime in minutes")

class StrategyExecutionResponse(BaseModel):
    id: int
    strategy_id: int
    status: str
    execution_params: Dict[str, Any]
    started_at: datetime
    ended_at: Optional[datetime]
    profit_loss: float
    trades_count: int
    error_message: Optional[str]
    hummingbot_instance_id: Optional[str]
    performance_metrics: Dict[str, Any]

class PerformanceMetrics(BaseModel):
    total_profit: float
    total_trades: int
    win_rate: float
    avg_profit_per_trade: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    volatility: float
    max_profit: float
    max_loss: float
    profit_factor: float
    avg_trade_duration: float  # in minutes

class StrategyBacktestRequest(BaseModel):
    strategy_config: Dict[str, Any] = Field(..., description="Strategy configuration")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: float = Field(10000.0, description="Initial capital")
    exchanges: List[str] = Field(..., description="Exchanges to use")
    trading_pairs: List[str] = Field(..., description="Trading pairs")

class BacktestResult(BaseModel):
    strategy_config: Dict[str, Any]
    performance: PerformanceMetrics
    trades: List[Dict[str, Any]]
    equity_curve: List[Dict[str, float]]  # timestamp -> equity value
    drawdown_curve: List[Dict[str, float]]  # timestamp -> drawdown
    execution_time: float  # seconds

# Helper function to get user_id from token
def get_user_id_from_token(token: str) -> int:
    # This would decode the JWT token and extract user_id
    # For now, return a dummy user_id
    return 1

@router.post("/strategies", response_model=StrategyResponse)
async def create_strategy(
    request: StrategyCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Create a new trading strategy"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # Validate strategy configuration
        strategy_type = StrategyType(request.strategy_type)
        
        # Create strategy instance
        strategy = Strategy(
            user_id=user_id,
            name=request.name,
            strategy_type=strategy_type,
            description=request.description,
            config=request.config,
            risk_params=request.risk_params,
            status=StrategyStatus.INACTIVE
        )
        
        # Validate configuration
        if not strategy.validate_config():
            raise HTTPException(status_code=400, detail="Invalid strategy configuration")
        
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        
        return StrategyResponse(
            id=strategy.id,
            name=strategy.name,
            strategy_type=strategy.strategy_type.value,
            description=strategy.description,
            config=strategy.config,
            risk_params=strategy.risk_params,
            status=strategy.status.value,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            total_profit=strategy.total_profit,
            total_trades=strategy.total_trades,
            win_rate=strategy.win_rate,
            max_drawdown=strategy.max_drawdown,
            sharpe_ratio=strategy.sharpe_ratio,
            is_active=strategy.is_active
        )
    
    except Exception as e:
        logger.error(f"Error creating strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies", response_model=List[StrategyResponse])
async def get_strategies(
    status: Optional[str] = Query(None, description="Filter by status"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    limit: int = Query(50, ge=1, le=200, description="Number of strategies to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Get user's trading strategies"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(Strategy.user_id == user_id)
        
        if status:
            query = query.where(Strategy.status == StrategyStatus(status))
        
        if strategy_type:
            query = query.where(Strategy.strategy_type == StrategyType(strategy_type))
        
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        strategies = result.scalars().all()
        
        return [
            StrategyResponse(
                id=strategy.id,
                name=strategy.name,
                strategy_type=strategy.strategy_type.value,
                description=strategy.description,
                config=strategy.config,
                risk_params=strategy.risk_params,
                status=strategy.status.value,
                created_at=strategy.created_at,
                updated_at=strategy.updated_at,
                total_profit=strategy.total_profit,
                total_trades=strategy.total_trades,
                win_rate=strategy.win_rate,
                max_drawdown=strategy.max_drawdown,
                sharpe_ratio=strategy.sharpe_ratio,
                is_active=strategy.is_active
            )
            for strategy in strategies
        ]
    
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Get a specific strategy"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        return StrategyResponse(
            id=strategy.id,
            name=strategy.name,
            strategy_type=strategy.strategy_type.value,
            description=strategy.description,
            config=strategy.config,
            risk_params=strategy.risk_params,
            status=strategy.status.value,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            total_profit=strategy.total_profit,
            total_trades=strategy.total_trades,
            win_rate=strategy.win_rate,
            max_drawdown=strategy.max_drawdown,
            sharpe_ratio=strategy.sharpe_ratio,
            is_active=strategy.is_active
        )
    
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/strategies/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    request: StrategyUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Update a strategy"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Check if strategy is running
        if strategy.is_active and request.config:
            raise HTTPException(status_code=400, detail="Cannot update config while strategy is running")
        
        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if field == 'status':
                setattr(strategy, field, StrategyStatus(value))
            else:
                setattr(strategy, field, value)
        
        # Validate configuration if updated
        if request.config and not strategy.validate_config():
            raise HTTPException(status_code=400, detail="Invalid strategy configuration")
        
        await db.commit()
        await db.refresh(strategy)
        
        return StrategyResponse(
            id=strategy.id,
            name=strategy.name,
            strategy_type=strategy.strategy_type.value,
            description=strategy.description,
            config=strategy.config,
            risk_params=strategy.risk_params,
            status=strategy.status.value,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            total_profit=strategy.total_profit,
            total_trades=strategy.total_trades,
            win_rate=strategy.win_rate,
            max_drawdown=strategy.max_drawdown,
            sharpe_ratio=strategy.sharpe_ratio,
            is_active=strategy.is_active
        )
    
    except Exception as e:
        logger.error(f"Error updating strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Delete a strategy"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        if strategy.is_active:
            raise HTTPException(status_code=400, detail="Cannot delete active strategy")
        
        await db.delete(strategy)
        await db.commit()
        
        return {"message": "Strategy deleted successfully"}
    
    except Exception as e:
        logger.error(f"Error deleting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies/{strategy_id}/start", response_model=StrategyExecutionResponse)
async def start_strategy(
    strategy_id: int,
    request: StrategyExecutionRequest,
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Start strategy execution"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        if strategy.is_active:
            raise HTTPException(status_code=400, detail="Strategy is already running")
        
        # Start strategy execution
        execution = await strategy.start_execution(
            execution_params=request.execution_params,
            auto_restart=request.auto_restart,
            max_runtime=request.max_runtime
        )
        
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        
        # Start Hummingbot instance if needed
        if strategy.strategy_type in [StrategyType.ARBITRAGE, StrategyType.MARKET_MAKING]:
            instance_id = await hummingbot_manager.start_strategy(
                strategy_config=strategy.config,
                execution_id=execution.id
            )
            execution.hummingbot_instance_id = instance_id
            await db.commit()
        
        # Broadcast strategy start event
        await manager.broadcast(json.dumps({
            "type": "strategy_started",
            "strategy_id": strategy_id,
            "execution_id": execution.id,
            "timestamp": datetime.now().isoformat()
        }))
        
        return StrategyExecutionResponse(
            id=execution.id,
            strategy_id=execution.strategy_id,
            status=execution.status.value,
            execution_params=execution.execution_params,
            started_at=execution.started_at,
            ended_at=execution.ended_at,
            profit_loss=execution.profit_loss,
            trades_count=execution.trades_count,
            error_message=execution.error_message,
            hummingbot_instance_id=execution.hummingbot_instance_id,
            performance_metrics=execution.performance_metrics
        )
    
    except Exception as e:
        logger.error(f"Error starting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Stop strategy execution"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        if not strategy.is_active:
            raise HTTPException(status_code=400, detail="Strategy is not running")
        
        # Stop strategy execution
        await strategy.stop_execution()
        
        # Stop Hummingbot instance if running
        active_execution = await strategy.get_active_execution()
        if active_execution and active_execution.hummingbot_instance_id:
            await hummingbot_manager.stop_strategy(active_execution.hummingbot_instance_id)
        
        await db.commit()
        
        # Broadcast strategy stop event
        await manager.broadcast(json.dumps({
            "type": "strategy_stopped",
            "strategy_id": strategy_id,
            "timestamp": datetime.now().isoformat()
        }))
        
        return {"message": "Strategy stopped successfully"}
    
    except Exception as e:
        logger.error(f"Error stopping strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies/{strategy_id}/executions", response_model=List[StrategyExecutionResponse])
async def get_strategy_executions(
    strategy_id: int,
    limit: int = Query(50, ge=1, le=200, description="Number of executions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Get strategy execution history"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # Verify strategy ownership
        strategy_query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Get executions
        query = select(StrategyExecution).where(
            StrategyExecution.strategy_id == strategy_id
        ).order_by(StrategyExecution.started_at.desc()).offset(offset).limit(limit)
        
        result = await db.execute(query)
        executions = result.scalars().all()
        
        return [
            StrategyExecutionResponse(
                id=execution.id,
                strategy_id=execution.strategy_id,
                status=execution.status.value,
                execution_params=execution.execution_params,
                started_at=execution.started_at,
                ended_at=execution.ended_at,
                profit_loss=execution.profit_loss,
                trades_count=execution.trades_count,
                error_message=execution.error_message,
                hummingbot_instance_id=execution.hummingbot_instance_id,
                performance_metrics=execution.performance_metrics
            )
            for execution in executions
        ]
    
    except Exception as e:
        logger.error(f"Error getting strategy executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies/{strategy_id}/performance", response_model=PerformanceMetrics)
async def get_strategy_performance(
    strategy_id: int,
    period: str = Query("7d", description="Performance period (1d, 7d, 30d, all)"),
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(security)
):
    """Get strategy performance metrics"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        query = select(Strategy).where(
            and_(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Calculate performance metrics for the specified period
        performance = await strategy.calculate_performance_metrics(period)
        
        return PerformanceMetrics(
            total_profit=performance.get("total_profit", 0.0),
            total_trades=performance.get("total_trades", 0),
            win_rate=performance.get("win_rate", 0.0),
            avg_profit_per_trade=performance.get("avg_profit_per_trade", 0.0),
            max_drawdown=performance.get("max_drawdown", 0.0),
            sharpe_ratio=performance.get("sharpe_ratio"),
            volatility=performance.get("volatility", 0.0),
            max_profit=performance.get("max_profit", 0.0),
            max_loss=performance.get("max_loss", 0.0),
            profit_factor=performance.get("profit_factor", 0.0),
            avg_trade_duration=performance.get("avg_trade_duration", 0.0)
        )
    
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/strategies/backtest", response_model=BacktestResult)
async def backtest_strategy(
    request: StrategyBacktestRequest,
    token: str = Depends(security)
):
    """Run strategy backtest"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # This would run a comprehensive backtest
        # For now, return mock results
        import time
        start_time = time.time()
        
        # Simulate backtest execution
        await asyncio.sleep(2)  # Simulate processing time
        
        execution_time = time.time() - start_time
        
        # Mock backtest results
        mock_performance = PerformanceMetrics(
            total_profit=1250.75,
            total_trades=45,
            win_rate=0.67,
            avg_profit_per_trade=27.79,
            max_drawdown=0.15,
            sharpe_ratio=1.85,
            volatility=0.12,
            max_profit=125.50,
            max_loss=-89.25,
            profit_factor=1.45,
            avg_trade_duration=45.5
        )
        
        mock_trades = [
            {
                "timestamp": (request.start_date + timedelta(hours=i)).isoformat(),
                "pair": "BTC/USDT",
                "side": "buy" if i % 2 == 0 else "sell",
                "amount": 0.1,
                "price": 45000 + (i * 100),
                "profit": (i * 10) - 50
            }
            for i in range(10)  # Sample trades
        ]
        
        mock_equity_curve = [
            {
                "timestamp": (request.start_date + timedelta(days=i)).timestamp(),
                "equity": request.initial_capital + (i * 50)
            }
            for i in range(30)  # 30 days of data
        ]
        
        mock_drawdown_curve = [
            {
                "timestamp": (request.start_date + timedelta(days=i)).timestamp(),
                "drawdown": max(0, (i - 15) * 0.01)  # Peak drawdown around day 15
            }
            for i in range(30)
        ]
        
        return BacktestResult(
            strategy_config=request.strategy_config,
            performance=mock_performance,
            trades=mock_trades,
            equity_curve=mock_equity_curve,
            drawdown_curve=mock_drawdown_curve,
            execution_time=execution_time
        )
    
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/strategies/ws")
async def strategy_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time strategy updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            
            # Handle different message types
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "subscribe_strategy":
                    strategy_id = message.get("strategy_id")
                    # Subscribe to specific strategy updates
                    await websocket.send_text(json.dumps({
                        "type": "subscription_confirmed",
                        "strategy_id": strategy_id
                    }))
                
                elif message_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@router.get("/strategy-templates")
async def get_strategy_templates():
    """Get available strategy templates"""
    templates = [
        {
            "id": "arbitrage_basic",
            "name": "Basic Arbitrage",
            "description": "Simple arbitrage between two exchanges",
            "strategy_type": "arbitrage",
            "config_template": {
                "exchanges": ["binance", "okx"],
                "trading_pairs": ["BTC/USDT"],
                "min_profit_threshold": 0.5,
                "max_position_size": 1000,
                "check_interval": 5
            }
        },
        {
            "id": "market_making_basic",
            "name": "Basic Market Making",
            "description": "Simple market making strategy",
            "strategy_type": "market_making",
            "config_template": {
                "exchange": "binance",
                "trading_pair": "BTC/USDT",
                "bid_spread": 0.1,
                "ask_spread": 0.1,
                "order_amount": 100,
                "inventory_skew_enabled": True
            }
        }
    ]
    
    return {"templates": templates}

@router.get("/strategies/{strategy_id}/logs")
async def get_strategy_logs(
    strategy_id: int,
    limit: int = Query(100, ge=1, le=1000, description="Number of log entries"),
    level: Optional[str] = Query(None, description="Log level filter"),
    token: str = Depends(security)
):
    """Get strategy execution logs"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # This would fetch logs from the logging system
        # For now, return mock logs
        mock_logs = [
            {
                "timestamp": (datetime.now() - timedelta(minutes=i)).isoformat(),
                "level": "INFO" if i % 3 != 0 else "WARNING",
                "message": f"Strategy execution log entry {i}",
                "component": "arbitrage_engine"
            }
            for i in range(min(limit, 50))
        ]
        
        if level:
            mock_logs = [log for log in mock_logs if log["level"] == level.upper()]
        
        return {"logs": mock_logs}
    
    except Exception as e:
        logger.error(f"Error getting strategy logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))