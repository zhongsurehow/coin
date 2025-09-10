import asyncio
import aiohttp
import websockets
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from ..config import settings
from ..models.strategy import Strategy, StrategyExecution
from ..models.arbitrage import ArbitrageOpportunity

logger = logging.getLogger(__name__)

@dataclass
class HummingbotStrategy:
    """Hummingbot strategy configuration"""
    strategy_name: str
    trading_pair: str
    exchange: str
    bid_spread: float
    ask_spread: float
    order_amount: float
    order_refresh_time: float
    max_order_age: float
    order_refresh_tolerance_pct: float
    filled_order_delay: float
    inventory_skew_enabled: bool
    inventory_target_base_pct: float
    inventory_range_multiplier: float
    hanging_orders_enabled: bool
    hanging_orders_cancel_pct: float
    order_optimization_enabled: bool
    ask_order_optimization_depth: int
    bid_order_optimization_depth: int
    add_transaction_costs: bool
    price_ceiling: float
    price_floor: float
    ping_pong_enabled: bool
    order_levels: int
    order_level_amount: float
    order_level_spread: float

class HummingbotClient:
    """Client for interacting with Hummingbot API"""
    
    def __init__(self):
        self.base_url = f"http://{settings.hummingbot_host}:{settings.hummingbot_port}"
        self.api_key = settings.hummingbot_api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.strategies: Dict[str, Dict] = {}
        self.is_connected = False
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
    
    async def connect(self):
        """Connect to Hummingbot"""
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            # Test connection
            await self.get_status()
            self.is_connected = True
            logger.info("Connected to Hummingbot successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Hummingbot: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self):
        """Disconnect from Hummingbot"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        self.is_connected = False
        logger.info("Disconnected from Hummingbot")
    
    async def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make HTTP request to Hummingbot API"""
        if not self.session:
            raise RuntimeError("Not connected to Hummingbot")
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with self.session.request(method, url, json=data) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Hummingbot API request failed: {e}")
            raise
    
    async def get_status(self) -> Dict:
        """Get Hummingbot status"""
        return await self._make_request("GET", "/status")
    
    async def get_balance(self, exchange: str = None) -> Dict:
        """Get account balances"""
        endpoint = "/balance"
        if exchange:
            endpoint += f"?exchange={exchange}"
        return await self._make_request("GET", endpoint)
    
    async def create_strategy(self, strategy_config: Dict) -> str:
        """Create a new strategy"""
        response = await self._make_request("POST", "/strategies", strategy_config)
        strategy_id = response.get("strategy_id")
        
        if strategy_id:
            self.strategies[strategy_id] = strategy_config
            logger.info(f"Created strategy: {strategy_id}")
        
        return strategy_id
    
    async def start_strategy(self, strategy_id: str) -> Dict:
        """Start a strategy"""
        response = await self._make_request("POST", f"/strategies/{strategy_id}/start")
        logger.info(f"Started strategy: {strategy_id}")
        return response
    
    async def stop_strategy(self, strategy_id: str) -> Dict:
        """Stop a strategy"""
        response = await self._make_request("POST", f"/strategies/{strategy_id}/stop")
        logger.info(f"Stopped strategy: {strategy_id}")
        return response
    
    async def get_strategy_status(self, strategy_id: str) -> Dict:
        """Get strategy status"""
        return await self._make_request("GET", f"/strategies/{strategy_id}/status")
    
    async def get_strategy_performance(self, strategy_id: str) -> Dict:
        """Get strategy performance metrics"""
        return await self._make_request("GET", f"/strategies/{strategy_id}/performance")
    
    async def get_active_orders(self, strategy_id: str = None) -> List[Dict]:
        """Get active orders"""
        endpoint = "/orders"
        if strategy_id:
            endpoint += f"?strategy_id={strategy_id}"
        response = await self._make_request("GET", endpoint)
        return response.get("orders", [])
    
    async def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order"""
        return await self._make_request("DELETE", f"/orders/{order_id}")
    
    async def get_trade_history(self, strategy_id: str = None, limit: int = 100) -> List[Dict]:
        """Get trade history"""
        endpoint = f"/trades?limit={limit}"
        if strategy_id:
            endpoint += f"&strategy_id={strategy_id}"
        response = await self._make_request("GET", endpoint)
        return response.get("trades", [])
    
    async def create_arbitrage_strategy(self, opportunity: ArbitrageOpportunity) -> str:
        """Create arbitrage strategy from opportunity"""
        strategy_config = {
            "strategy_name": "arbitrage",
            "primary_market": opportunity.buy_exchange,
            "secondary_market": opportunity.sell_exchange,
            "trading_pair": opportunity.symbol,
            "min_profitability": opportunity.profit_percentage / 100,
            "order_amount": opportunity.recommended_amount,
            "max_order_age": 30,
            "cancel_order_threshold": 0.1,
            "active_order_cancellation": True,
            "debug_price_shim": False,
            "gateway_transaction_cancel_interval": 600
        }
        
        return await self.create_strategy(strategy_config)
    
    async def create_market_making_strategy(self, config: Dict) -> str:
        """Create market making strategy"""
        strategy_config = {
            "strategy_name": "pure_market_making",
            "exchange": config["exchange"],
            "trading_pair": config["trading_pair"],
            "bid_spread": config.get("bid_spread", 0.1),
            "ask_spread": config.get("ask_spread", 0.1),
            "order_amount": config["order_amount"],
            "order_refresh_time": config.get("order_refresh_time", 30),
            "max_order_age": config.get("max_order_age", 1800),
            "order_refresh_tolerance_pct": config.get("order_refresh_tolerance_pct", 0.2),
            "filled_order_delay": config.get("filled_order_delay", 60),
            "inventory_skew_enabled": config.get("inventory_skew_enabled", True),
            "inventory_target_base_pct": config.get("inventory_target_base_pct", 50),
            "inventory_range_multiplier": config.get("inventory_range_multiplier", 50),
            "hanging_orders_enabled": config.get("hanging_orders_enabled", False),
            "order_optimization_enabled": config.get("order_optimization_enabled", True),
            "add_transaction_costs": config.get("add_transaction_costs", True),
            "price_ceiling": config.get("price_ceiling", -1),
            "price_floor": config.get("price_floor", -1),
            "ping_pong_enabled": config.get("ping_pong_enabled", False)
        }
        
        return await self.create_strategy(strategy_config)
    
    async def monitor_strategy(self, strategy_id: str, callback=None) -> None:
        """Monitor strategy execution"""
        while True:
            try:
                status = await self.get_strategy_status(strategy_id)
                performance = await self.get_strategy_performance(strategy_id)
                
                if callback:
                    await callback(strategy_id, status, performance)
                
                # Check if strategy is still running
                if status.get("status") in ["stopped", "error"]:
                    break
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring strategy {strategy_id}: {e}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def get_market_data(self, exchange: str, trading_pair: str) -> Dict:
        """Get market data for a trading pair"""
        endpoint = f"/market_data?exchange={exchange}&trading_pair={trading_pair}"
        return await self._make_request("GET", endpoint)
    
    async def get_order_book(self, exchange: str, trading_pair: str, depth: int = 10) -> Dict:
        """Get order book data"""
        endpoint = f"/order_book?exchange={exchange}&trading_pair={trading_pair}&depth={depth}"
        return await self._make_request("GET", endpoint)
    
    async def validate_strategy_config(self, config: Dict) -> Dict:
        """Validate strategy configuration"""
        return await self._make_request("POST", "/strategies/validate", config)
    
    async def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchanges"""
        response = await self._make_request("GET", "/exchanges")
        return response.get("exchanges", [])
    
    async def get_trading_pairs(self, exchange: str) -> List[str]:
        """Get trading pairs for an exchange"""
        response = await self._make_request("GET", f"/exchanges/{exchange}/trading_pairs")
        return response.get("trading_pairs", [])
    
    async def emergency_stop_all(self) -> Dict:
        """Emergency stop all strategies"""
        response = await self._make_request("POST", "/emergency_stop")
        logger.warning("Emergency stop executed for all strategies")
        return response
    
    async def get_logs(self, strategy_id: str = None, level: str = "INFO", limit: int = 100) -> List[Dict]:
        """Get application logs"""
        endpoint = f"/logs?level={level}&limit={limit}"
        if strategy_id:
            endpoint += f"&strategy_id={strategy_id}"
        response = await self._make_request("GET", endpoint)
        return response.get("logs", [])

class HummingbotManager:
    """High-level manager for Hummingbot integration"""
    
    def __init__(self):
        self.client = HummingbotClient()
        self.active_strategies: Dict[str, str] = {}  # strategy_id -> hummingbot_strategy_id
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
    
    async def start(self):
        """Start the Hummingbot manager"""
        await self.client.connect()
        logger.info("Hummingbot manager started")
    
    async def stop(self):
        """Stop the Hummingbot manager"""
        # Cancel all monitoring tasks
        for task in self.monitoring_tasks.values():
            task.cancel()
        
        # Stop all active strategies
        for hb_strategy_id in self.active_strategies.values():
            try:
                await self.client.stop_strategy(hb_strategy_id)
            except Exception as e:
                logger.error(f"Error stopping strategy {hb_strategy_id}: {e}")
        
        await self.client.disconnect()
        logger.info("Hummingbot manager stopped")
    
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity, strategy: Strategy) -> str:
        """Execute arbitrage opportunity using Hummingbot"""
        try:
            # Create Hummingbot strategy
            hb_strategy_id = await self.client.create_arbitrage_strategy(opportunity)
            
            # Store mapping
            self.active_strategies[str(strategy.id)] = hb_strategy_id
            
            # Start strategy
            await self.client.start_strategy(hb_strategy_id)
            
            # Start monitoring
            monitor_task = asyncio.create_task(
                self.client.monitor_strategy(
                    hb_strategy_id,
                    self._strategy_callback
                )
            )
            self.monitoring_tasks[str(strategy.id)] = monitor_task
            
            logger.info(f"Started arbitrage execution for strategy {strategy.id}")
            return hb_strategy_id
            
        except Exception as e:
            logger.error(f"Failed to execute arbitrage: {e}")
            raise
    
    async def _strategy_callback(self, strategy_id: str, status: Dict, performance: Dict):
        """Callback for strategy monitoring"""
        logger.info(f"Strategy {strategy_id} status: {status.get('status')}")
        
        # Update strategy performance in database
        # This would be implemented with database operations
        pass
    
    async def stop_strategy(self, strategy_id: str) -> bool:
        """Stop a strategy"""
        hb_strategy_id = self.active_strategies.get(str(strategy_id))
        if not hb_strategy_id:
            return False
        
        try:
            await self.client.stop_strategy(hb_strategy_id)
            
            # Cancel monitoring task
            if str(strategy_id) in self.monitoring_tasks:
                self.monitoring_tasks[str(strategy_id)].cancel()
                del self.monitoring_tasks[str(strategy_id)]
            
            del self.active_strategies[str(strategy_id)]
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop strategy {strategy_id}: {e}")
            return False
    
    async def get_strategy_performance(self, strategy_id: str) -> Optional[Dict]:
        """Get strategy performance from Hummingbot"""
        hb_strategy_id = self.active_strategies.get(str(strategy_id))
        if not hb_strategy_id:
            return None
        
        try:
            return await self.client.get_strategy_performance(hb_strategy_id)
        except Exception as e:
            logger.error(f"Failed to get strategy performance: {e}")
            return None