from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
import json
import asyncio
import logging

from ..services.arbitrage_service import arbitrage_service
from ..models.arbitrage import ArbitrageOpportunity, ArbitrageTrade
from ..database import get_db_session
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
security = HTTPBearer()

router = APIRouter()

# Pydantic models for API
class ArbitrageConfigUpdate(BaseModel):
    min_profit_percentage: Optional[float] = Field(None, ge=0, le=100)
    max_trade_amount: Optional[float] = Field(None, gt=0)
    min_trade_amount: Optional[float] = Field(None, gt=0)
    max_spread_percentage: Optional[float] = Field(None, ge=0, le=100)
    min_volume_ratio: Optional[float] = Field(None, ge=0, le=1)
    execution_timeout: Optional[int] = Field(None, ge=1, le=300)
    slippage_tolerance: Optional[float] = Field(None, ge=0, le=10)
    max_concurrent_trades: Optional[int] = Field(None, ge=1, le=20)
    risk_limit_percentage: Optional[float] = Field(None, ge=0, le=100)

class MonitoringRequest(BaseModel):
    symbols: List[str] = Field(..., min_items=1, max_items=50)
    exchanges: Optional[List[str]] = None

class ArbitrageOpportunityResponse(BaseModel):
    id: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    profit_per_unit: float
    profit_percentage: float
    recommended_amount: float
    max_amount: float
    buy_volume: float
    sell_volume: float
    spread_percentage: float
    detected_at: datetime
    expires_at: datetime
    status: str
    
    @classmethod
    def from_opportunity(cls, opportunity: ArbitrageOpportunity):
        return cls(
            id=str(opportunity.id),
            symbol=opportunity.symbol,
            buy_exchange=opportunity.buy_exchange,
            sell_exchange=opportunity.sell_exchange,
            buy_price=float(opportunity.buy_price),
            sell_price=float(opportunity.sell_price),
            profit_per_unit=float(opportunity.profit_per_unit),
            profit_percentage=float(opportunity.profit_percentage),
            recommended_amount=float(opportunity.recommended_amount),
            max_amount=float(opportunity.max_amount),
            buy_volume=float(opportunity.buy_volume),
            sell_volume=float(opportunity.sell_volume),
            spread_percentage=float(opportunity.spread_percentage),
            detected_at=opportunity.detected_at,
            expires_at=opportunity.expires_at,
            status=opportunity.status.value
        )

class ArbitrageTradeResponse(BaseModel):
    id: str
    opportunity_id: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    planned_amount: float
    actual_amount: Optional[float]
    planned_buy_price: float
    planned_sell_price: float
    actual_buy_price: Optional[float]
    actual_sell_price: Optional[float]
    expected_profit: float
    actual_profit: Optional[float]
    buy_order_id: Optional[str]
    sell_order_id: Optional[str]
    status: str
    created_at: datetime
    executed_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    
    @classmethod
    def from_trade(cls, trade: ArbitrageTrade):
        return cls(
            id=str(trade.id),
            opportunity_id=str(trade.opportunity_id),
            symbol=trade.symbol,
            buy_exchange=trade.buy_exchange,
            sell_exchange=trade.sell_exchange,
            planned_amount=float(trade.planned_amount),
            actual_amount=float(trade.actual_amount) if trade.actual_amount else None,
            planned_buy_price=float(trade.planned_buy_price),
            planned_sell_price=float(trade.planned_sell_price),
            actual_buy_price=float(trade.actual_buy_price) if trade.actual_buy_price else None,
            actual_sell_price=float(trade.actual_sell_price) if trade.actual_sell_price else None,
            expected_profit=float(trade.expected_profit),
            actual_profit=float(trade.actual_profit) if trade.actual_profit else None,
            buy_order_id=trade.buy_order_id,
            sell_order_id=trade.sell_order_id,
            status=trade.status.value,
            created_at=trade.created_at,
            executed_at=trade.executed_at,
            completed_at=trade.completed_at,
            error_message=trade.error_message
        )

