"""交易所服务模块

提供与各大交易所的API集成功能，包括数据获取、订单管理、余额查询等。
"""

import asyncio
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
import aiohttp
import ccxt.async_support as ccxt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..database import get_async_session
from ..models import Exchange, TradingPair, ApiKey
from ..config import settings
from .logging_service import logger


class ExchangeService:
    """交易所服务类"""
    
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.last_requests: Dict[str, datetime] = {}
    
    async def initialize_exchanges(self):
        """初始化交易所连接"""
        try:
            async with get_async_session() as session:
                # 获取活跃的交易所
                result = await session.execute(
                    select(Exchange).where(Exchange.is_active == True)
                )
                exchanges = result.scalars().all()
                
                for exchange in exchanges:
                    await self._setup_exchange(exchange)
                    
                logger.info(f"初始化了 {len(self.exchanges)} 个交易所连接")
                
        except Exception as e:
            logger.error(f"初始化交易所失败: {e}")
    
    async def _setup_exchange(self, exchange: Exchange):
        """设置单个交易所"""
        try:
            # 获取API密钥
            async with get_async_session() as session:
                result = await session.execute(
                    select(ApiKey)
                    .where(ApiKey.exchange_id == exchange.id)
                    .where(ApiKey.is_active == True)
                )
                api_key = result.scalar_one_or_none()
            
            if not api_key:
                logger.warning(f"交易所 {exchange.name} 没有有效的API密钥")
                return
            
            # 创建CCXT交易所实例
            exchange_class = getattr(ccxt, exchange.name.lower())
            exchange_instance = exchange_class({
                'apiKey': api_key.api_key,
                'secret': api_key.secret_key,
                'password': api_key.passphrase,  # 某些交易所需要
                'sandbox': exchange.is_testnet,
                'enableRateLimit': True,
                'timeout': 30000,
            })
            
            # 测试连接
            await exchange_instance.load_markets()
            
            self.exchanges[exchange.name] = exchange_instance
            self.rate_limits[exchange.name] = {
                'requests_per_second': exchange.rate_limit or 10,
                'last_request': datetime.utcnow()
            }
            
            logger.info(f"交易所 {exchange.name} 连接成功")
            
        except Exception as e:
            logger.error(f"设置交易所 {exchange.name} 失败: {e}")
    
    async def _check_rate_limit(self, exchange_name: str):
        """检查API速率限制"""
        if exchange_name not in self.rate_limits:
            return
        
        rate_limit = self.rate_limits[exchange_name]
        now = datetime.utcnow()
        last_request = rate_limit['last_request']
        min_interval = 1.0 / rate_limit['requests_per_second']
        
        elapsed = (now - last_request).total_seconds()
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            await asyncio.sleep(sleep_time)
        
        self.rate_limits[exchange_name]['last_request'] = datetime.utcnow()
    
    async def get_ticker(self, exchange_name: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取交易对行情"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            ticker = await exchange.fetch_ticker(symbol)
            
            return {
                'symbol': symbol,
                'exchange': exchange_name,
                'bid': Decimal(str(ticker['bid'])) if ticker['bid'] else None,
                'ask': Decimal(str(ticker['ask'])) if ticker['ask'] else None,
                'last': Decimal(str(ticker['last'])) if ticker['last'] else None,
                'volume': Decimal(str(ticker['baseVolume'])) if ticker['baseVolume'] else None,
                'timestamp': datetime.fromtimestamp(ticker['timestamp'] / 1000) if ticker['timestamp'] else datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} {symbol} 行情失败: {e}")
            return None
    
    async def get_orderbook(self, exchange_name: str, symbol: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """获取订单簿"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            orderbook = await exchange.fetch_order_book(symbol, limit)
            
            return {
                'symbol': symbol,
                'exchange': exchange_name,
                'bids': [[Decimal(str(price)), Decimal(str(amount))] for price, amount in orderbook['bids']],
                'asks': [[Decimal(str(price)), Decimal(str(amount))] for price, amount in orderbook['asks']],
                'timestamp': datetime.fromtimestamp(orderbook['timestamp'] / 1000) if orderbook['timestamp'] else datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} {symbol} 订单簿失败: {e}")
            return None
    
    async def get_balance(self, exchange_name: str) -> Optional[Dict[str, Any]]:
        """获取账户余额"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            balance = await exchange.fetch_balance()
            
            # 格式化余额数据
            formatted_balance = {}
            for currency, amounts in balance.items():
                if currency not in ['info', 'free', 'used', 'total']:
                    formatted_balance[currency] = {
                        'free': Decimal(str(amounts['free'])) if amounts['free'] else Decimal('0'),
                        'used': Decimal(str(amounts['used'])) if amounts['used'] else Decimal('0'),
                        'total': Decimal(str(amounts['total'])) if amounts['total'] else Decimal('0')
                    }
            
            return {
                'exchange': exchange_name,
                'balances': formatted_balance,
                'timestamp': datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} 余额失败: {e}")
            return None
    
    async def create_order(self, exchange_name: str, symbol: str, order_type: str, 
                          side: str, amount: Decimal, price: Optional[Decimal] = None) -> Optional[Dict[str, Any]]:
        """创建订单"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            
            # 创建订单
            if order_type == 'market':
                order = await exchange.create_market_order(symbol, side, float(amount))
            elif order_type == 'limit':
                if price is None:
                    raise ValueError("限价单必须指定价格")
                order = await exchange.create_limit_order(symbol, side, float(amount), float(price))
            else:
                raise ValueError(f"不支持的订单类型: {order_type}")
            
            return {
                'id': order['id'],
                'symbol': symbol,
                'exchange': exchange_name,
                'type': order_type,
                'side': side,
                'amount': Decimal(str(order['amount'])),
                'price': Decimal(str(order['price'])) if order['price'] else None,
                'status': order['status'],
                'timestamp': datetime.fromtimestamp(order['timestamp'] / 1000) if order['timestamp'] else datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"在 {exchange_name} 创建订单失败: {e}")
            return None
    
    async def cancel_order(self, exchange_name: str, order_id: str, symbol: str) -> bool:
        """取消订单"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return False
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            await exchange.cancel_order(order_id, symbol)
            
            logger.info(f"订单 {order_id} 在 {exchange_name} 取消成功")
            return True
            
        except Exception as e:
            logger.error(f"在 {exchange_name} 取消订单 {order_id} 失败: {e}")
            return False
    
    async def get_order_status(self, exchange_name: str, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取订单状态"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            order = await exchange.fetch_order(order_id, symbol)
            
            return {
                'id': order['id'],
                'symbol': symbol,
                'exchange': exchange_name,
                'type': order['type'],
                'side': order['side'],
                'amount': Decimal(str(order['amount'])),
                'price': Decimal(str(order['price'])) if order['price'] else None,
                'filled': Decimal(str(order['filled'])),
                'remaining': Decimal(str(order['remaining'])),
                'status': order['status'],
                'timestamp': datetime.fromtimestamp(order['timestamp'] / 1000) if order['timestamp'] else datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} 订单 {order_id} 状态失败: {e}")
            return None
    
    async def get_trading_pairs(self, exchange_name: str) -> List[str]:
        """获取交易对列表"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return []
            
            exchange = self.exchanges[exchange_name]
            markets = await exchange.load_markets()
            
            return list(markets.keys())
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} 交易对列表失败: {e}")
            return []
    
    async def get_historical_trades(self, exchange_name: str, symbol: str, 
                                   since: Optional[datetime] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取历史交易数据"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return []
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            
            since_timestamp = None
            if since:
                since_timestamp = int(since.timestamp() * 1000)
            
            trades = await exchange.fetch_trades(symbol, since_timestamp, limit)
            
            return [
                {
                    'id': trade['id'],
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'side': trade['side'],
                    'amount': Decimal(str(trade['amount'])),
                    'price': Decimal(str(trade['price'])),
                    'timestamp': datetime.fromtimestamp(trade['timestamp'] / 1000)
                }
                for trade in trades
            ]
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} {symbol} 历史交易失败: {e}")
            return []
    
    async def check_exchange_status(self, exchange_name: str) -> Dict[str, Any]:
        """检查交易所状态"""
        try:
            if exchange_name not in self.exchanges:
                return {
                    'exchange': exchange_name,
                    'status': 'disconnected',
                    'message': '交易所未初始化'
                }
            
            exchange = self.exchanges[exchange_name]
            
            # 尝试获取服务器时间来测试连接
            await exchange.fetch_time()
            
            return {
                'exchange': exchange_name,
                'status': 'connected',
                'message': '连接正常',
                'timestamp': datetime.utcnow()
            }
            
        except Exception as e:
            return {
                'exchange': exchange_name,
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.utcnow()
            }
    
    async def get_deposit_address(self, exchange_name: str, currency: str) -> Optional[Dict[str, Any]]:
        """获取充值地址"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            address_info = await exchange.fetch_deposit_address(currency)
            
            return {
                'currency': currency,
                'exchange': exchange_name,
                'address': address_info['address'],
                'tag': address_info.get('tag'),
                'network': address_info.get('network'),
                'timestamp': datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"获取 {exchange_name} {currency} 充值地址失败: {e}")
            return None
    
    async def withdraw(self, exchange_name: str, currency: str, amount: Decimal, 
                     address: str, tag: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """提现"""
        try:
            if exchange_name not in self.exchanges:
                logger.error(f"交易所 {exchange_name} 未初始化")
                return None
            
            await self._check_rate_limit(exchange_name)
            
            exchange = self.exchanges[exchange_name]
            
            params = {}
            if tag:
                params['tag'] = tag
            
            withdrawal = await exchange.withdraw(currency, float(amount), address, params)
            
            return {
                'id': withdrawal['id'],
                'currency': currency,
                'exchange': exchange_name,
                'amount': Decimal(str(withdrawal['amount'])),
                'address': address,
                'tag': tag,
                'status': withdrawal['status'],
                'fee': Decimal(str(withdrawal['fee']['cost'])) if withdrawal.get('fee') else None,
                'timestamp': datetime.fromtimestamp(withdrawal['timestamp'] / 1000) if withdrawal['timestamp'] else datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"在 {exchange_name} 提现 {amount} {currency} 失败: {e}")
            return None
    
    async def close_all_connections(self):
        """关闭所有交易所连接"""
        for exchange_name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"交易所 {exchange_name} 连接已关闭")
            except Exception as e:
                logger.error(f"关闭交易所 {exchange_name} 连接失败: {e}")
        
        self.exchanges.clear()
        self.rate_limits.clear()


# 全局交易所服务实例
exchange_service = ExchangeService()