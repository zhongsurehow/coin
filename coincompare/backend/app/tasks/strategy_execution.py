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
from ..models import Strategy, Trade, ArbitrageOpportunity, User
from ..config import settings
from sqlalchemy import select, and_, desc

logger = logging.getLogger(__name__)

@urgent_task(name="app.tasks.strategy_execution.execute_arbitrage_strategy")
def execute_arbitrage_strategy(self, strategy_id: int, opportunity_id: int = None):
    """执行套利策略任务（高优先级）"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_execute_arbitrage_strategy_async(strategy_id, opportunity_id))
        loop.close()
        
        logger.info(f"Arbitrage strategy execution completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Arbitrage strategy execution failed: {str(e)}")
        raise self.retry(countdown=30, max_retries=3)

async def _execute_arbitrage_strategy_async(strategy_id: int, opportunity_id: Optional[int]):
    """异步执行套利策略"""
    try:
        async with get_async_session() as session:
            # 获取策略信息
            strategy_result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = strategy_result.scalar_one_or_none()
            
            if not strategy or strategy.status != "active":
                return {"error": "Strategy not found or not active"}
            
            # 获取套利机会
            if opportunity_id:
                opp_result = await session.execute(
                    select(ArbitrageOpportunity).where(ArbitrageOpportunity.id == opportunity_id)
                )
                opportunity = opp_result.scalar_one_or_none()
            else:
                # 查找最佳套利机会
                opportunity = await _find_best_opportunity(session, strategy)
            
            if not opportunity:
                return {"error": "No suitable arbitrage opportunity found"}
            
            # 验证策略参数
            validation_result = await _validate_strategy_execution(strategy, opportunity)
            if not validation_result["valid"]:
                return {"error": validation_result["reason"]}
            
            # 执行套利交易
            execution_result = await _execute_arbitrage_trades(strategy, opportunity)
            
            # 记录交易结果
            if execution_result["success"]:
                await _record_trade_results(session, strategy, opportunity, execution_result)
            
            return {
                "strategy_id": strategy_id,
                "opportunity_id": opportunity.id,
                "execution_result": execution_result,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async arbitrage strategy execution failed: {str(e)}")
        raise

async def _find_best_opportunity(session, strategy: Strategy) -> Optional[ArbitrageOpportunity]:
    """查找最佳套利机会"""
    try:
        # 查找符合策略条件的套利机会
        query = select(ArbitrageOpportunity).where(
            and_(
                ArbitrageOpportunity.symbol == strategy.symbol,
                ArbitrageOpportunity.status == "active",
                ArbitrageOpportunity.profit_percentage >= strategy.min_profit_threshold,
                ArbitrageOpportunity.created_at > datetime.utcnow() - timedelta(minutes=5)
            )
        ).order_by(desc(ArbitrageOpportunity.profit_percentage))
        
        result = await session.execute(query)
        opportunities = result.scalars().all()
        
        if not opportunities:
            return None
        
        # 选择最佳机会（考虑利润率和置信度）
        best_opportunity = None
        best_score = 0
        
        for opp in opportunities:
            # 计算综合评分
            score = float(opp.profit_percentage) * 0.7 + float(opp.confidence) * 0.3
            
            if score > best_score:
                best_score = score
                best_opportunity = opp
        
        return best_opportunity
        
    except Exception as e:
        logger.error(f"Failed to find best opportunity: {str(e)}")
        return None

async def _validate_strategy_execution(strategy: Strategy, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
    """验证策略执行条件"""
    try:
        # 检查策略状态
        if strategy.status != "active":
            return {"valid": False, "reason": "Strategy is not active"}
        
        # 检查最小利润阈值
        if float(opportunity.profit_percentage) < float(strategy.min_profit_threshold or 0):
            return {"valid": False, "reason": "Profit below minimum threshold"}
        
        # 检查最大仓位限制
        if float(opportunity.volume) > float(strategy.max_position_size or 0):
            return {"valid": False, "reason": "Volume exceeds maximum position size"}
        
        # 检查风险限制
        if float(opportunity.profit_percentage) > 10:  # 利润过高可能有风险
            return {"valid": False, "reason": "Profit too high, potential risk"}
        
        # 检查交易所可用性
        buy_exchange_available = await _check_exchange_availability(opportunity.buy_exchange)
        sell_exchange_available = await _check_exchange_availability(opportunity.sell_exchange)
        
        if not buy_exchange_available or not sell_exchange_available:
            return {"valid": False, "reason": "Exchange not available"}
        
        # 检查资金充足性
        balance_check = await _check_balance_sufficiency(strategy, opportunity)
        if not balance_check["sufficient"]:
            return {"valid": False, "reason": balance_check["reason"]}
        
        return {"valid": True, "reason": "All validations passed"}
        
    except Exception as e:
        logger.error(f"Failed to validate strategy execution: {str(e)}")
        return {"valid": False, "reason": f"Validation error: {str(e)}"}

async def _check_exchange_availability(exchange_name: str) -> bool:
    """检查交易所可用性"""
    try:
        # 简化的交易所可用性检查
        # 实际实现中应该检查交易所API状态
        available_exchanges = ["binance", "huobi", "okx", "coinbase", "kraken"]
        return exchange_name.lower() in available_exchanges
        
    except Exception as e:
        logger.error(f"Failed to check exchange availability: {str(e)}")
        return False

async def _check_balance_sufficiency(strategy: Strategy, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
    """检查资金充足性"""
    try:
        # 简化的资金检查
        # 实际实现中应该查询用户在各交易所的余额
        required_amount = float(opportunity.buy_price) * float(opportunity.volume)
        
        # 假设用户有足够资金（实际应该查询数据库或API）
        available_balance = 10000  # 简化处理
        
        if required_amount > available_balance:
            return {
                "sufficient": False,
                "reason": f"Insufficient balance: required ${required_amount:.2f}, available ${available_balance:.2f}"
            }
        
        return {"sufficient": True, "reason": "Balance sufficient"}
        
    except Exception as e:
        logger.error(f"Failed to check balance sufficiency: {str(e)}")
        return {"sufficient": False, "reason": f"Balance check error: {str(e)}"}

async def _execute_arbitrage_trades(strategy: Strategy, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
    """执行套利交易"""
    try:
        # 模拟交易执行（实际实现中应该调用交易所API）
        execution_result = {
            "success": True,
            "buy_order": {
                "exchange": opportunity.buy_exchange,
                "symbol": opportunity.symbol,
                "side": "buy",
                "amount": float(opportunity.volume),
                "price": float(opportunity.buy_price),
                "order_id": f"buy_{datetime.utcnow().timestamp()}",
                "status": "filled",
                "executed_at": datetime.utcnow().isoformat()
            },
            "sell_order": {
                "exchange": opportunity.sell_exchange,
                "symbol": opportunity.symbol,
                "side": "sell",
                "amount": float(opportunity.volume),
                "price": float(opportunity.sell_price),
                "order_id": f"sell_{datetime.utcnow().timestamp()}",
                "status": "filled",
                "executed_at": datetime.utcnow().isoformat()
            },
            "profit": float(opportunity.profit_amount),
            "profit_percentage": float(opportunity.profit_percentage),
            "fees": {
                "buy_fee": float(opportunity.buy_price) * float(opportunity.volume) * 0.001,
                "sell_fee": float(opportunity.sell_price) * float(opportunity.volume) * 0.001
            }
        }
        
        # 计算实际净利润
        total_fees = execution_result["fees"]["buy_fee"] + execution_result["fees"]["sell_fee"]
        net_profit = execution_result["profit"] - total_fees
        execution_result["net_profit"] = net_profit
        
        logger.info(f"Arbitrage trade executed successfully: {execution_result}")
        return execution_result
        
    except Exception as e:
        logger.error(f"Failed to execute arbitrage trades: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

async def _record_trade_results(session, strategy: Strategy, opportunity: ArbitrageOpportunity, execution_result: Dict[str, Any]):
    """记录交易结果"""
    try:
        # 记录买入交易
        buy_trade = Trade(
            user_id=strategy.user_id,
            strategy_id=strategy.id,
            symbol=opportunity.symbol,
            exchange=opportunity.buy_exchange,
            side="buy",
            amount=Decimal(str(execution_result["buy_order"]["amount"])),
            price=Decimal(str(execution_result["buy_order"]["price"])),
            order_id=execution_result["buy_order"]["order_id"],
            status="filled",
            fee=Decimal(str(execution_result["fees"]["buy_fee"])),
            profit_loss=Decimal("0"),  # 买入交易本身不计算盈亏
            metadata=json.dumps(execution_result["buy_order"])
        )
        session.add(buy_trade)
        
        # 记录卖出交易
        sell_trade = Trade(
            user_id=strategy.user_id,
            strategy_id=strategy.id,
            symbol=opportunity.symbol,
            exchange=opportunity.sell_exchange,
            side="sell",
            amount=Decimal(str(execution_result["sell_order"]["amount"])),
            price=Decimal(str(execution_result["sell_order"]["price"])),
            order_id=execution_result["sell_order"]["order_id"],
            status="filled",
            fee=Decimal(str(execution_result["fees"]["sell_fee"])),
            profit_loss=Decimal(str(execution_result["net_profit"])),
            metadata=json.dumps(execution_result["sell_order"])
        )
        session.add(sell_trade)
        
        # 更新套利机会状态
        opportunity.status = "executed"
        opportunity.updated_at = datetime.utcnow()
        
        await session.commit()
        
    except Exception as e:
        logger.error(f"Failed to record trade results: {str(e)}")
        raise

@task_with_retry(name="app.tasks.strategy_execution.monitor_active_strategies")
def monitor_active_strategies(self, user_id: int = None):
    """监控活跃策略任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_monitor_active_strategies_async(user_id))
        loop.close()
        
        logger.info(f"Active strategies monitoring completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Active strategies monitoring failed: {str(e)}")
        raise self.retry(countdown=60, max_retries=3)