class PerformanceMetrics(BaseModel):
    total_profit: float
    total_trades: int
    success_rate: float
    active_opportunities: int
    active_trades: int
    avg_profit_per_trade: float
    best_opportunity: Optional[ArbitrageOpportunityResponse]
    recent_trades: List[ArbitrageTradeResponse]

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except:
            self.disconnect(websocket)
    
    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                disconnected.append(connection)
        
        # Remove disconnected connections
        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

@router.get("/opportunities", response_model=List[ArbitrageOpportunityResponse])
async def get_arbitrage_opportunities(
    limit: int = Query(50, ge=1, le=200),
    symbol: Optional[str] = Query(None),
    min_profit: Optional[float] = Query(None, ge=0),
    token: str = Depends(security)
):
    """Get current arbitrage opportunities"""
    try:
        opportunities = await arbitrage_service.get_active_opportunities()
        
        # Filter by symbol if provided
        if symbol:
            opportunities = [opp for opp in opportunities if opp.symbol.upper() == symbol.upper()]
        
        # Filter by minimum profit if provided
        if min_profit is not None:
            opportunities = [opp for opp in opportunities if opp.profit_percentage >= min_profit]
        
        # Sort by profit percentage (highest first)
        opportunities.sort(key=lambda x: x.profit_percentage, reverse=True)
        
        # Limit results
        opportunities = opportunities[:limit]
        
        return [ArbitrageOpportunityResponse.from_opportunity(opp) for opp in opportunities]
    
    except Exception as e:
        logger.error(f"Error getting arbitrage opportunities: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/trades", response_model=List[ArbitrageTradeResponse])
