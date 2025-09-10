from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging
from datetime import datetime, timedelta
import json
from decimal import Decimal
import aiohttp
import websockets
from collections import defaultdict, deque
import numpy as np
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class DataType(Enum):
    """数据类型"""
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    KLINE = "kline"
    BALANCE = "balance"
    ORDER = "order"

class ExchangeStatus(Enum):
    """交易所状态"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"

@dataclass
class MarketData:
    """市场数据基类"""
    exchange: str
    symbol: str
    timestamp: datetime
    data_type: DataType
    raw_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TickerData(MarketData):
    """行情数据"""
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal
    high_24h: Optional[Decimal] = None
    low_24h: Optional[Decimal] = None
    change_24h: Optional[Decimal] = None
    
    def __post_init__(self):
        self.data_type = DataType.TICKER

@dataclass
class OrderBookData(MarketData):
    """订单簿数据"""
    bids: List[List[Decimal]]  # [[price, size], ...]
    asks: List[List[Decimal]]  # [[price, size], ...]
    
    def __post_init__(self):
        self.data_type = DataType.ORDERBOOK
    
    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0][0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0][0] if self.asks else None
    
    @property
    def spread(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
    
    @property
    def spread_percentage(self) -> Optional[Decimal]:
        if self.best_bid and self.spread:
            return (self.spread / self.best_bid) * 100
        return None

@dataclass
class TradeData(MarketData):
    """交易数据"""
    price: Decimal
    size: Decimal
    side: str  # 'buy' or 'sell'
    trade_id: str
    
    def __post_init__(self):
        self.data_type = DataType.TRADES

@dataclass
class KlineData(MarketData):
    """K线数据"""
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    interval: str  # '1m', '5m', '1h', etc.
    
    def __post_init__(self):
        self.data_type = DataType.KLINE

class DataSubscription:
    """数据订阅"""
    
    def __init__(self, exchange: str, symbol: str, data_type: DataType, callback: Callable):
        self.exchange = exchange
        self.symbol = symbol
        self.data_type = data_type
        self.callback = callback
        self.active = True
        self.created_at = datetime.utcnow()
        self.last_update = None
        self.error_count = 0

class ExchangeConnector:
    """交易所连接器基类"""
    
    def __init__(self, exchange_name: str, config: Dict[str, Any]):
        self.exchange_name = exchange_name
        self.config = config
        self.status = ExchangeStatus.DISCONNECTED
        self.websocket = None
        self.session = None
        self.subscriptions: Dict[str, DataSubscription] = {}
        self.last_heartbeat = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        
    async def connect(self):
        """连接到交易所"""
        try:
            self.session = aiohttp.ClientSession()
            await self._connect_websocket()
            self.status = ExchangeStatus.CONNECTED
            self.reconnect_attempts = 0
            logger.info(f"Connected to {self.exchange_name}")
        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_name}: {e}")
            self.status = ExchangeStatus.ERROR
            raise
    
    async def disconnect(self):
        """断开连接"""
        self.status = ExchangeStatus.DISCONNECTED
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info(f"Disconnected from {self.exchange_name}")
    
    async def _connect_websocket(self):
        """连接WebSocket（子类实现）"""
        raise NotImplementedError
    
    async def subscribe(self, symbol: str, data_type: DataType, callback: Callable):
        """订阅数据（子类实现）"""
        raise NotImplementedError
    
    async def unsubscribe(self, symbol: str, data_type: DataType):
        """取消订阅（子类实现）"""
        raise NotImplementedError
    
    async def get_ticker(self, symbol: str) -> Optional[TickerData]:
        """获取行情数据（子类实现）"""
        raise NotImplementedError
    
    async def get_orderbook(self, symbol: str, limit: int = 20) -> Optional[OrderBookData]:
        """获取订单簿数据（子类实现）"""
        raise NotImplementedError
    
    async def _handle_message(self, message: str):
        """处理WebSocket消息（子类实现）"""
        raise NotImplementedError
    
    async def _reconnect(self):
        """重连逻辑"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Max reconnection attempts reached for {self.exchange_name}")
            self.status = ExchangeStatus.ERROR
            return
        
        self.status = ExchangeStatus.RECONNECTING
        self.reconnect_attempts += 1
        
        logger.info(f"Attempting to reconnect to {self.exchange_name} (attempt {self.reconnect_attempts})")
        
        try:
            await asyncio.sleep(min(2 ** self.reconnect_attempts, 30))  # 指数退避
            await self.connect()
            
            # 重新订阅
            for subscription in self.subscriptions.values():
                if subscription.active:
                    await self.subscribe(subscription.symbol, subscription.data_type, subscription.callback)
                    
        except Exception as e:
            logger.error(f"Reconnection failed for {self.exchange_name}: {e}")
            await self._reconnect()

