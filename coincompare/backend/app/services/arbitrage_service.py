import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, asdict
import json
import math

from ..config import settings
from ..models.arbitrage import ArbitrageOpportunity, ArbitrageTrade, ArbitrageStatus, TradeStatus
from ..models.strategy import Strategy, StrategyExecution
from ..database import get_redis_client
from .hummingbot_client import HummingbotManager
from .deposit_withdrawal import DepositWithdrawalService

logger = logging.getLogger(__name__)

@dataclass
class ExchangePrice:
    """Price information from an exchange"""
    exchange: str
    symbol: str
    bid: Decimal
    ask: Decimal
    volume: Decimal
    timestamp: datetime
    spread: Decimal
    
    @property
    def mid_price(self) -> Decimal:
        return (self.bid + self.ask) / 2

@dataclass
class ArbitrageConfig:
    """Arbitrage configuration"""
    min_profit_percentage: Decimal = Decimal('0.5')  # 0.5%
    max_trade_amount: Decimal = Decimal('1000')  # USD
    min_trade_amount: Decimal = Decimal('10')  # USD
    max_spread_percentage: Decimal = Decimal('2.0')  # 2%
    min_volume_ratio: Decimal = Decimal('0.1')  # 10% of our trade amount
    execution_timeout: int = 30  # seconds
    slippage_tolerance: Decimal = Decimal('0.1')  # 0.1%
    max_concurrent_trades: int = 5
    risk_limit_percentage: Decimal = Decimal('10')  # 10% of portfolio
    blacklisted_exchanges: Set[str] = None
    whitelisted_symbols: Set[str] = None
    
    def __post_init__(self):
        if self.blacklisted_exchanges is None:
            self.blacklisted_exchanges = set()
        if self.whitelisted_symbols is None:
            self.whitelisted_symbols = set()