async def get_arbitrage_trades(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    token: str = Depends(security)
):
    """Get arbitrage trades"""
    try:
        trades = await arbitrage_service.get_active_trades()
        
        # Filter by status if provided
        if status:
            trades = [trade for trade in trades if trade.status.value.lower() == status.lower()]
        
        # Filter by symbol if provided
        if symbol:
            trades = [trade for trade in trades if trade.symbol.upper() == symbol.upper()]
        
        # Sort by created_at (newest first)
        trades.sort(key=lambda x: x.created_at, reverse=True)
        
        # Limit results
        trades = trades[:limit]
        
        return [ArbitrageTradeResponse.from_trade(trade) for trade in trades]
    
    except Exception as e:
        logger.error(f"Error getting arbitrage trades: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(token: str = Depends(security)):
    """Get arbitrage performance metrics"""
    try:
        metrics = await arbitrage_service.get_performance_metrics()
        
        # Get additional metrics
        opportunities = await arbitrage_service.get_active_opportunities()
        trades = await arbitrage_service.get_active_trades()
        
        # Find best opportunity
        best_opportunity = None
        if opportunities:
            best_opp = max(opportunities, key=lambda x: x.profit_percentage)
            best_opportunity = ArbitrageOpportunityResponse.from_opportunity(best_opp)
        
        # Get recent trades
        recent_trades = sorted(trades, key=lambda x: x.created_at, reverse=True)[:10]
        recent_trade_responses = [ArbitrageTradeResponse.from_trade(trade) for trade in recent_trades]
        
        # Calculate average profit per trade
        completed_trades = [t for t in trades if t.actual_profit is not None]
        avg_profit = sum(float(t.actual_profit) for t in completed_trades) / len(completed_trades) if completed_trades else 0
        
        return PerformanceMetrics(
            total_profit=metrics["total_profit"],
            total_trades=metrics["total_trades"],
            success_rate=metrics["success_rate"],
            active_opportunities=metrics["active_opportunities"],
            active_trades=metrics["active_trades"],
            avg_profit_per_trade=avg_profit,
            best_opportunity=best_opportunity,
            recent_trades=recent_trade_responses
        )
    
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/start-monitoring")
async def start_monitoring(
    request: MonitoringRequest,
    token: str = Depends(security)
):
    """Start arbitrage monitoring for specified symbols"""
    try:
        await arbitrage_service.start_monitoring(request.symbols)
        return {"message": f"Started monitoring for {len(request.symbols)} symbols", "symbols": request.symbols}
    
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop-monitoring")
async def stop_monitoring(token: str = Depends(security)):
    """Stop arbitrage monitoring"""
    try:
        await arbitrage_service.stop_monitoring()
        return {"message": "Arbitrage monitoring stopped"}
    
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_arbitrage_config(token: str = Depends(security)):
    """Get current arbitrage configuration"""
    try:
        config = arbitrage_service.config
        return {
            "min_profit_percentage": float(config.min_profit_percentage),
            "max_trade_amount": float(config.max_trade_amount),
            "min_trade_amount": float(config.min_trade_amount),
            "max_spread_percentage": float(config.max_spread_percentage),
            "min_volume_ratio": float(config.min_volume_ratio),
            "execution_timeout": config.execution_timeout,
            "slippage_tolerance": float(config.slippage_tolerance),
            "max_concurrent_trades": config.max_concurrent_trades,
            "risk_limit_percentage": float(config.risk_limit_percentage),
            "blacklisted_exchanges": list(config.blacklisted_exchanges),
            "whitelisted_symbols": list(config.whitelisted_symbols)
        }
    
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/config")
async def update_arbitrage_config(
    config_update: ArbitrageConfigUpdate,
    token: str = Depends(security)
):
    """Update arbitrage configuration"""
    try:
        # Convert to dict and filter out None values
        update_dict = {k: v for k, v in config_update.dict().items() if v is not None}
        
        await arbitrage_service.update_config(update_dict)
        
        return {"message": "Configuration updated successfully", "updated_fields": list(update_dict.keys())}
    
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_arbitrage_status(token: str = Depends(security)):
    """Get arbitrage service status"""
    try:
        return {
            "is_running": arbitrage_service.is_running,
            "active_opportunities": len(arbitrage_service.active_opportunities),
            "active_trades": len(arbitrage_service.active_trades),
            "exchanges_connected": len(arbitrage_service.exchanges),
            "hummingbot_connected": arbitrage_service.hummingbot_manager.client.is_connected if arbitrage_service.hummingbot_manager else False
        }
    
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time arbitrage updates"""
    await manager.connect(websocket)
    
    try:
        # Send initial data
        opportunities = await arbitrage_service.get_active_opportunities()
        initial_data = {
            "type": "initial",
            "opportunities": [ArbitrageOpportunityResponse.from_opportunity(opp).dict() for opp in opportunities[:20]]
        }
        await manager.send_personal_message(json.dumps(initial_data), websocket)
        
        # Start sending periodic updates
        while True:
            try:
                # Wait for client message or timeout
                await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            except asyncio.TimeoutError:
                # Send periodic updates
                opportunities = await arbitrage_service.get_active_opportunities()
                trades = await arbitrage_service.get_active_trades()
                
                update_data = {
                    "type": "update",
                    "timestamp": datetime.now().isoformat(),
                    "opportunities": [ArbitrageOpportunityResponse.from_opportunity(opp).dict() for opp in opportunities[:20]],
                    "active_trades": len([t for t in trades if t.status.value in ["pending", "executing"]]),
                    "total_profit": sum(float(t.actual_profit or 0) for t in trades)
                }
                
                await manager.send_personal_message(json.dumps(update_data), websocket)
            
            except WebSocketDisconnect:
                break
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        manager.disconnect(websocket)

@router.post("/emergency-stop")
async def emergency_stop(token: str = Depends(security)):
    """Emergency stop all arbitrage activities"""
    try:
        await arbitrage_service.stop_monitoring()
        
        # Stop all active trades
        trades = await arbitrage_service.get_active_trades()
        active_trades = [t for t in trades if t.status.value in ["pending", "executing"]]
        
        for trade in active_trades:
            if trade.hummingbot_strategy_id and arbitrage_service.hummingbot_manager:
                await arbitrage_service.hummingbot_manager.stop_strategy(trade.hummingbot_strategy_id)
        
        return {
            "message": "Emergency stop executed",
            "stopped_trades": len(active_trades)
        }
    
    except Exception as e:
        logger.error(f"Error in emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))