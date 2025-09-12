from celery import current_app
from typing import List, Dict, Any
import asyncio
import logging
from datetime import datetime, timedelta

from ..celery_app import task_with_retry, urgent_task
from ..services.data_aggregator import data_aggregator
from ..database import get_async_session
from ..models import TradingPair, ArbitrageOpportunity
from ..config import settings

logger = logging.getLogger(__name__)

@task_with_retry(name="app.tasks.data_collection.collect_market_data")
def collect_market_data(self):
    """收集市场数据任务"""
    try:
        # 运行异步数据收集
        result = asyncio.run(_collect_market_data_async())
        
        logger.info(f"Market data collection completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Market data collection failed: {str(e)}")
        raise self.retry(countdown=60, max_retries=3)

async def _collect_market_data_async():
    """异步收集市场数据"""
    try:
        # 获取所有活跃的交易对
        async with get_async_session() as session:
            # 这里应该从数据库获取交易对，简化处理
            trading_pairs = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        
        collected_data = []
        
        # 为每个交易对收集数据
        for pair in trading_pairs:
            try:
                # 获取ticker数据
                ticker_data = await data_aggregator.get_ticker_data(pair)
                if ticker_data:
                    collected_data.append({
                        "pair": pair,
                        "type": "ticker",
                        "data": ticker_data,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # 获取订单簿数据
                orderbook_data = await data_aggregator.get_orderbook_data(pair)
                if orderbook_data:
                    collected_data.append({
                        "pair": pair,
                        "type": "orderbook",
                        "data": orderbook_data,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            except Exception as e:
                logger.error(f"Failed to collect data for {pair}: {str(e)}")
                continue
        
        return {
            "collected_pairs": len(trading_pairs),
            "successful_collections": len(collected_data),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async market data collection failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.data_collection.collect_orderbook_data")
def collect_orderbook_data(self, symbols: List[str] = None):
    """收集订单簿数据任务"""
    try:
        if not symbols:
            symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        
        result = asyncio.run(_collect_orderbook_data_async(symbols))
        
        logger.info(f"Orderbook data collection completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Orderbook data collection failed: {str(e)}")
        raise self.retry(countdown=30, max_retries=5)

async def _collect_orderbook_data_async(symbols: List[str]):
    """异步收集订单簿数据"""
    try:
        collected_data = []
        
        for symbol in symbols:
            try:
                # 从所有交易所获取订单簿数据
                orderbook_data = await data_aggregator.get_orderbook_data(symbol)
                
                if orderbook_data:
                    collected_data.append({
                        "symbol": symbol,
                        "exchanges": list(orderbook_data.keys()),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            except Exception as e:
                logger.error(f"Failed to collect orderbook for {symbol}: {str(e)}")
                continue
        
        return {
            "requested_symbols": len(symbols),
            "successful_collections": len(collected_data),
            "data": collected_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async orderbook collection failed: {str(e)}")
        raise

@urgent_task(name="app.tasks.data_collection.collect_real_time_prices")
def collect_real_time_prices(self, symbols: List[str]):
    """实时价格收集任务（高优先级）"""
    try:
        result = asyncio.run(_collect_real_time_prices_async(symbols))
        
        return result
        
    except Exception as e:
        logger.error(f"Real-time price collection failed: {str(e)}")
        raise self.retry(countdown=5, max_retries=10)

async def _collect_real_time_prices_async(symbols: List[str]):
    """异步收集实时价格"""
    try:
        price_data = {}
        
        for symbol in symbols:
            try:
                ticker_data = await data_aggregator.get_ticker_data(symbol)
                if ticker_data:
                    price_data[symbol] = {
                        "exchanges": {},
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    for exchange, data in ticker_data.items():
                        if data and 'last' in data:
                            price_data[symbol]["exchanges"][exchange] = {
                                "price": data['last'],
                                "volume": data.get('volume', 0),
                                "timestamp": data.get('timestamp', datetime.utcnow().isoformat())
                            }
                            
            except Exception as e:
                logger.error(f"Failed to collect real-time price for {symbol}: {str(e)}")
                continue
        
        return price_data
        
    except Exception as e:
        logger.error(f"Async real-time price collection failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.data_collection.update_trading_pairs")
def update_trading_pairs(self):
    """更新交易对信息任务"""
    try:
        result = asyncio.run(_update_trading_pairs_async())
        
        logger.info(f"Trading pairs update completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Trading pairs update failed: {str(e)}")
        raise self.retry(countdown=300, max_retries=2)

async def _update_trading_pairs_async():
    """异步更新交易对信息"""
    try:
        updated_pairs = []
        
        # 获取所有交易所的交易对信息
        for exchange_name in data_aggregator.exchanges.keys():
            try:
                exchange = data_aggregator.exchanges[exchange_name]
                if hasattr(exchange, 'load_markets'):
                    markets = await exchange.load_markets()
                    
                    for symbol, market in markets.items():
                        if market.get('active', False):
                            updated_pairs.append({
                                "exchange": exchange_name,
                                "symbol": symbol,
                                "base": market.get('base'),
                                "quote": market.get('quote'),
                                "active": market.get('active', False),
                                "min_amount": market.get('limits', {}).get('amount', {}).get('min'),
                                "max_amount": market.get('limits', {}).get('amount', {}).get('max'),
                                "min_cost": market.get('limits', {}).get('cost', {}).get('min'),
                                "precision_amount": market.get('precision', {}).get('amount'),
                                "precision_price": market.get('precision', {}).get('price'),
                            })
                            
            except Exception as e:
                logger.error(f"Failed to update pairs for {exchange_name}: {str(e)}")
                continue
        
        return {
            "total_pairs_found": len(updated_pairs),
            "exchanges_processed": len(data_aggregator.exchanges),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async trading pairs update failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.data_collection.collect_historical_data")
def collect_historical_data(self, symbol: str, timeframe: str = "1h", limit: int = 100):
    """收集历史数据任务"""
    try:
        result = asyncio.run(_collect_historical_data_async(symbol, timeframe, limit))
        
        logger.info(f"Historical data collection completed for {symbol}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Historical data collection failed for {symbol}: {str(e)}")
        raise self.retry(countdown=120, max_retries=2)

async def _collect_historical_data_async(symbol: str, timeframe: str, limit: int):
    """异步收集历史数据"""
    try:
        historical_data = {}
        
        for exchange_name, exchange in data_aggregator.exchanges.items():
            try:
                if hasattr(exchange, 'fetch_ohlcv'):
                    ohlcv_data = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                    
                    if ohlcv_data:
                        historical_data[exchange_name] = {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "data_points": len(ohlcv_data),
                            "start_time": datetime.fromtimestamp(ohlcv_data[0][0] / 1000).isoformat() if ohlcv_data else None,
                            "end_time": datetime.fromtimestamp(ohlcv_data[-1][0] / 1000).isoformat() if ohlcv_data else None,
                            "data": ohlcv_data
                        }
                        
            except Exception as e:
                logger.error(f"Failed to collect historical data from {exchange_name}: {str(e)}")
                continue
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "exchanges_collected": len(historical_data),
            "total_data_points": sum(data["data_points"] for data in historical_data.values()),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async historical data collection failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.data_collection.validate_data_quality")
def validate_data_quality(self):
    """数据质量验证任务"""
    try:
        result = asyncio.run(_validate_data_quality_async())
        
        logger.info(f"Data quality validation completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Data quality validation failed: {str(e)}")
        raise self.retry(countdown=180, max_retries=2)

async def _validate_data_quality_async():
    """异步数据质量验证"""
    try:
        validation_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "exchanges": {},
            "overall_health": "unknown"
        }
        
        total_exchanges = 0
        healthy_exchanges = 0
        
        for exchange_name in data_aggregator.exchanges.keys():
            total_exchanges += 1
            exchange_health = {
                "status": "unknown",
                "last_update": None,
                "data_freshness": None,
                "error_rate": 0
            }
            
            try:
                # 检查交易所连接状态
                ticker_data = await data_aggregator.get_ticker_data("BTC/USDT")
                
                if ticker_data and exchange_name in ticker_data:
                    exchange_health["status"] = "healthy"
                    exchange_health["last_update"] = datetime.utcnow().isoformat()
                    healthy_exchanges += 1
                else:
                    exchange_health["status"] = "no_data"
                    
            except Exception as e:
                exchange_health["status"] = "error"
                exchange_health["error"] = str(e)
            
            validation_results["exchanges"][exchange_name] = exchange_health
        
        # 计算整体健康状态
        if healthy_exchanges == total_exchanges:
            validation_results["overall_health"] = "excellent"
        elif healthy_exchanges >= total_exchanges * 0.8:
            validation_results["overall_health"] = "good"
        elif healthy_exchanges >= total_exchanges * 0.5:
            validation_results["overall_health"] = "fair"
        else:
            validation_results["overall_health"] = "poor"
        
        validation_results["healthy_exchanges"] = healthy_exchanges
        validation_results["total_exchanges"] = total_exchanges
        validation_results["health_percentage"] = (healthy_exchanges / total_exchanges * 100) if total_exchanges > 0 else 0
        
        return validation_results
        
    except Exception as e:
        logger.error(f"Async data quality validation failed: {str(e)}")
        raise

# 导出任务函数
__all__ = [
    "collect_market_data",
    "collect_orderbook_data", 
    "collect_real_time_prices",
    "update_trading_pairs",
    "collect_historical_data",
    "validate_data_quality"
]