async def _monitor_active_strategies_async(user_id: Optional[int]):
    """异步监控活跃策略"""
    try:
        async with get_async_session() as session:
            # 获取活跃策略
            if user_id:
                query = select(Strategy).where(
                    and_(
                        Strategy.user_id == user_id,
                        Strategy.status == "active"
                    )
                )
            else:
                query = select(Strategy).where(Strategy.status == "active")
            
            result = await session.execute(query)
            strategies = result.scalars().all()
            
            monitoring_results = []
            
            for strategy in strategies:
                try:
                    # 检查策略表现
                    performance = await _check_strategy_performance(session, strategy)
                    
                    # 检查是否需要调整策略
                    adjustment_needed = _evaluate_strategy_adjustment(strategy, performance)
                    
                    monitoring_results.append({
                        "strategy_id": strategy.id,
                        "strategy_name": strategy.name,
                        "performance": performance,
                        "adjustment_needed": adjustment_needed,
                        "status": strategy.status
                    })
                    
                    # 如果需要调整，自动调整策略参数
                    if adjustment_needed["needed"]:
                        await _auto_adjust_strategy(session, strategy, adjustment_needed)
                    
                except Exception as e:
                    logger.error(f"Failed to monitor strategy {strategy.id}: {str(e)}")
                    continue
            
            return {
                "strategies_monitored": len(strategies),
                "adjustments_made": len([r for r in monitoring_results if r["adjustment_needed"]["needed"]]),
                "monitoring_results": monitoring_results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async active strategies monitoring failed: {str(e)}")
        raise

async def _check_strategy_performance(session, strategy: Strategy) -> Dict[str, Any]:
    """检查策略表现"""
    try:
        # 获取最近7天的交易记录
        trades_result = await session.execute(
            select(Trade).where(
                and_(
                    Trade.strategy_id == strategy.id,
                    Trade.created_at > datetime.utcnow() - timedelta(days=7)
                )
            )
        )
        trades = trades_result.scalars().all()
        
        if not trades:
            return {
                "total_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "avg_profit_per_trade": 0,
                "max_drawdown": 0
            }
        
        total_pnl = sum(float(trade.profit_loss or 0) for trade in trades)
        profitable_trades = [trade for trade in trades if float(trade.profit_loss or 0) > 0]
        win_rate = len(profitable_trades) / len(trades) * 100
        avg_profit_per_trade = total_pnl / len(trades)
        
        # 计算最大回撤
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0
        
        for trade in sorted(trades, key=lambda x: x.created_at):
            cumulative_pnl += float(trade.profit_loss or 0)
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            drawdown = (peak - cumulative_pnl) / abs(peak) * 100 if peak != 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            "total_trades": len(trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_profit_per_trade": avg_profit_per_trade,
            "max_drawdown": max_drawdown
        }
        
    except Exception as e:
        logger.error(f"Failed to check strategy performance: {str(e)}")
        return {}

def _evaluate_strategy_adjustment(strategy: Strategy, performance: Dict[str, Any]) -> Dict[str, Any]:
    """评估策略是否需要调整"""
    try:
        adjustments = []
        
        # 胜率过低，提高最小利润阈值
        if performance.get("win_rate", 100) < 40:
            adjustments.append({
                "type": "increase_min_profit",
                "reason": "Low win rate",
                "current_value": float(strategy.min_profit_threshold or 0),
                "suggested_value": float(strategy.min_profit_threshold or 0) * 1.2
            })
        
        # 最大回撤过高，减少仓位大小
        if performance.get("max_drawdown", 0) > 15:
            adjustments.append({
                "type": "reduce_position_size",
                "reason": "High max drawdown",
                "current_value": float(strategy.max_position_size or 0),
                "suggested_value": float(strategy.max_position_size or 0) * 0.8
            })
        
        # 平均每笔交易利润过低
        if performance.get("avg_profit_per_trade", 0) < 1:
            adjustments.append({
                "type": "increase_min_profit",
                "reason": "Low average profit per trade",
                "current_value": float(strategy.min_profit_threshold or 0),
                "suggested_value": float(strategy.min_profit_threshold or 0) * 1.1
            })
        
        return {
            "needed": len(adjustments) > 0,
            "adjustments": adjustments
        }
        
    except Exception as e:
        logger.error(f"Failed to evaluate strategy adjustment: {str(e)}")
        return {"needed": False, "adjustments": []}

async def _auto_adjust_strategy(session, strategy: Strategy, adjustment_info: Dict[str, Any]):
    """自动调整策略参数"""
    try:
        for adjustment in adjustment_info["adjustments"]:
            if adjustment["type"] == "increase_min_profit":
                strategy.min_profit_threshold = Decimal(str(adjustment["suggested_value"]))
                logger.info(f"Adjusted min profit threshold for strategy {strategy.id}: {adjustment['suggested_value']}")
            
            elif adjustment["type"] == "reduce_position_size":
                strategy.max_position_size = Decimal(str(adjustment["suggested_value"]))
                logger.info(f"Adjusted max position size for strategy {strategy.id}: {adjustment['suggested_value']}")
        
        strategy.updated_at = datetime.utcnow()
        await session.commit()
        
    except Exception as e:
        logger.error(f"Failed to auto adjust strategy: {str(e)}")
        raise

@task_with_retry(name="app.tasks.strategy_execution.execute_scheduled_strategies")
def execute_scheduled_strategies(self):
    """执行定时策略任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_execute_scheduled_strategies_async())
        loop.close()
        
        logger.info(f"Scheduled strategies execution completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Scheduled strategies execution failed: {str(e)}")
        raise self.retry(countdown=120, max_retries=2)

async def _execute_scheduled_strategies_async():
    """异步执行定时策略"""
    try:
        async with get_async_session() as session:
            # 获取需要执行的定时策略
            query = select(Strategy).where(
                and_(
                    Strategy.status == "active",
                    Strategy.strategy_type == "scheduled",
                    Strategy.next_execution_time <= datetime.utcnow()
                )
            )
            
            result = await session.execute(query)
            strategies = result.scalars().all()
            
            execution_results = []
            
            for strategy in strategies:
                try:
                    # 查找适合的套利机会
                    opportunity = await _find_best_opportunity(session, strategy)
                    
                    if opportunity:
                        # 执行策略
                        execution_result = await _execute_arbitrage_strategy_async(strategy.id, opportunity.id)
                        execution_results.append(execution_result)
                    
                    # 更新下次执行时间
                    if strategy.execution_interval:
                        strategy.next_execution_time = datetime.utcnow() + timedelta(minutes=strategy.execution_interval)
                        await session.commit()
                    
                except Exception as e:
                    logger.error(f"Failed to execute scheduled strategy {strategy.id}: {str(e)}")
                    continue
            
            return {
                "scheduled_strategies": len(strategies),
                "executed_strategies": len(execution_results),
                "successful_executions": len([r for r in execution_results if not r.get("error")]),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async scheduled strategies execution failed: {str(e)}")
        raise

@task_with_retry(name="app.tasks.strategy_execution.cleanup_old_trades")
def cleanup_old_trades(self):
    """清理旧交易记录任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_cleanup_old_trades_async())
        loop.close()
        
        logger.info(f"Old trades cleanup completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Old trades cleanup failed: {str(e)}")
        raise self.retry(countdown=300, max_retries=2)

async def _cleanup_old_trades_async():
    """异步清理旧交易记录"""
    try:
        async with get_async_session() as session:
            # 删除超过90天的交易记录（保留重要数据用于分析）
            cutoff_time = datetime.utcnow() - timedelta(days=90)
            
            result = await session.execute(
                select(Trade).where(Trade.created_at < cutoff_time)
            )
            
            old_trades = result.scalars().all()
            
            # 可以选择归档而不是删除
            for trade in old_trades:
                # 这里可以实现归档逻辑
                await session.delete(trade)
            
            await session.commit()
            
            return {
                "deleted_trades": len(old_trades),
                "cutoff_time": cutoff_time.isoformat(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async old trades cleanup failed: {str(e)}")
        raise

# 导出任务函数
__all__ = [
    "execute_arbitrage_strategy",
    "monitor_active_strategies",
    "execute_scheduled_strategies",
    "cleanup_old_trades"
]