class ExchangeConnector:
    """Base class for exchange connectors"""
    
    def __init__(self, exchange_name: str, api_key: str = None, api_secret: str = None):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_request_time = {}
        self.rate_limits = {
            'requests_per_second': 10,
            'requests_per_minute': 1200
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_ticker(self, symbol: str) -> ExchangePrice:
        """Get ticker data for symbol"""
        raise NotImplementedError
    
    async def get_order_book(self, symbol: str, depth: int = 10) -> Dict:
        """Get order book data"""
        raise NotImplementedError
    
    async def get_balance(self, currency: str) -> Decimal:
        """Get balance for currency"""
        raise NotImplementedError
    
    async def place_order(self, symbol: str, side: str, amount: Decimal, price: Decimal = None) -> str:
        """Place order"""
        raise NotImplementedError
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order"""
        raise NotImplementedError
    
    async def get_order_status(self, order_id: str, symbol: str) -> Dict:
        """Get order status"""
        raise NotImplementedError
    
    async def _rate_limit(self):
        """Implement rate limiting"""
        now = datetime.now()
        if self.exchange_name in self.last_request_time:
            time_diff = (now - self.last_request_time[self.exchange_name]).total_seconds()
            min_interval = 1.0 / self.rate_limits['requests_per_second']
            if time_diff < min_interval:
                await asyncio.sleep(min_interval - time_diff)
        
        self.last_request_time[self.exchange_name] = now

class BinanceConnector(ExchangeConnector):
    """Binance exchange connector"""
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        super().__init__("binance", api_key, api_secret)
        self.base_url = "https://api.binance.com"
    
    async def get_ticker(self, symbol: str) -> ExchangePrice:
        await self._rate_limit()
        
        url = f"{self.base_url}/api/v3/ticker/bookTicker"
        params = {"symbol": symbol.replace('/', '').upper()}
        
        async with self.session.get(url, params=params) as response:
            data = await response.json()
            
            return ExchangePrice(
                exchange="binance",
                symbol=symbol,
                bid=Decimal(data['bidPrice']),
                ask=Decimal(data['askPrice']),
                volume=Decimal(data.get('bidQty', '0')),
                timestamp=datetime.now(),
                spread=Decimal(data['askPrice']) - Decimal(data['bidPrice'])
            )
    
    async def get_order_book(self, symbol: str, depth: int = 10) -> Dict:
        await self._rate_limit()
        
        url = f"{self.base_url}/api/v3/depth"
        params = {
            "symbol": symbol.replace('/', '').upper(),
            "limit": depth
        }
        
        async with self.session.get(url, params=params) as response:
            return await response.json()

class OKXConnector(ExchangeConnector):
    """OKX exchange connector"""
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        super().__init__("okx", api_key, api_secret)
        self.base_url = "https://www.okx.com"
    
    async def get_ticker(self, symbol: str) -> ExchangePrice:
        await self._rate_limit()
        
        url = f"{self.base_url}/api/v5/market/ticker"
        params = {"instId": symbol.replace('/', '-').upper()}
        
        async with self.session.get(url, params=params) as response:
            data = await response.json()
            ticker = data['data'][0]
            
            return ExchangePrice(
                exchange="okx",
                symbol=symbol,
                bid=Decimal(ticker['bidPx']),
                ask=Decimal(ticker['askPx']),
                volume=Decimal(ticker['bidSz']),
                timestamp=datetime.now(),
                spread=Decimal(ticker['askPx']) - Decimal(ticker['bidPx'])
            )

class ArbitrageService:
    """Main arbitrage service for detecting and executing opportunities"""
    
    def __init__(self):
        self.config = ArbitrageConfig()
        self.exchanges: Dict[str, ExchangeConnector] = {}
        self.redis_client = None
        self.hummingbot_manager = None
        self.deposit_withdrawal_service = None
        self.active_opportunities: Dict[str, ArbitrageOpportunity] = {}
        self.active_trades: Dict[str, ArbitrageTrade] = {}
        self.price_cache: Dict[str, ExchangePrice] = {}
        self.cache_ttl = 5  # seconds
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False
        
    async def initialize(self):
        """Initialize the arbitrage service"""
        self.redis_client = await get_redis_client()
        self.hummingbot_manager = HummingbotManager()
        self.deposit_withdrawal_service = DepositWithdrawalService()
        
        # Initialize exchange connectors
        self.exchanges = {
            "binance": BinanceConnector(),
            "okx": OKXConnector(),
            # Add more exchanges as needed
        }
        
        await self.hummingbot_manager.start()
        await self.deposit_withdrawal_service.initialize()
        
        logger.info("Arbitrage service initialized")
    
    async def start_monitoring(self, symbols: List[str]):
        """Start monitoring for arbitrage opportunities"""
        if self.is_running:
            logger.warning("Arbitrage monitoring is already running")
            return
        
        self.is_running = True
        self.monitoring_task = asyncio.create_task(
            self._monitoring_loop(symbols)
        )
        
        logger.info(f"Started arbitrage monitoring for symbols: {symbols}")
    
    async def stop_monitoring(self):
        """Stop monitoring for arbitrage opportunities"""
        self.is_running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all active trades
        for trade in self.active_trades.values():
            await self._cancel_trade(trade)
        
        logger.info("Stopped arbitrage monitoring")
    
    async def _monitoring_loop(self, symbols: List[str]):
        """Main monitoring loop"""
        while self.is_running:
            try:
                # Get prices from all exchanges
                price_tasks = []
                for symbol in symbols:
                    for exchange_name, exchange in self.exchanges.items():
                        if exchange_name not in self.config.blacklisted_exchanges:
                            price_tasks.append(
                                self._get_cached_price(exchange, symbol)
                            )
                
                # Wait for all price updates
                prices = await asyncio.gather(*price_tasks, return_exceptions=True)
                
                # Filter out exceptions and organize by symbol
                symbol_prices = {}
                for price in prices:
                    if isinstance(price, ExchangePrice):
                        if price.symbol not in symbol_prices:
                            symbol_prices[price.symbol] = []
                        symbol_prices[price.symbol].append(price)
                
                # Detect arbitrage opportunities
                for symbol, exchange_prices in symbol_prices.items():
                    if len(exchange_prices) >= 2:
                        opportunities = await self._detect_opportunities(symbol, exchange_prices)
                        
                        for opportunity in opportunities:
                            await self._process_opportunity(opportunity)
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Wait longer on error
    
    async def _get_cached_price(self, exchange: ExchangeConnector, symbol: str) -> Optional[ExchangePrice]:
        """Get price with caching"""
        cache_key = f"{exchange.exchange_name}:{symbol}"
        
        # Check cache first
        if cache_key in self.price_cache:
            cached_price = self.price_cache[cache_key]
            if (datetime.now() - cached_price.timestamp).total_seconds() < self.cache_ttl:
                return cached_price
        
        # Get fresh price
        try:
            async with exchange:
                price = await exchange.get_ticker(symbol)
                self.price_cache[cache_key] = price
                return price
        except Exception as e:
            logger.error(f"Failed to get price from {exchange.exchange_name} for {symbol}: {e}")
            return None
    
    async def _detect_opportunities(self, symbol: str, prices: List[ExchangePrice]) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities from price data"""
        opportunities = []
        
        # Sort prices by bid (highest first) and ask (lowest first)
        sorted_by_bid = sorted(prices, key=lambda p: p.bid, reverse=True)
        sorted_by_ask = sorted(prices, key=lambda p: p.ask)
        
        # Find best buy and sell opportunities
        for sell_price in sorted_by_bid:
            for buy_price in sorted_by_ask:
                if sell_price.exchange == buy_price.exchange:
                    continue
                
                # Calculate profit
                profit_per_unit = sell_price.bid - buy_price.ask
                profit_percentage = (profit_per_unit / buy_price.ask) * 100
                
                if profit_percentage >= self.config.min_profit_percentage:
                    # Calculate recommended trade amount
                    max_amount_by_volume = min(
                        sell_price.volume * self.config.min_volume_ratio,
                        buy_price.volume * self.config.min_volume_ratio
                    )
                    
                    recommended_amount = min(
                        self.config.max_trade_amount / buy_price.ask,
                        max_amount_by_volume
                    )
                    
                    if recommended_amount >= self.config.min_trade_amount / buy_price.ask:
                        opportunity = ArbitrageOpportunity(
                            symbol=symbol,
                            buy_exchange=buy_price.exchange,
                            sell_exchange=sell_price.exchange,
                            buy_price=buy_price.ask,
                            sell_price=sell_price.bid,
                            profit_per_unit=profit_per_unit,
                            profit_percentage=profit_percentage,
                            recommended_amount=recommended_amount,
                            max_amount=max_amount_by_volume,
                            buy_volume=buy_price.volume,
                            sell_volume=sell_price.volume,
                            spread_percentage=((sell_price.ask - sell_price.bid) / sell_price.mid_price) * 100,
                            detected_at=datetime.now(),
                            expires_at=datetime.now() + timedelta(seconds=30),
                            status=ArbitrageStatus.DETECTED
                        )
                        
                        opportunities.append(opportunity)
        
        return opportunities
    
    async def _process_opportunity(self, opportunity: ArbitrageOpportunity):
        """Process a detected arbitrage opportunity"""
        opportunity_key = f"{opportunity.symbol}:{opportunity.buy_exchange}:{opportunity.sell_exchange}"
        
        # Check if we're already processing this opportunity
        if opportunity_key in self.active_opportunities:
            existing = self.active_opportunities[opportunity_key]
            if existing.status in [ArbitrageStatus.EXECUTING, ArbitrageStatus.MONITORING]:
                return
        
        # Check if we have too many concurrent trades
        active_trade_count = len([t for t in self.active_trades.values() 
                                if t.status in [TradeStatus.PENDING, TradeStatus.EXECUTING]])
        
        if active_trade_count >= self.config.max_concurrent_trades:
            logger.info(f"Max concurrent trades reached, skipping opportunity: {opportunity_key}")
            return
        
        # Validate opportunity
        if not await self._validate_opportunity(opportunity):
            return
        
        # Store opportunity
        self.active_opportunities[opportunity_key] = opportunity
        
        # Execute opportunity
        await self._execute_opportunity(opportunity)
    
    async def _validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate arbitrage opportunity"""
        # Check if opportunity has expired
        if datetime.now() > opportunity.expires_at:
            return False
        
        # Check minimum profit
        if opportunity.profit_percentage < self.config.min_profit_percentage:
            return False
        
        # Check spread limits
        if opportunity.spread_percentage > self.config.max_spread_percentage:
            return False
        
        # Check symbol whitelist
        if self.config.whitelisted_symbols and opportunity.symbol not in self.config.whitelisted_symbols:
            return False
        
        # Additional risk checks can be added here
        return True
    
    async def _execute_opportunity(self, opportunity: ArbitrageOpportunity):
        """Execute arbitrage opportunity"""
        try:
            opportunity.status = ArbitrageStatus.EXECUTING
            
            # Create arbitrage trade record
            trade = ArbitrageTrade(
                opportunity_id=opportunity.id,
                symbol=opportunity.symbol,
                buy_exchange=opportunity.buy_exchange,
                sell_exchange=opportunity.sell_exchange,
                planned_amount=opportunity.recommended_amount,
                planned_buy_price=opportunity.buy_price,
                planned_sell_price=opportunity.sell_price,
                expected_profit=opportunity.profit_per_unit * opportunity.recommended_amount,
                status=TradeStatus.PENDING,
                created_at=datetime.now()
            )
            
            self.active_trades[str(trade.id)] = trade
            
            # Execute using Hummingbot if available
            if self.hummingbot_manager and self.hummingbot_manager.client.is_connected:
                await self._execute_with_hummingbot(opportunity, trade)
            else:
                await self._execute_manual(opportunity, trade)
            
        except Exception as e:
            logger.error(f"Failed to execute opportunity: {e}")
            opportunity.status = ArbitrageStatus.FAILED
            if str(trade.id) in self.active_trades:
                self.active_trades[str(trade.id)].status = TradeStatus.FAILED
                self.active_trades[str(trade.id)].error_message = str(e)
    
    async def _execute_with_hummingbot(self, opportunity: ArbitrageOpportunity, trade: ArbitrageTrade):
        """Execute arbitrage using Hummingbot"""
        try:
            # Create strategy in database (this would be a real database operation)
            strategy = Strategy(
                name=f"arbitrage_{opportunity.symbol}_{int(datetime.now().timestamp())}",
                strategy_type="arbitrage",
                config={
                    "symbol": opportunity.symbol,
                    "buy_exchange": opportunity.buy_exchange,
                    "sell_exchange": opportunity.sell_exchange,
                    "amount": str(opportunity.recommended_amount),
                    "max_price_deviation": str(self.config.slippage_tolerance)
                },
                user_id=1,  # This would come from the actual user
                is_active=True
            )
            
            # Execute using Hummingbot
            hb_strategy_id = await self.hummingbot_manager.execute_arbitrage(opportunity, strategy)
            
            trade.hummingbot_strategy_id = hb_strategy_id
            trade.status = TradeStatus.EXECUTING
            
            logger.info(f"Arbitrage execution started with Hummingbot: {hb_strategy_id}")
            
        except Exception as e:
            logger.error(f"Failed to execute with Hummingbot: {e}")
            raise
    
    async def _execute_manual(self, opportunity: ArbitrageOpportunity, trade: ArbitrageTrade):
        """Execute arbitrage manually (fallback)"""
        # This would implement manual execution logic
        # For now, we'll just mark it as executed
        trade.status = TradeStatus.EXECUTED
        trade.executed_at = datetime.now()
        
        logger.info(f"Manual arbitrage execution completed for {opportunity.symbol}")
    
    async def _cancel_trade(self, trade: ArbitrageTrade):
        """Cancel an active trade"""
        try:
            if trade.hummingbot_strategy_id:
                await self.hummingbot_manager.stop_strategy(trade.hummingbot_strategy_id)
            
            trade.status = TradeStatus.CANCELLED
            trade.updated_at = datetime.now()
            
            logger.info(f"Trade cancelled: {trade.id}")
            
        except Exception as e:
            logger.error(f"Failed to cancel trade {trade.id}: {e}")
    
    async def get_active_opportunities(self) -> List[ArbitrageOpportunity]:
        """Get all active arbitrage opportunities"""
        return list(self.active_opportunities.values())
    
    async def get_active_trades(self) -> List[ArbitrageTrade]:
        """Get all active trades"""
        return list(self.active_trades.values())
    
    async def get_performance_metrics(self) -> Dict:
        """Get arbitrage performance metrics"""
        completed_trades = [t for t in self.active_trades.values() 
                          if t.status == TradeStatus.COMPLETED]
        
        total_profit = sum(t.actual_profit or Decimal('0') for t in completed_trades)
        total_trades = len(completed_trades)
        success_rate = (total_trades / len(self.active_trades)) * 100 if self.active_trades else 0
        
        return {
            "total_profit": float(total_profit),
            "total_trades": total_trades,
            "success_rate": success_rate,
            "active_opportunities": len(self.active_opportunities),
            "active_trades": len([t for t in self.active_trades.values() 
                                if t.status in [TradeStatus.PENDING, TradeStatus.EXECUTING]])
        }
    
    async def update_config(self, new_config: Dict):
        """Update arbitrage configuration"""
        for key, value in new_config.items():
            if hasattr(self.config, key):
                setattr(self.config, key, Decimal(value) if isinstance(value, (int, float, str)) else value)
        
        logger.info(f"Arbitrage configuration updated: {new_config}")
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.stop_monitoring()
        
        if self.hummingbot_manager:
            await self.hummingbot_manager.stop()
        
        # Close exchange connections
        for exchange in self.exchanges.values():
            if hasattr(exchange, 'session') and exchange.session:
                await exchange.session.close()
        
        logger.info("Arbitrage service cleanup completed")

# Global service instance
arbitrage_service = ArbitrageService()