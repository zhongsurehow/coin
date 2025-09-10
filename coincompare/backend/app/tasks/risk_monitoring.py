from celery import current_app
from typing import List, Dict, Any, Optional
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import json

from ..celery_app import task_with_retry, urgent_task
from ..services.data_aggregator import data_aggregator
from ..database import get_async_session
from ..models import RiskAlert, Strategy, Trade, User
from ..config import settings
from sqlalchemy import select, and_, func, desc

logger = logging.getLogger(__name__)

@urgent_task(name="app.tasks.risk_monitoring.monitor_portfolio_risk")
def monitor_portfolio_risk(self, user_id: int = None):
    """监控投资组合风险任务（高优先级）"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_monitor_portfolio_risk_async(user_id))
        loop.close()
        
        logger.info(f"Portfolio risk monitoring completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Portfolio risk monitoring failed: {str(e)}")
        raise self.retry(countdown=30, max_retries=5)

async def _monitor_portfolio_risk_async(user_id: Optional[int]):
    """异步监控投资组合风险"""
    try:
        async with get_async_session() as session:
            # 获取需要监控的用户
            if user_id:
                users_query = select(User).where(User.id == user_id)
            else:
                users_query = select(User).where(User.is_active == True)
            
            users_result = await session.execute(users_query)
            users = users_result.scalars().all()
            
            risk_alerts = []
            
            for user in users:
                try:
                    # 获取用户的活跃策略
                    strategies_result = await session.execute(
                        select(Strategy).where(
                            and_(
                                Strategy.user_id == user.id,
                                Strategy.status == "active"
                            )
                        )
                    )
                    strategies = strategies_result.scalars().all()
                    
                    if not strategies:
                        continue
                    
                    # 计算用户风险指标
                    user_risk = await _calculate_user_risk(session, user, strategies)
                    
                    # 检查风险阈值
                    alerts = _check_risk_thresholds(user, user_risk)
                    risk_alerts.extend(alerts)
                    
                except Exception as e:
                    logger.error(f"Failed to monitor risk for user {user.id}: {str(e)}")
                    continue
            
            # 保存风险警报
            if risk_alerts:
                await _save_risk_alerts(session, risk_alerts)
            
            return {
                "users_monitored": len(users),
                "alerts_generated": len(risk_alerts),
                "high_risk_alerts": len([alert for alert in risk_alerts if alert["severity"] == "high"]),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async portfolio risk monitoring failed: {str(e)}")
        raise

async def _calculate_user_risk(session, user: User, strategies: List[Strategy]) -> Dict[str, Any]:
    """计算用户风险指标"""
    try:
        # 获取用户最近的交易记录
        trades_result = await session.execute(
            select(Trade).where(
                and_(
                    Trade.user_id == user.id,
                    Trade.created_at > datetime.utcnow() - timedelta(days=30)
                )
            ).order_by(desc(Trade.created_at))
        )
        trades = trades_result.scalars().all()
        
        # 计算基本风险指标
        total_volume = sum(float(trade.amount) for trade in trades)
        total_profit_loss = sum(float(trade.profit_loss or 0) for trade in trades)
        
        # 计算胜率
        profitable_trades = [trade for trade in trades if float(trade.profit_loss or 0) > 0]
        win_rate = len(profitable_trades) / len(trades) * 100 if trades else 0
        
        # 计算最大回撤
        max_drawdown = _calculate_max_drawdown(trades)
        
        # 计算风险敞口
        total_exposure = sum(float(strategy.max_position_size or 0) for strategy in strategies)
        
        # 计算集中度风险
        symbol_exposure = {}
        for strategy in strategies:
            symbol = strategy.symbol
            if symbol in symbol_exposure:
                symbol_exposure[symbol] += float(strategy.max_position_size or 0)
            else:
                symbol_exposure[symbol] = float(strategy.max_position_size or 0)
        
        max_symbol_exposure = max(symbol_exposure.values()) if symbol_exposure else 0
        concentration_risk = max_symbol_exposure / total_exposure * 100 if total_exposure > 0 else 0
        
        # 计算波动率
        volatility = _calculate_volatility(trades)
        
        return {
            "total_volume": total_volume,
            "total_profit_loss": total_profit_loss,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "total_exposure": total_exposure,
            "concentration_risk": concentration_risk,
            "volatility": volatility,
            "trades_count": len(trades),
            "active_strategies": len(strategies)
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate user risk: {str(e)}")
        return {}

def _calculate_max_drawdown(trades: List[Trade]) -> float:
    """计算最大回撤"""
    try:
        if not trades:
            return 0.0
        
        # 按时间排序
        sorted_trades = sorted(trades, key=lambda x: x.created_at)
        
        # 计算累计收益
        cumulative_returns = []
        cumulative_pnl = 0
        
        for trade in sorted_trades:
            cumulative_pnl += float(trade.profit_loss or 0)
            cumulative_returns.append(cumulative_pnl)
        
        if not cumulative_returns:
            return 0.0
        
        # 计算最大回撤
        peak = cumulative_returns[0]
        max_drawdown = 0
        
        for value in cumulative_returns:
            if value > peak:
                peak = value
            drawdown = (peak - value) / abs(peak) * 100 if peak != 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
        
    except Exception as e:
        logger.error(f"Failed to calculate max drawdown: {str(e)}")
        return 0.0

def _calculate_volatility(trades: List[Trade]) -> float:
    """计算收益波动率"""
    try:
        if len(trades) < 2:
            return 0.0
        
        returns = [float(trade.profit_loss or 0) for trade in trades]
        mean_return = sum(returns) / len(returns)
        
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5
        
        return volatility
        
    except Exception as e:
        logger.error(f"Failed to calculate volatility: {str(e)}")
        return 0.0

def _check_risk_thresholds(user: User, risk_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检查风险阈值"""
    alerts = []
    
    try:
        # 最大回撤警报
        if risk_metrics.get("max_drawdown", 0) > settings.max_drawdown_threshold:
            alerts.append({
                "user_id": user.id,
                "alert_type": "max_drawdown",
                "severity": "high",
                "message": f"最大回撤超过阈值: {risk_metrics['max_drawdown']:.2f}%",
                "value": risk_metrics["max_drawdown"],
                "threshold": settings.max_drawdown_threshold,
                "metadata": {"risk_metrics": risk_metrics}
            })
        
        # 集中度风险警报
        if risk_metrics.get("concentration_risk", 0) > settings.concentration_risk_threshold:
            alerts.append({
                "user_id": user.id,
                "alert_type": "concentration_risk",
                "severity": "medium",
                "message": f"单一标的集中度过高: {risk_metrics['concentration_risk']:.2f}%",
                "value": risk_metrics["concentration_risk"],
                "threshold": settings.concentration_risk_threshold,
                "metadata": {"risk_metrics": risk_metrics}
            })
        
        # 胜率警报
        if risk_metrics.get("win_rate", 100) < settings.min_win_rate_threshold:
            alerts.append({
                "user_id": user.id,
                "alert_type": "low_win_rate",
                "severity": "medium",
                "message": f"胜率过低: {risk_metrics['win_rate']:.2f}%",
                "value": risk_metrics["win_rate"],
                "threshold": settings.min_win_rate_threshold,
                "metadata": {"risk_metrics": risk_metrics}
            })
        
        # 波动率警报
        if risk_metrics.get("volatility", 0) > settings.max_volatility_threshold:
            alerts.append({
                "user_id": user.id,
                "alert_type": "high_volatility",
                "severity": "medium",
                "message": f"收益波动率过高: {risk_metrics['volatility']:.2f}",
                "value": risk_metrics["volatility"],
                "threshold": settings.max_volatility_threshold,
                "metadata": {"risk_metrics": risk_metrics}
            })
        
        # 总敞口警报
        if risk_metrics.get("total_exposure", 0) > settings.max_total_exposure:
            alerts.append({
                "user_id": user.id,
                "alert_type": "high_exposure",
                "severity": "high",
                "message": f"总风险敞口过高: ${risk_metrics['total_exposure']:,.2f}",
                "value": risk_metrics["total_exposure"],
                "threshold": settings.max_total_exposure,
                "metadata": {"risk_metrics": risk_metrics}
            })
        
        return alerts
        
    except Exception as e:
        logger.error(f"Failed to check risk thresholds: {str(e)}")
        return []

