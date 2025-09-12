from celery import current_app
from typing import List, Dict, Any, Optional
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from ..celery_app import task_with_retry, urgent_task
from ..services.data_aggregator import data_aggregator
from ..database import get_async_session
from ..models import ArbitrageOpportunity, TradingPair
from ..config import settings
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

@urgent_task(name="app.tasks.arbitrage_detection.detect_opportunities")
def detect_opportunities(self, symbols: List[str] = None):
    """检测套利机会任务（高优先级）"""
    try:
        if not symbols:
            symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "DOT/USDT"]
        
        result = asyncio.run(_detect_opportunities_async(symbols))
        
        logger.info(f"Arbitrage detection completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Arbitrage detection failed: {str(e)}")
        raise self.retry(countdown=10, max_retries=5)

async def _detect_opportunities_async(symbols: List[str]):
    """异步检测套利机会"""
    try:
        opportunities = []
        
        for symbol in symbols:
            try:
                # 获取所有交易所的ticker数据
                ticker_data = await data_aggregator.get_ticker_data(symbol)
                
                if not ticker_data or len(ticker_data) < 2:
                    continue
                
                # 计算套利机会
                symbol_opportunities = _calculate_arbitrage_opportunities(symbol, ticker_data)
                opportunities.extend(symbol_opportunities)
                
            except Exception as e:
                logger.error(f"Failed to detect opportunities for {symbol}: {str(e)}")
                continue
        
        # 保存发现的套利机会到数据库
        if opportunities:
            await _save_opportunities_to_db(opportunities)
        
        return {
            "symbols_checked": len(symbols),
            "opportunities_found": len(opportunities),
            "high_profit_opportunities": len([op for op in opportunities if op["profit_percentage"] > 1.0]),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async arbitrage detection failed: {str(e)}")
        raise

def _calculate_arbitrage_opportunities(symbol: str, ticker_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """计算套利机会"""
    opportunities = []
    
    try:
        # 提取有效的价格数据
        valid_prices = {}
        for exchange, data in ticker_data.items():
            if data and 'bid' in data and 'ask' in data and data['bid'] and data['ask']:
                valid_prices[exchange] = {
                    'bid': float(data['bid']),
                    'ask': float(data['ask']),
                    'volume': float(data.get('volume', 0)),
                    'timestamp': data.get('timestamp', datetime.utcnow().isoformat())
                }
        
        if len(valid_prices) < 2:
            return opportunities
        
        # 计算所有交易所对之间的套利机会
        exchanges = list(valid_prices.keys())
        
        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                exchange_a = exchanges[i]
                exchange_b = exchanges[j]
                
                price_a = valid_prices[exchange_a]
                price_b = valid_prices[exchange_b]
                
                # 计算两个方向的套利机会
                # 方向1: 在A买入，在B卖出
                profit_a_to_b = _calculate_profit(
                    buy_price=price_a['ask'],
                    sell_price=price_b['bid'],
                    buy_exchange=exchange_a,
                    sell_exchange=exchange_b
                )
                
                # 方向2: 在B买入，在A卖出
                profit_b_to_a = _calculate_profit(
                    buy_price=price_b['ask'],
                    sell_price=price_a['bid'],
                    buy_exchange=exchange_b,
                    sell_exchange=exchange_a
                )
                
                # 检查是否满足最小利润阈值
                min_profit = settings.min_profit_threshold
                
                if profit_a_to_b['profit_percentage'] > min_profit:
                    opportunity = {
                        "symbol": symbol,
                        "buy_exchange": exchange_a,
                        "sell_exchange": exchange_b,
                        "buy_price": price_a['ask'],
                        "sell_price": price_b['bid'],
                        "profit_percentage": profit_a_to_b['profit_percentage'],
                        "profit_amount": profit_a_to_b['profit_amount'],
                        "volume": min(price_a['volume'], price_b['volume']),
                        "timestamp": datetime.utcnow().isoformat(),
                        "confidence": _calculate_confidence(price_a, price_b)
                    }
                    opportunities.append(opportunity)
                
                if profit_b_to_a['profit_percentage'] > min_profit:
                    opportunity = {
                        "symbol": symbol,
                        "buy_exchange": exchange_b,
                        "sell_exchange": exchange_a,
                        "buy_price": price_b['ask'],
                        "sell_price": price_a['bid'],
                        "profit_percentage": profit_b_to_a['profit_percentage'],
                        "profit_amount": profit_b_to_a['profit_amount'],
                        "volume": min(price_a['volume'], price_b['volume']),
                        "timestamp": datetime.utcnow().isoformat(),
                        "confidence": _calculate_confidence(price_b, price_a)
                    }
                    opportunities.append(opportunity)
        
        # 按利润率排序
        opportunities.sort(key=lambda x: x['profit_percentage'], reverse=True)
        
        return opportunities
        
    except Exception as e:
        logger.error(f"Failed to calculate arbitrage opportunities for {symbol}: {str(e)}")
        return []

def _calculate_profit(buy_price: float, sell_price: float, buy_exchange: str, sell_exchange: str) -> Dict[str, float]:
    """计算利润"""
    try:
        # 考虑交易费用（简化处理，实际应该从交易所获取具体费率）
        buy_fee = 0.001  # 0.1%
        sell_fee = 0.001  # 0.1%
        
        # 计算实际成本和收入
        actual_buy_cost = buy_price * (1 + buy_fee)
        actual_sell_income = sell_price * (1 - sell_fee)
        
        # 计算利润
        profit_amount = actual_sell_income - actual_buy_cost
        profit_percentage = (profit_amount / actual_buy_cost) * 100 if actual_buy_cost > 0 else 0
        
        return {
            "profit_amount": profit_amount,
            "profit_percentage": profit_percentage,
            "buy_cost": actual_buy_cost,
            "sell_income": actual_sell_income
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate profit: {str(e)}")
        return {"profit_amount": 0, "profit_percentage": 0, "buy_cost": 0, "sell_income": 0}

def _calculate_confidence(price_a: Dict[str, Any], price_b: Dict[str, Any]) -> float:
    """计算套利机会的置信度"""
    try:
        # 基于交易量和价差稳定性计算置信度
        volume_score = min(price_a['volume'], price_b['volume']) / 1000000  # 标准化到百万
        volume_score = min(volume_score, 1.0)  # 最大为1
        
        # 价差稳定性（简化处理）
        spread_a = abs(price_a['ask'] - price_a['bid']) / price_a['ask'] if price_a['ask'] > 0 else 1
        spread_b = abs(price_b['ask'] - price_b['bid']) / price_b['ask'] if price_b['ask'] > 0 else 1
        spread_score = 1 - min(spread_a + spread_b, 1.0)
        
        # 综合置信度
        confidence = (volume_score * 0.6 + spread_score * 0.4) * 100
        return round(confidence, 2)
        
    except Exception as e:
        logger.error(f"Failed to calculate confidence: {str(e)}")
        return 0.0

async def _save_opportunities_to_db(opportunities: List[Dict[str, Any]]):
    """保存套利机会到数据库"""
    try:
        async with get_async_session() as session:
            for opp in opportunities:
                # 检查是否已存在相似的机会（避免重复）
                existing = await session.execute(
                    select(ArbitrageOpportunity).where(
                        and_(
                            ArbitrageOpportunity.symbol == opp["symbol"],
                            ArbitrageOpportunity.buy_exchange == opp["buy_exchange"],
                            ArbitrageOpportunity.sell_exchange == opp["sell_exchange"],
                            ArbitrageOpportunity.created_at > datetime.utcnow() - timedelta(minutes=5)
                        )
                    )
                )
                
                if not existing.scalar_one_or_none():
                    # 创建新的套利机会记录
                    db_opportunity = ArbitrageOpportunity(
                        symbol=opp["symbol"],
                        buy_exchange=opp["buy_exchange"],
                        sell_exchange=opp["sell_exchange"],
                        buy_price=Decimal(str(opp["buy_price"])),
                        sell_price=Decimal(str(opp["sell_price"])),
                        profit_percentage=Decimal(str(opp["profit_percentage"])),
                        profit_amount=Decimal(str(opp["profit_amount"])),
                        volume=Decimal(str(opp["volume"])),
                        confidence=Decimal(str(opp["confidence"])),
                        status="active"
                    )
                    session.add(db_opportunity)
            
            await session.commit()
            
    except Exception as e:
        logger.error(f"Failed to save opportunities to database: {str(e)}")
        raise

@task_with_retry(name="app.tasks.arbitrage_detection.calculate_profits")
def calculate_profits(self, opportunity_ids: List[int] = None):
    """计算套利利润任务"""
    try:
        result = asyncio.run(_calculate_profits_async(opportunity_ids))
        
        logger.info(f"Profit calculation completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Profit calculation failed: {str(e)}")
        raise self.retry(countdown=30, max_retries=3)

async def _calculate_profits_async(opportunity_ids: Optional[List[int]]):
    """异步计算套利利润"""
    try:
        async with get_async_session() as session:
            # 获取活跃的套利机会
            if opportunity_ids:
                query = select(ArbitrageOpportunity).where(
                    and_(
                        ArbitrageOpportunity.id.in_(opportunity_ids),
                        ArbitrageOpportunity.status == "active"
                    )
                )
            else:
                query = select(ArbitrageOpportunity).where(
                    and_(
                        ArbitrageOpportunity.status == "active",
                        ArbitrageOpportunity.created_at > datetime.utcnow() - timedelta(hours=1)
                    )
                )
            
            result = await session.execute(query)
            opportunities = result.scalars().all()
            
            updated_opportunities = []
            
            for opp in opportunities:
                try:
                    # 获取最新价格数据
                    ticker_data = await data_aggregator.get_ticker_data(opp.symbol)
                    
                    if not ticker_data:
                        continue
                    
                    buy_exchange_data = ticker_data.get(opp.buy_exchange)
                    sell_exchange_data = ticker_data.get(opp.sell_exchange)
                    
                    if not buy_exchange_data or not sell_exchange_data:
                        continue
                    
                    # 重新计算利润
                    current_profit = _calculate_profit(
                        buy_price=float(buy_exchange_data.get('ask', 0)),
                        sell_price=float(sell_exchange_data.get('bid', 0)),
                        buy_exchange=opp.buy_exchange,
                        sell_exchange=opp.sell_exchange
                    )
                    
                    # 更新机会数据
                    opp.buy_price = Decimal(str(buy_exchange_data.get('ask', 0)))
                    opp.sell_price = Decimal(str(sell_exchange_data.get('bid', 0)))
                    opp.profit_percentage = Decimal(str(current_profit['profit_percentage']))
                    opp.profit_amount = Decimal(str(current_profit['profit_amount']))
                    opp.updated_at = datetime.utcnow()
                    
                    # 如果利润低于阈值，标记为过期
                    if current_profit['profit_percentage'] < settings.min_profit_threshold:
                        opp.status = "expired"
                    
                    updated_opportunities.append({
                        "id": opp.id,
                        "symbol": opp.symbol,
                        "profit_percentage": float(opp.profit_percentage),
                        "status": opp.status
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to update opportunity {opp.id}: {str(e)}")
                    continue
            
            await session.commit()
            
            return {
                "opportunities_processed": len(opportunities),
                "opportunities_updated": len(updated_opportunities),
                "active_opportunities": len([op for op in updated_opportunities if op["status"] == "active"]),
                "expired_opportunities": len([op for op in updated_opportunities if op["status"] == "expired"]),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async profit calculation failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.arbitrage_detection.analyze_market_trends")
def analyze_market_trends(self, symbols: List[str] = None, timeframe: str = "1h"):
    """分析市场趋势任务"""
    try:
        if not symbols:
            symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        
        result = asyncio.run(_analyze_market_trends_async(symbols, timeframe))
        
        logger.info(f"Market trend analysis completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Market trend analysis failed: {str(e)}")
        raise self.retry(countdown=60, max_retries=2)

async def _analyze_market_trends_async(symbols: List[str], timeframe: str):
    """异步分析市场趋势"""
    try:
        trend_analysis = {
            "symbols": {},
            "overall_trend": "neutral",
            "volatility_level": "normal",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for symbol in symbols:
            try:
                # 获取历史数据进行趋势分析
                ticker_data = await data_aggregator.get_ticker_data(symbol)
                
                if not ticker_data:
                    continue
                
                # 简化的趋势分析
                prices = []
                volumes = []
                
                for exchange, data in ticker_data.items():
                    if data and 'last' in data:
                        prices.append(float(data['last']))
                        volumes.append(float(data.get('volume', 0)))
                
                if len(prices) >= 2:
                    avg_price = sum(prices) / len(prices)
                    price_variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
                    volatility = (price_variance ** 0.5) / avg_price * 100
                    
                    trend_analysis["symbols"][symbol] = {
                        "average_price": avg_price,
                        "volatility": volatility,
                        "volume": sum(volumes),
                        "exchanges_count": len(prices),
                        "trend": "volatile" if volatility > 5 else "stable"
                    }
                    
            except Exception as e:
                logger.error(f"Failed to analyze trend for {symbol}: {str(e)}")
                continue
        
        # 计算整体市场趋势
        if trend_analysis["symbols"]:
            avg_volatility = sum(data["volatility"] for data in trend_analysis["symbols"].values()) / len(trend_analysis["symbols"])
            
            if avg_volatility > 10:
                trend_analysis["volatility_level"] = "high"
                trend_analysis["overall_trend"] = "volatile"
            elif avg_volatility > 5:
                trend_analysis["volatility_level"] = "medium"
                trend_analysis["overall_trend"] = "moderate"
            else:
                trend_analysis["volatility_level"] = "low"
                trend_analysis["overall_trend"] = "stable"
        
        return trend_analysis
        
    except Exception as e:
        logger.error(f"Async market trend analysis failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.arbitrage_detection.cleanup_expired_opportunities")
def cleanup_expired_opportunities(self):
    """清理过期套利机会任务"""
    try:
        result = asyncio.run(_cleanup_expired_opportunities_async())
        
        logger.info(f"Expired opportunities cleanup completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Expired opportunities cleanup failed: {str(e)}")
        raise self.retry(countdown=300, max_retries=2)

async def _cleanup_expired_opportunities_async():
    """异步清理过期套利机会"""
    try:
        async with get_async_session() as session:
            # 删除超过24小时的过期机会
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            result = await session.execute(
                select(ArbitrageOpportunity).where(
                    and_(
                        ArbitrageOpportunity.status == "expired",
                        ArbitrageOpportunity.updated_at < cutoff_time
                    )
                )
            )
            
            expired_opportunities = result.scalars().all()
            
            for opp in expired_opportunities:
                await session.delete(opp)
            
            await session.commit()
            
            return {
                "deleted_opportunities": len(expired_opportunities),
                "cutoff_time": cutoff_time.isoformat(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async expired opportunities cleanup failed: {str(e)}")
        raise

# 导出任务函数
__all__ = [
    "detect_opportunities",
    "calculate_profits",
    "analyze_market_trends",
    "cleanup_expired_opportunities"
]