class BinanceConnector(ExchangeConnector):
    """Binance连接器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("binance", config)
        self.base_url = "https://api.binance.com"
        self.ws_url = "wss://stream.binance.com:9443/ws"
        
    async def _connect_websocket(self):
        """连接Binance WebSocket"""
        self.websocket = await websockets.connect(self.ws_url)
        
        # 启动消息处理任务
        asyncio.create_task(self._message_handler())
    
    async def _message_handler(self):
        """WebSocket消息处理器"""
        try:
            async for message in self.websocket:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"WebSocket connection closed for {self.exchange_name}")
            await self._reconnect()
        except Exception as e:
            logger.error(f"WebSocket error for {self.exchange_name}: {e}")
            await self._reconnect()
    
    async def _handle_message(self, message: str):
        """处理Binance WebSocket消息"""
        try:
            data = json.loads(message)
            
            if 'stream' in data:
                stream = data['stream']
                payload = data['data']
                
                if '@ticker' in stream:
                    await self._handle_ticker_data(payload)
                elif '@depth' in stream:
                    await self._handle_orderbook_data(payload)
                elif '@trade' in stream:
                    await self._handle_trade_data(payload)
                    
        except Exception as e:
            logger.error(f"Error handling message from {self.exchange_name}: {e}")
    
    async def _handle_ticker_data(self, data: Dict[str, Any]):
        """处理行情数据"""
        symbol = data['s'].lower()
        
        ticker = TickerData(
            exchange=self.exchange_name,
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data_type=DataType.TICKER,
            bid=Decimal(data['b']),
            ask=Decimal(data['a']),
            last=Decimal(data['c']),
            volume=Decimal(data['v']),
            high_24h=Decimal(data['h']),
            low_24h=Decimal(data['l']),
            change_24h=Decimal(data['P']),
            raw_data=data
        )
        
        # 调用订阅回调
        subscription_key = f"{symbol}_{DataType.TICKER.value}"
        if subscription_key in self.subscriptions:
            subscription = self.subscriptions[subscription_key]
            if subscription.active:
                await subscription.callback(ticker)
                subscription.last_update = datetime.utcnow()
    
    async def _handle_orderbook_data(self, data: Dict[str, Any]):
        """处理订单簿数据"""
        symbol = data['s'].lower()
        
        bids = [[Decimal(price), Decimal(size)] for price, size in data['b']]
        asks = [[Decimal(price), Decimal(size)] for price, size in data['a']]
        
        orderbook = OrderBookData(
            exchange=self.exchange_name,
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data_type=DataType.ORDERBOOK,
            bids=bids,
            asks=asks,
            raw_data=data
        )
        
        # 调用订阅回调
        subscription_key = f"{symbol}_{DataType.ORDERBOOK.value}"
        if subscription_key in self.subscriptions:
            subscription = self.subscriptions[subscription_key]
            if subscription.active:
                await subscription.callback(orderbook)
                subscription.last_update = datetime.utcnow()
    
    async def _handle_trade_data(self, data: Dict[str, Any]):
        """处理交易数据"""
        symbol = data['s'].lower()
        
        trade = TradeData(
            exchange=self.exchange_name,
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data_type=DataType.TRADES,
            price=Decimal(data['p']),
            size=Decimal(data['q']),
            side='buy' if data['m'] else 'sell',
            trade_id=str(data['t']),
            raw_data=data
        )
        
        # 调用订阅回调
        subscription_key = f"{symbol}_{DataType.TRADES.value}"
        if subscription_key in self.subscriptions:
            subscription = self.subscriptions[subscription_key]
            if subscription.active:
                await subscription.callback(trade)
                subscription.last_update = datetime.utcnow()
    
    async def subscribe(self, symbol: str, data_type: DataType, callback: Callable):
        """订阅Binance数据"""
        stream_name = self._get_stream_name(symbol, data_type)
        
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": 1
        }
        
        await self.websocket.send(json.dumps(subscribe_msg))
        
        subscription_key = f"{symbol}_{data_type.value}"
        self.subscriptions[subscription_key] = DataSubscription(
            exchange=self.exchange_name,
            symbol=symbol,
            data_type=data_type,
            callback=callback
        )
        
        logger.info(f"Subscribed to {stream_name} on {self.exchange_name}")
    
    async def unsubscribe(self, symbol: str, data_type: DataType):
        """取消订阅Binance数据"""
        stream_name = self._get_stream_name(symbol, data_type)
        
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": [stream_name],
            "id": 1
        }
        
        await self.websocket.send(json.dumps(unsubscribe_msg))
        
        subscription_key = f"{symbol}_{data_type.value}"
        if subscription_key in self.subscriptions:
            self.subscriptions[subscription_key].active = False
            del self.subscriptions[subscription_key]
        
        logger.info(f"Unsubscribed from {stream_name} on {self.exchange_name}")
    
    def _get_stream_name(self, symbol: str, data_type: DataType) -> str:
        """获取Binance流名称"""
        symbol = symbol.upper()
        
        if data_type == DataType.TICKER:
            return f"{symbol.lower()}@ticker"
        elif data_type == DataType.ORDERBOOK:
            return f"{symbol.lower()}@depth20@100ms"
        elif data_type == DataType.TRADES:
            return f"{symbol.lower()}@trade"
        else:
            raise ValueError(f"Unsupported data type: {data_type}")
    
    async def get_ticker(self, symbol: str) -> Optional[TickerData]:
        """获取Binance行情数据"""
        try:
            url = f"{self.base_url}/api/v3/ticker/24hr"
            params = {'symbol': symbol.upper()}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return TickerData(
                        exchange=self.exchange_name,
                        symbol=symbol.lower(),
                        timestamp=datetime.utcnow(),
                        data_type=DataType.TICKER,
                        bid=Decimal(data['bidPrice']),
                        ask=Decimal(data['askPrice']),
                        last=Decimal(data['lastPrice']),
                        volume=Decimal(data['volume']),
                        high_24h=Decimal(data['highPrice']),
                        low_24h=Decimal(data['lowPrice']),
                        change_24h=Decimal(data['priceChangePercent']),
                        raw_data=data
                    )
        except Exception as e:
            logger.error(f"Error getting ticker from {self.exchange_name}: {e}")
        
        return None
    
    async def get_orderbook(self, symbol: str, limit: int = 20) -> Optional[OrderBookData]:
        """获取Binance订单簿数据"""
        try:
            url = f"{self.base_url}/api/v3/depth"
            params = {'symbol': symbol.upper(), 'limit': limit}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    bids = [[Decimal(price), Decimal(size)] for price, size in data['bids']]
                    asks = [[Decimal(price), Decimal(size)] for price, size in data['asks']]
                    
                    return OrderBookData(
                        exchange=self.exchange_name,
                        symbol=symbol.lower(),
                        timestamp=datetime.utcnow(),
                        data_type=DataType.ORDERBOOK,
                        bids=bids,
                        asks=asks,
                        raw_data=data
                    )
        except Exception as e:
            logger.error(f"Error getting orderbook from {self.exchange_name}: {e}")
        
        return None

class DataCache:
    """数据缓存"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 60):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_size))
        self.timestamps: Dict[str, datetime] = {}
    
    def add(self, key: str, data: MarketData):
        """添加数据到缓存"""
        self.cache[key].append(data)
        self.timestamps[key] = datetime.utcnow()
        
        # 清理过期数据
        self._cleanup_expired()
    
    def get_latest(self, key: str) -> Optional[MarketData]:
        """获取最新数据"""
        if key in self.cache and self.cache[key]:
            return self.cache[key][-1]
        return None
    
    def get_history(self, key: str, limit: int = 100) -> List[MarketData]:
        """获取历史数据"""
        if key in self.cache:
            return list(self.cache[key])[-limit:]
        return []
    
    def _cleanup_expired(self):
        """清理过期数据"""
        now = datetime.utcnow()
        expired_keys = []
        
        for key, timestamp in self.timestamps.items():
            if (now - timestamp).total_seconds() > self.ttl_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            del self.timestamps[key]