async def _save_risk_alerts(session, alerts: List[Dict[str, Any]]):
    """保存风险警报到数据库"""
    try:
        for alert in alerts:
            db_alert = RiskAlert(
                user_id=alert["user_id"],
                alert_type=alert["alert_type"],
                severity=alert["severity"],
                message=alert["message"],
                value=Decimal(str(alert["value"])),
                threshold=Decimal(str(alert["threshold"])),
                metadata=json.dumps(alert["metadata"]),
                status="active"
            )
            session.add(db_alert)
        
        await session.commit()
        
    except Exception as e:
        logger.error(f"Failed to save risk alerts: {str(e)}")
        raise

@task_with_retry(name="app.tasks.risk_monitoring.monitor_market_risk")
def monitor_market_risk(self, symbols: List[str] = None):
    """监控市场风险任务"""
    try:
        if not symbols:
            symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_monitor_market_risk_async(symbols))
        loop.close()
        
        logger.info(f"Market risk monitoring completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Market risk monitoring failed: {str(e)}")
        raise self.retry(countdown=60, max_retries=3)

async def _monitor_market_risk_async(symbols: List[str]):
    """异步监控市场风险"""
    try:
        market_risks = []
        
        for symbol in symbols:
            try:
                # 获取市场数据
                ticker_data = await data_aggregator.get_ticker_data(symbol)
                
                if not ticker_data:
                    continue
                
                # 计算市场风险指标
                risk_metrics = _calculate_market_risk_metrics(symbol, ticker_data)
                
                if risk_metrics:
                    market_risks.append(risk_metrics)
                    
            except Exception as e:
                logger.error(f"Failed to monitor market risk for {symbol}: {str(e)}")
                continue
        
        # 生成市场风险警报
        alerts = _generate_market_risk_alerts(market_risks)
        
        return {
            "symbols_monitored": len(symbols),
            "risk_metrics_calculated": len(market_risks),
            "market_alerts": len(alerts),
            "high_risk_symbols": len([risk for risk in market_risks if risk.get("risk_level") == "high"]),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async market risk monitoring failed: {str(e)}")
        raise

def _calculate_market_risk_metrics(symbol: str, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
    """计算市场风险指标"""
    try:
        prices = []
        volumes = []
        spreads = []
        
        for exchange, data in ticker_data.items():
            if data and 'last' in data:
                prices.append(float(data['last']))
                volumes.append(float(data.get('volume', 0)))
                
                # 计算买卖价差
                if 'bid' in data and 'ask' in data and data['bid'] and data['ask']:
                    spread = (float(data['ask']) - float(data['bid'])) / float(data['ask']) * 100
                    spreads.append(spread)
        
        if not prices:
            return {}
        
        # 计算价格离散度
        avg_price = sum(prices) / len(prices)
        price_variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
        price_volatility = (price_variance ** 0.5) / avg_price * 100
        
        # 计算流动性风险
        total_volume = sum(volumes)
        avg_spread = sum(spreads) / len(spreads) if spreads else 0
        
        # 评估风险等级
        risk_level = "low"
        if price_volatility > 10 or avg_spread > 1.0:
            risk_level = "high"
        elif price_volatility > 5 or avg_spread > 0.5:
            risk_level = "medium"
        
        return {
            "symbol": symbol,
            "price_volatility": price_volatility,
            "average_price": avg_price,
            "total_volume": total_volume,
            "average_spread": avg_spread,
            "exchanges_count": len(prices),
            "risk_level": risk_level,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate market risk metrics for {symbol}: {str(e)}")
        return {}

def _generate_market_risk_alerts(market_risks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """生成市场风险警报"""
    alerts = []
    
    try:
        for risk in market_risks:
            # 高波动率警报
            if risk.get("price_volatility", 0) > 15:
                alerts.append({
                    "alert_type": "high_market_volatility",
                    "symbol": risk["symbol"],
                    "severity": "high",
                    "message": f"{risk['symbol']} 价格波动率异常: {risk['price_volatility']:.2f}%",
                    "value": risk["price_volatility"],
                    "metadata": risk
                })
            
            # 流动性风险警报
            if risk.get("average_spread", 0) > 2.0:
                alerts.append({
                    "alert_type": "liquidity_risk",
                    "symbol": risk["symbol"],
                    "severity": "medium",
                    "message": f"{risk['symbol']} 买卖价差过大: {risk['average_spread']:.2f}%",
                    "value": risk["average_spread"],
                    "metadata": risk
                })
            
            # 交易量异常警报
            if risk.get("total_volume", 0) < 1000:
                alerts.append({
                    "alert_type": "low_volume",
                    "symbol": risk["symbol"],
                    "severity": "low",
                    "message": f"{risk['symbol']} 交易量过低: {risk['total_volume']:,.0f}",
                    "value": risk["total_volume"],
                    "metadata": risk
                })
        
        return alerts
        
    except Exception as e:
        logger.error(f"Failed to generate market risk alerts: {str(e)}")
        return []

@task_with_retry(name="app.tasks.risk_monitoring.check_strategy_performance")
def check_strategy_performance(self, strategy_ids: List[int] = None):
    """检查策略表现任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_check_strategy_performance_async(strategy_ids))
        loop.close()
        
        logger.info(f"Strategy performance check completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Strategy performance check failed: {str(e)}")
        raise self.retry(countdown=120, max_retries=2)

async def _check_strategy_performance_async(strategy_ids: Optional[List[int]]):
    """异步检查策略表现"""
    try:
        async with get_async_session() as session:
            # 获取需要检查的策略
            if strategy_ids:
                strategies_query = select(Strategy).where(Strategy.id.in_(strategy_ids))
            else:
                strategies_query = select(Strategy).where(Strategy.status == "active")
            
            strategies_result = await session.execute(strategies_query)
            strategies = strategies_result.scalars().all()
            
            performance_alerts = []
            
            for strategy in strategies:
                try:
                    # 获取策略的交易记录
                    trades_result = await session.execute(
                        select(Trade).where(
                            and_(
                                Trade.strategy_id == strategy.id,
                                Trade.created_at > datetime.utcnow() - timedelta(days=7)
                            )
                        )
                    )
                    trades = trades_result.scalars().all()
                    
                    # 计算策略表现指标
                    performance = _calculate_strategy_performance(strategy, trades)
                    
                    # 检查表现阈值
                    alerts = _check_strategy_thresholds(strategy, performance)
                    performance_alerts.extend(alerts)
                    
                except Exception as e:
                    logger.error(f"Failed to check performance for strategy {strategy.id}: {str(e)}")
                    continue
            
            # 保存策略表现警报
            if performance_alerts:
                await _save_risk_alerts(session, performance_alerts)
            
            return {
                "strategies_checked": len(strategies),
                "performance_alerts": len(performance_alerts),
                "underperforming_strategies": len([alert for alert in performance_alerts if "underperform" in alert.get("alert_type", "")]),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async strategy performance check failed: {str(e)}")
        raise

def _calculate_strategy_performance(strategy: Strategy, trades: List[Trade]) -> Dict[str, Any]:
    """计算策略表现指标"""
    try:
        if not trades:
            return {
                "total_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "max_consecutive_losses": 0
            }
        
        total_pnl = sum(float(trade.profit_loss or 0) for trade in trades)
        profitable_trades = [trade for trade in trades if float(trade.profit_loss or 0) > 0]
        losing_trades = [trade for trade in trades if float(trade.profit_loss or 0) < 0]
        
        win_rate = len(profitable_trades) / len(trades) * 100
        avg_profit = sum(float(trade.profit_loss) for trade in profitable_trades) / len(profitable_trades) if profitable_trades else 0
        avg_loss = sum(float(trade.profit_loss) for trade in losing_trades) / len(losing_trades) if losing_trades else 0
        
        total_profit = sum(float(trade.profit_loss) for trade in profitable_trades)
        total_loss = abs(sum(float(trade.profit_loss) for trade in losing_trades))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # 计算最大连续亏损
        max_consecutive_losses = _calculate_max_consecutive_losses(trades)
        
        return {
            "total_trades": len(trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_consecutive_losses": max_consecutive_losses
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate strategy performance: {str(e)}")
        return {}

def _calculate_max_consecutive_losses(trades: List[Trade]) -> int:
    """计算最大连续亏损次数"""
    try:
        if not trades:
            return 0
        
        sorted_trades = sorted(trades, key=lambda x: x.created_at)
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in sorted_trades:
            if float(trade.profit_loss or 0) < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
        
    except Exception as e:
        logger.error(f"Failed to calculate max consecutive losses: {str(e)}")
        return 0

def _check_strategy_thresholds(strategy: Strategy, performance: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检查策略表现阈值"""
    alerts = []
    
    try:
        # 胜率过低警报
        if performance.get("win_rate", 100) < 30:
            alerts.append({
                "user_id": strategy.user_id,
                "alert_type": "strategy_underperform_winrate",
                "severity": "medium",
                "message": f"策略 {strategy.name} 胜率过低: {performance['win_rate']:.2f}%",
                "value": performance["win_rate"],
                "threshold": 30,
                "metadata": {"strategy_id": strategy.id, "performance": performance}
            })
        
        # 连续亏损警报
        if performance.get("max_consecutive_losses", 0) > 5:
            alerts.append({
                "user_id": strategy.user_id,
                "alert_type": "strategy_consecutive_losses",
                "severity": "high",
                "message": f"策略 {strategy.name} 连续亏损 {performance['max_consecutive_losses']} 次",
                "value": performance["max_consecutive_losses"],
                "threshold": 5,
                "metadata": {"strategy_id": strategy.id, "performance": performance}
            })
        
        # 盈亏比过低警报
        if performance.get("profit_factor", 0) < 1.2:
            alerts.append({
                "user_id": strategy.user_id,
                "alert_type": "strategy_low_profit_factor",
                "severity": "medium",
                "message": f"策略 {strategy.name} 盈亏比过低: {performance['profit_factor']:.2f}",
                "value": performance["profit_factor"],
                "threshold": 1.2,
                "metadata": {"strategy_id": strategy.id, "performance": performance}
            })
        
        # 总收益为负警报
        if performance.get("total_pnl", 0) < -1000:
            alerts.append({
                "user_id": strategy.user_id,
                "alert_type": "strategy_negative_pnl",
                "severity": "high",
                "message": f"策略 {strategy.name} 总收益为负: ${performance['total_pnl']:.2f}",
                "value": performance["total_pnl"],
                "threshold": -1000,
                "metadata": {"strategy_id": strategy.id, "performance": performance}
            })
        
        return alerts
        
    except Exception as e:
        logger.error(f"Failed to check strategy thresholds: {str(e)}")
        return []

@task_with_retry(name="app.tasks.risk_monitoring.cleanup_old_alerts")
def cleanup_old_alerts(self):
    """清理旧的风险警报任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_cleanup_old_alerts_async())
        loop.close()
        
        logger.info(f"Old alerts cleanup completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Old alerts cleanup failed: {str(e)}")
        raise self.retry(countdown=300, max_retries=2)

async def _cleanup_old_alerts_async():
    """异步清理旧的风险警报"""
    try:
        async with get_async_session() as session:
            # 删除超过30天的已处理警报
            cutoff_time = datetime.utcnow() - timedelta(days=30)
            
            result = await session.execute(
                select(RiskAlert).where(
                    and_(
                        RiskAlert.status.in_(["resolved", "dismissed"]),
                        RiskAlert.created_at < cutoff_time
                    )
                )
            )
            
            old_alerts = result.scalars().all()
            
            for alert in old_alerts:
                await session.delete(alert)
            
            await session.commit()
            
            return {
                "deleted_alerts": len(old_alerts),
                "cutoff_time": cutoff_time.isoformat(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async old alerts cleanup failed: {str(e)}")
        raise

# 导出任务函数
__all__ = [
    "monitor_portfolio_risk",
    "monitor_market_risk",
    "check_strategy_performance",
    "cleanup_old_alerts"
]