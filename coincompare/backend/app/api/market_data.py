from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import json
import asyncio
from enum import Enum

from ..services.arbitrage_service import arbitrage_service
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)
security = HTTPBearer()

router = APIRouter()

# Enums
class TimeInterval(str, Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"

class OrderBookDepth(int, Enum):
    DEPTH_5 = 5
    DEPTH_10 = 10
    DEPTH_20 = 20
    DEPTH_50 = 50
    DEPTH_100 = 100

# WebSocket connection manager
class MarketDataConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.subscriptions: Dict[WebSocket, List[str]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "general"):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
        self.subscriptions[websocket] = [channel]

    def disconnect(self, websocket: WebSocket):
        # Remove from all channels
        for channel, connections in self.active_connections.items():
            if websocket in connections:
                connections.remove(websocket)
        
        # Remove subscriptions
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]

    async def subscribe(self, websocket: WebSocket, channel: str):
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        
        if websocket not in self.active_connections[channel]:
            self.active_connections[channel].append(websocket)
        
        if websocket not in self.subscriptions:
            self.subscriptions[websocket] = []
        
        if channel not in self.subscriptions[websocket]:
            self.subscriptions[websocket].append(channel)

    async def unsubscribe(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections and websocket in self.active_connections[channel]:
            self.active_connections[channel].remove(websocket)
        
        if websocket in self.subscriptions and channel in self.subscriptions[websocket]:
            self.subscriptions[websocket].remove(channel)

    async def broadcast_to_channel(self, channel: str, message: str):
        if channel in self.active_connections:
            disconnected = []
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_text(message)
                except:
                    disconnected.append(connection)
            
            # Remove disconnected connections
            for conn in disconnected:
                self.disconnect(conn)

market_manager = MarketDataConnectionManager()

# Pydantic models
class PriceData(BaseModel):
    symbol: str
    exchange: str
    price: float
    volume_24h: float
    change_24h: float
    change_24h_percent: float
    high_24h: float
    low_24h: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None

class HistoricalPrice(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class OrderBookEntry(BaseModel):
    price: float
    quantity: float
    total: float

class OrderBook(BaseModel):
    symbol: str
    exchange: str
    timestamp: datetime
    bids: List[OrderBookEntry]
    asks: List[OrderBookEntry]
    spread: float
    mid_price: float

class Trade(BaseModel):
    id: str
    symbol: str
    exchange: str
    price: float
    quantity: float
    side: str  # "buy" or "sell"
    timestamp: datetime

class MarketSummary(BaseModel):
    symbol: str
    exchanges: List[str]
    avg_price: float
    price_range: Dict[str, float]  # {"min": price, "max": price}
    total_volume_24h: float
    arbitrage_opportunities: int
    best_bid: Dict[str, Any]  # {"exchange": str, "price": float}
    best_ask: Dict[str, Any]  # {"exchange": str, "price": float}
    spread_analysis: Dict[str, float]

class ExchangeStatus(BaseModel):
    exchange: str
    status: str  # "online", "offline", "maintenance"
    latency: Optional[float] = None
    last_update: datetime
    supported_pairs: List[str]
    api_limits: Dict[str, Any]

class MarketMetrics(BaseModel):
    total_exchanges: int
    total_pairs: int
    active_arbitrage_opportunities: int
    avg_spread: float
    market_volatility: float
    trading_volume_24h: float
    top_gainers: List[Dict[str, Any]]
    top_losers: List[Dict[str, Any]]

# Helper function to get user_id from token (optional for market data)
def get_user_id_from_token_optional(token: Optional[str] = None) -> Optional[int]:
    if not token:
        return None
    # This would decode the JWT token and extract user_id
    # For now, return a dummy user_id
    return 1

@router.get("/prices", response_model=List[PriceData])
async def get_current_prices(
    symbols: Optional[str] = Query(None, description="Comma-separated list of symbols"),
    exchanges: Optional[str] = Query(None, description="Comma-separated list of exchanges"),
    limit: int = Query(50, ge=1, le=200, description="Number of prices to return")
):
    """Get current prices for symbols across exchanges"""
    try:
        symbol_list = symbols.split(",") if symbols else None
        exchange_list = exchanges.split(",") if exchanges else None
        
        # Get prices from arbitrage service
        prices = await arbitrage_service.get_current_prices(
            symbols=symbol_list,
            exchanges=exchange_list,
            limit=limit
        )
        
        return [
            PriceData(
                symbol=price["symbol"],
                exchange=price["exchange"],
                price=price["price"],
                volume_24h=price.get("volume_24h", 0),
                change_24h=price.get("change_24h", 0),
                change_24h_percent=price.get("change_24h_percent", 0),
                high_24h=price.get("high_24h", price["price"]),
                low_24h=price.get("low_24h", price["price"]),
                timestamp=price.get("timestamp", datetime.now()),
                bid=price.get("bid"),
                ask=price.get("ask"),
                spread=price.get("spread")
            )
            for price in prices
        ]
    
    except Exception as e:
        logger.error(f"Error getting current prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prices/{symbol}", response_model=List[PriceData])
async def get_symbol_prices(
    symbol: str,
    exchanges: Optional[str] = Query(None, description="Comma-separated list of exchanges")
):
    """Get current prices for a specific symbol across exchanges"""
    try:
        exchange_list = exchanges.split(",") if exchanges else None
        
        prices = await arbitrage_service.get_symbol_prices(
            symbol=symbol,
            exchanges=exchange_list
        )
        
        return [
            PriceData(
                symbol=price["symbol"],
                exchange=price["exchange"],
                price=price["price"],
                volume_24h=price.get("volume_24h", 0),
                change_24h=price.get("change_24h", 0),
                change_24h_percent=price.get("change_24h_percent", 0),
                high_24h=price.get("high_24h", price["price"]),
                low_24h=price.get("low_24h", price["price"]),
                timestamp=price.get("timestamp", datetime.now()),
                bid=price.get("bid"),
                ask=price.get("ask"),
                spread=price.get("spread")
            )
            for price in prices
        ]
    
    except Exception as e:
        logger.error(f"Error getting symbol prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/historical/{symbol}", response_model=List[HistoricalPrice])
async def get_historical_prices(
    symbol: str,
    exchange: str = Query(..., description="Exchange name"),
    interval: TimeInterval = Query(TimeInterval.ONE_HOUR, description="Time interval"),
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time"),
    limit: int = Query(100, ge=1, le=1000, description="Number of data points")
):
    """Get historical price data"""
    try:
        # Default to last 24 hours if no time range specified
        if not start_time:
            start_time = datetime.now() - timedelta(days=1)
        if not end_time:
            end_time = datetime.now()
        
        # This would fetch from exchange APIs or database
        # For now, generate mock historical data
        historical_data = []
        current_time = start_time
        base_price = 45000.0  # Mock BTC price
        
        interval_minutes = {
            TimeInterval.ONE_MINUTE: 1,
            TimeInterval.FIVE_MINUTES: 5,
            TimeInterval.FIFTEEN_MINUTES: 15,
            TimeInterval.THIRTY_MINUTES: 30,
            TimeInterval.ONE_HOUR: 60,
            TimeInterval.FOUR_HOURS: 240,
            TimeInterval.ONE_DAY: 1440,
            TimeInterval.ONE_WEEK: 10080
        }[interval]
        
        count = 0
        while current_time <= end_time and count < limit:
            # Generate mock OHLCV data
            import random
            price_change = random.uniform(-0.02, 0.02)  # ±2% change
            open_price = base_price * (1 + price_change)
            high_price = open_price * (1 + random.uniform(0, 0.01))
            low_price = open_price * (1 - random.uniform(0, 0.01))
            close_price = open_price * (1 + random.uniform(-0.01, 0.01))
            volume = random.uniform(100, 1000)
            
            historical_data.append(HistoricalPrice(
                timestamp=current_time,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume
            ))
            
            base_price = close_price  # Use close as next base
            current_time += timedelta(minutes=interval_minutes)
            count += 1
        
        return historical_data
    
    except Exception as e:
        logger.error(f"Error getting historical prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orderbook/{symbol}", response_model=OrderBook)
async def get_order_book(
    symbol: str,
    exchange: str = Query(..., description="Exchange name"),
    depth: OrderBookDepth = Query(OrderBookDepth.DEPTH_20, description="Order book depth")
):
    """Get order book for a symbol"""
    try:
        # This would fetch from exchange API
        # For now, generate mock order book data
        import random
        
        base_price = 45000.0
        spread_percent = 0.001  # 0.1% spread
        
        # Generate bids (buy orders)
        bids = []
        for i in range(depth.value):
            price = base_price * (1 - spread_percent/2 - i * 0.0001)
            quantity = random.uniform(0.1, 2.0)
            bids.append(OrderBookEntry(
                price=price,
                quantity=quantity,
                total=price * quantity
            ))
        
        # Generate asks (sell orders)
        asks = []
        for i in range(depth.value):
            price = base_price * (1 + spread_percent/2 + i * 0.0001)
            quantity = random.uniform(0.1, 2.0)
            asks.append(OrderBookEntry(
                price=price,
                quantity=quantity,
                total=price * quantity
            ))
        
        best_bid = bids[0].price if bids else 0
        best_ask = asks[0].price if asks else 0
        spread = best_ask - best_bid
        mid_price = (best_bid + best_ask) / 2
        
        return OrderBook(
            symbol=symbol,
            exchange=exchange,
            timestamp=datetime.now(),
            bids=bids,
            asks=asks,
            spread=spread,
            mid_price=mid_price
        )
    
    except Exception as e:
        logger.error(f"Error getting order book: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades/{symbol}", response_model=List[Trade])
async def get_recent_trades(
    symbol: str,
    exchange: str = Query(..., description="Exchange name"),
    limit: int = Query(50, ge=1, le=500, description="Number of trades to return")
):
    """Get recent trades for a symbol"""
    try:
        # This would fetch from exchange API
        # For now, generate mock trade data
        import random
        
        trades = []
        base_price = 45000.0
        current_time = datetime.now()
        
        for i in range(limit):
            price_change = random.uniform(-0.001, 0.001)  # ±0.1% change
            price = base_price * (1 + price_change)
            quantity = random.uniform(0.01, 1.0)
            side = random.choice(["buy", "sell"])
            
            trades.append(Trade(
                id=f"trade_{i}_{int(current_time.timestamp())}",
                symbol=symbol,
                exchange=exchange,
                price=price,
                quantity=quantity,
                side=side,
                timestamp=current_time - timedelta(seconds=i*10)
            ))
        
        return trades
    
    except Exception as e:
        logger.error(f"Error getting recent trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary/{symbol}", response_model=MarketSummary)
async def get_market_summary(
    symbol: str
):
    """Get market summary for a symbol across all exchanges"""
    try:
        # Get prices from all exchanges
        prices = await arbitrage_service.get_symbol_prices(symbol=symbol)
        
        if not prices:
            raise HTTPException(status_code=404, detail="Symbol not found")
        
        # Calculate summary statistics
        price_values = [p["price"] for p in prices]
        exchanges = [p["exchange"] for p in prices]
        
        avg_price = sum(price_values) / len(price_values)
        min_price = min(price_values)
        max_price = max(price_values)
        
        # Find best bid/ask
        best_bid = {"exchange": "", "price": 0}
        best_ask = {"exchange": "", "price": float('inf')}
        
        for price_data in prices:
            if price_data.get("bid", 0) > best_bid["price"]:
                best_bid = {"exchange": price_data["exchange"], "price": price_data.get("bid", 0)}
            if price_data.get("ask", float('inf')) < best_ask["price"]:
                best_ask = {"exchange": price_data["exchange"], "price": price_data.get("ask", 0)}
        
        # Get arbitrage opportunities
        opportunities = await arbitrage_service.detect_opportunities([symbol])
        
        return MarketSummary(
            symbol=symbol,
            exchanges=exchanges,
            avg_price=avg_price,
            price_range={"min": min_price, "max": max_price},
            total_volume_24h=sum(p.get("volume_24h", 0) for p in prices),
            arbitrage_opportunities=len(opportunities),
            best_bid=best_bid,
            best_ask=best_ask,
            spread_analysis={
                "avg_spread": (max_price - min_price) / avg_price * 100,
                "max_spread": (max_price - min_price),
                "spread_percentage": (max_price - min_price) / min_price * 100
            }
        )
    
    except Exception as e:
        logger.error(f"Error getting market summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/exchanges", response_model=List[ExchangeStatus])
async def get_exchange_status():
    """Get status of all supported exchanges"""
    try:
        # This would check actual exchange status
        # For now, return mock data
        exchanges = [
            ExchangeStatus(
                exchange="binance",
                status="online",
                latency=45.2,
                last_update=datetime.now(),
                supported_pairs=["BTC/USDT", "ETH/USDT", "BNB/USDT"],
                api_limits={"requests_per_minute": 1200, "weight_per_minute": 6000}
            ),
            ExchangeStatus(
                exchange="okx",
                status="online",
                latency=52.8,
                last_update=datetime.now(),
                supported_pairs=["BTC/USDT", "ETH/USDT", "OKB/USDT"],
                api_limits={"requests_per_minute": 600, "weight_per_minute": 3000}
            ),
            ExchangeStatus(
                exchange="huobi",
                status="maintenance",
                latency=None,
                last_update=datetime.now() - timedelta(minutes=30),
                supported_pairs=["BTC/USDT", "ETH/USDT", "HT/USDT"],
                api_limits={"requests_per_minute": 800, "weight_per_minute": 4000}
            )
        ]
        
        return exchanges
    
    except Exception as e:
        logger.error(f"Error getting exchange status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics", response_model=MarketMetrics)
async def get_market_metrics():
    """Get overall market metrics"""
    try:
        # This would calculate from real data
        # For now, return mock metrics
        return MarketMetrics(
            total_exchanges=5,
            total_pairs=150,
            active_arbitrage_opportunities=12,
            avg_spread=0.15,
            market_volatility=0.08,
            trading_volume_24h=2500000000.0,
            top_gainers=[
                {"symbol": "BTC/USDT", "change": 5.2},
                {"symbol": "ETH/USDT", "change": 3.8},
                {"symbol": "BNB/USDT", "change": 2.1}
            ],
            top_losers=[
                {"symbol": "ADA/USDT", "change": -2.5},
                {"symbol": "DOT/USDT", "change": -1.8},
                {"symbol": "LINK/USDT", "change": -1.2}
            ]
        )
    
    except Exception as e:
        logger.error(f"Error getting market metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/symbols")
async def get_supported_symbols(
    exchange: Optional[str] = Query(None, description="Filter by exchange")
):
    """Get list of supported trading symbols"""
    try:
        # This would fetch from exchange APIs
        # For now, return mock data
        symbols = {
            "binance": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "DOT/USDT"],
            "okx": ["BTC/USDT", "ETH/USDT", "OKB/USDT", "ADA/USDT", "LINK/USDT"],
            "huobi": ["BTC/USDT", "ETH/USDT", "HT/USDT", "ADA/USDT", "DOT/USDT"]
        }
        
        if exchange:
            return {"exchange": exchange, "symbols": symbols.get(exchange, [])}
        else:
            # Return all unique symbols
            all_symbols = set()
            for exchange_symbols in symbols.values():
                all_symbols.update(exchange_symbols)
            return {"symbols": sorted(list(all_symbols))}
    
    except Exception as e:
        logger.error(f"Error getting supported symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws")
async def market_data_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time market data"""
    await market_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "subscribe":
                    channel = message.get("channel")
                    if channel:
                        await market_manager.subscribe(websocket, channel)
                        await websocket.send_text(json.dumps({
                            "type": "subscription_confirmed",
                            "channel": channel
                        }))
                
                elif message_type == "unsubscribe":
                    channel = message.get("channel")
                    if channel:
                        await market_manager.unsubscribe(websocket, channel)
                        await websocket.send_text(json.dumps({
                            "type": "unsubscription_confirmed",
                            "channel": channel
                        }))
                
                elif message_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
                
    except WebSocketDisconnect:
        market_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        market_manager.disconnect(websocket)

# Background task to broadcast market data updates
async def broadcast_market_updates():
    """Background task to broadcast real-time market data"""
    while True:
        try:
            # Get latest prices
            prices = await arbitrage_service.get_current_prices(limit=10)
            
            # Broadcast to price channel
            price_update = {
                "type": "price_update",
                "data": prices,
                "timestamp": datetime.now().isoformat()
            }
            
            await market_manager.broadcast_to_channel(
                "prices", 
                json.dumps(price_update)
            )
            
            # Get arbitrage opportunities
            opportunities = await arbitrage_service.detect_opportunities()
            
            # Broadcast to arbitrage channel
            arbitrage_update = {
                "type": "arbitrage_update",
                "data": opportunities[:5],  # Top 5 opportunities
                "timestamp": datetime.now().isoformat()
            }
            
            await market_manager.broadcast_to_channel(
                "arbitrage",
                json.dumps(arbitrage_update)
            )
            
            # Wait before next update
            await asyncio.sleep(5)  # Update every 5 seconds
            
        except Exception as e:
            logger.error(f"Error in market data broadcast: {e}")
            await asyncio.sleep(10)  # Wait longer on error

# Start background task when module is imported
# This would normally be started in the main application
# asyncio.create_task(broadcast_market_updates())