class DataAggregator:
    """数据聚合器"""
    
    def __init__(self):
        self.connectors: Dict[str, ExchangeConnector] = {}
        self.cache = DataCache()
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def add_exchange(self, exchange_name: str, config: Dict[str, Any]):
        """添加交易所连接器"""
        if exchange_name.lower() == 'binance':
            connector = BinanceConnector(config)
        else:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
        
        self.connectors[exchange_name] = connector
        await connector.connect()
        
        logger.info(f"Added exchange connector: {exchange_name}")
    
    async def remove_exchange(self, exchange_name: str):
        """移除交易所连接器"""
        if exchange_name in self.connectors:
            await self.connectors[exchange_name].disconnect()
            del self.connectors[exchange_name]
            logger.info(f"Removed exchange connector: {exchange_name}")
    
    async def subscribe_ticker(self, exchange: str, symbol: str, callback: Optional[Callable] = None):
        """订阅行情数据"""
        if exchange not in self.connectors:
            raise ValueError(f"Exchange {exchange} not connected")
        
        async def data_handler(data: TickerData):
            # 缓存数据
            cache_key = f"{exchange}_{symbol}_ticker"
            self.cache.add(cache_key, data)
            
            # 通知订阅者
            for subscriber in self.subscribers.get(cache_key, []):
                try:
                    await subscriber(data)
                except Exception as e:
                    logger.error(f"Error in subscriber callback: {e}")
            
            # 调用自定义回调
            if callback:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in custom callback: {e}")
        
        await self.connectors[exchange].subscribe(symbol, DataType.TICKER, data_handler)
        
        # 添加到订阅者列表
        cache_key = f"{exchange}_{symbol}_ticker"
        if callback:
            self.subscribers[cache_key].append(callback)
    
    async def subscribe_orderbook(self, exchange: str, symbol: str, callback: Optional[Callable] = None):
        """订阅订单簿数据"""
        if exchange not in self.connectors:
            raise ValueError(f"Exchange {exchange} not connected")
        
        async def data_handler(data: OrderBookData):
            # 缓存数据
            cache_key = f"{exchange}_{symbol}_orderbook"
            self.cache.add(cache_key, data)
            
            # 通知订阅者
            for subscriber in self.subscribers.get(cache_key, []):
                try:
                    await subscriber(data)
                except Exception as e:
                    logger.error(f"Error in subscriber callback: {e}")
            
            # 调用自定义回调
            if callback:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in custom callback: {e}")
        
        await self.connectors[exchange].subscribe(symbol, DataType.ORDERBOOK, data_handler)
        
        # 添加到订阅者列表
        cache_key = f"{exchange}_{symbol}_orderbook"
        if callback:
            self.subscribers[cache_key].append(callback)
    
    async def get_ticker(self, exchange: str, symbol: str) -> Optional[TickerData]:
        """获取行情数据"""
        # 先从缓存获取
        cache_key = f"{exchange}_{symbol}_ticker"
        cached_data = self.cache.get_latest(cache_key)
        
        if cached_data and isinstance(cached_data, TickerData):
            # 检查数据是否过期（5秒内的数据认为是新鲜的）
            if (datetime.utcnow() - cached_data.timestamp).total_seconds() < 5:
                return cached_data
        
        # 从交易所获取最新数据
        if exchange in self.connectors:
            return await self.connectors[exchange].get_ticker(symbol)
        
        return None
    
    async def get_orderbook(self, exchange: str, symbol: str, limit: int = 20) -> Optional[OrderBookData]:
        """获取订单簿数据"""
        # 先从缓存获取
        cache_key = f"{exchange}_{symbol}_orderbook"
        cached_data = self.cache.get_latest(cache_key)
        
        if cached_data and isinstance(cached_data, OrderBookData):
            # 检查数据是否过期（1秒内的数据认为是新鲜的）
            if (datetime.utcnow() - cached_data.timestamp).total_seconds() < 1:
                return cached_data
        
        # 从交易所获取最新数据
        if exchange in self.connectors:
            return await self.connectors[exchange].get_orderbook(symbol, limit)
        
        return None
    
    async def get_arbitrage_opportunities(self, symbol: str, min_profit_percentage: float = 0.1) -> List[Dict[str, Any]]:
        """获取套利机会"""
        opportunities = []
        
        # 获取所有交易所的行情数据
        tickers = {}
        for exchange in self.connectors:
            ticker = await self.get_ticker(exchange, symbol)
            if ticker:
                tickers[exchange] = ticker
        
        # 计算套利机会
        exchanges = list(tickers.keys())
        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                exchange_a = exchanges[i]
                exchange_b = exchanges[j]
                
                ticker_a = tickers[exchange_a]
                ticker_b = tickers[exchange_b]
                
                # 计算价差
                if ticker_a.ask < ticker_b.bid:
                    # 在A买入，在B卖出
                    profit = ticker_b.bid - ticker_a.ask
                    profit_percentage = (profit / ticker_a.ask) * 100
                    
                    if profit_percentage >= min_profit_percentage:
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': exchange_a,
                            'sell_exchange': exchange_b,
                            'buy_price': float(ticker_a.ask),
                            'sell_price': float(ticker_b.bid),
                            'profit': float(profit),
                            'profit_percentage': float(profit_percentage),
                            'timestamp': datetime.utcnow().isoformat()
                        })
                
                elif ticker_b.ask < ticker_a.bid:
                    # 在B买入，在A卖出
                    profit = ticker_a.bid - ticker_b.ask
                    profit_percentage = (profit / ticker_b.ask) * 100
                    
                    if profit_percentage >= min_profit_percentage:
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': exchange_b,
                            'sell_exchange': exchange_a,
                            'buy_price': float(ticker_b.ask),
                            'sell_price': float(ticker_a.bid),
                            'profit': float(profit),
                            'profit_percentage': float(profit_percentage),
                            'timestamp': datetime.utcnow().isoformat()
                        })
        
        return opportunities
    
    def get_exchange_status(self) -> Dict[str, str]:
        """获取所有交易所状态"""
        return {name: connector.status.value for name, connector in self.connectors.items()}
    
    async def start(self):
        """启动数据聚合器"""
        self.running = True
        logger.info("Data aggregator started")
    
    async def stop(self):
        """停止数据聚合器"""
        self.running = False
        
        # 断开所有连接
        for connector in self.connectors.values():
            await connector.disconnect()
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        logger.info("Data aggregator stopped")

# 全局数据聚合器实例
data_aggregator: Optional[DataAggregator] = None

def get_data_aggregator() -> DataAggregator:
    """获取数据聚合器实例"""
    global data_aggregator
    if data_aggregator is None:
        data_aggregator = DataAggregator()
    return data_aggregator