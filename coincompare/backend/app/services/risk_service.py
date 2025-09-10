"""风险管理服务模块

提供风险评估、监控和控制功能，确保交易安全。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
import numpy as np
from dataclasses import dataclass

from ..database import get_async_session
from ..models import (
    Trade, ArbitrageOpportunity, RiskAlert, Strategy, 
    User, Exchange, TradingPair
)
from ..config import settings
from .logging_service import logger


@dataclass
class RiskMetrics:
    """风险指标数据类"""
    max_drawdown: Decimal
    volatility: Decimal
    sharpe_ratio: Decimal
    var_95: Decimal  # 95% VaR
    concentration_risk: Decimal
    liquidity_risk: Decimal
    correlation_risk: Decimal
    timestamp: datetime


@dataclass
class RiskLimits:
    """风险限制数据类"""
    max_position_size: Decimal
    max_daily_loss: Decimal
    max_drawdown: Decimal
    max_concentration: Decimal
    min_liquidity: Decimal
    max_correlation: Decimal


class RiskService:
    """风险管理服务类"""
    
    def __init__(self):
        self.risk_limits = RiskLimits(
            max_position_size=Decimal(str(settings.MAX_POSITION_SIZE)),
            max_daily_loss=Decimal(str(settings.MAX_DAILY_LOSS)),
            max_drawdown=Decimal(str(settings.MAX_DRAWDOWN)),
            max_concentration=Decimal(str(settings.MAX_CONCENTRATION)),
            min_liquidity=Decimal(str(settings.MIN_LIQUIDITY)),
            max_correlation=Decimal(str(settings.MAX_CORRELATION))
        )
        self.alert_cache: Dict[str, datetime] = {}
    
    async def check_arbitrage_risk(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """检查套利机会的风险"""
        try:
            risk_checks = {
                'approved': True,
                'reason': '',
                'risk_score': 0.0,
                'checks': {}
            }
            
            # 1. 检查仓位大小
            position_check = await self._check_position_size(opportunity)
            risk_checks['checks']['position_size'] = position_check
            if not position_check['passed']:
                risk_checks['approved'] = False
                risk_checks['reason'] = position_check['reason']
            
            # 2. 检查流动性风险
            liquidity_check = await self._check_liquidity_risk(opportunity)
            risk_checks['checks']['liquidity'] = liquidity_check
            if not liquidity_check['passed']:
                risk_checks['approved'] = False
                risk_checks['reason'] = liquidity_check['reason']
            
            # 3. 检查价格偏差
            price_check = await self._check_price_deviation(opportunity)
            risk_checks['checks']['price_deviation'] = price_check
            if not price_check['passed']:
                risk_checks['approved'] = False
                risk_checks['reason'] = price_check['reason']
            
            # 4. 检查交易所风险
            exchange_check = await self._check_exchange_risk(opportunity)
            risk_checks['checks']['exchange'] = exchange_check
            if not exchange_check['passed']:
                risk_checks['approved'] = False
                risk_checks['reason'] = exchange_check['reason']
            
            # 5. 检查集中度风险
            concentration_check = await self._check_concentration_risk(opportunity)
            risk_checks['checks']['concentration'] = concentration_check
            if not concentration_check['passed']:
                risk_checks['approved'] = False
                risk_checks['reason'] = concentration_check['reason']
            
            # 计算综合风险评分
            risk_checks['risk_score'] = self._calculate_risk_score(risk_checks['checks'])
            
            # 如果风险评分过高，拒绝交易
            if risk_checks['risk_score'] > 0.8:
                risk_checks['approved'] = False
                risk_checks['reason'] = f"风险评分过高: {risk_checks['risk_score']:.2f}"
            
            logger.info(f"套利风险检查完成: {opportunity.id}, 批准: {risk_checks['approved']}")
            return risk_checks
            
        except Exception as e:
            logger.error(f"套利风险检查失败: {e}")
            return {
                'approved': False,
                'reason': f'风险检查失败: {e}',
                'risk_score': 1.0,
                'checks': {}
            }
    
    async def _check_position_size(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """检查仓位大小"""
        try:
            position_value = opportunity.quantity * opportunity.buy_price
            
            if position_value > self.risk_limits.max_position_size:
                return {
                    'passed': False,
                    'reason': f'仓位大小超限: {position_value} > {self.risk_limits.max_position_size}',
                    'value': float(position_value),
                    'limit': float(self.risk_limits.max_position_size)
                }
            
            return {
                'passed': True,
                'reason': '仓位大小正常',
                'value': float(position_value),
                'limit': float(self.risk_limits.max_position_size)
            }
            
        except Exception as e:
            return {
                'passed': False,
                'reason': f'仓位检查失败: {e}',
                'value': 0,
                'limit': float(self.risk_limits.max_position_size)
            }
    
    async def _check_liquidity_risk(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """检查流动性风险"""
        try:
            # 这里应该检查订单簿深度，暂时使用交易量作为流动性指标
            async with get_async_session() as session:
                # 获取最近24小时的交易量
                yesterday = datetime.utcnow() - timedelta(days=1)
                
                volume_result = await session.execute(
                    select(func.sum(Trade.quantity))
                    .where(Trade.trading_pair_id == opportunity.trading_pair_id)
                    .where(Trade.created_at > yesterday)
                )
                daily_volume = volume_result.scalar() or Decimal('0')
                
                # 检查流动性是否足够
                liquidity_ratio = opportunity.quantity / daily_volume if daily_volume > 0 else Decimal('1')
                
                if liquidity_ratio > self.risk_limits.min_liquidity:
                    return {
                        'passed': False,
                        'reason': f'流动性不足: 交易量占比 {liquidity_ratio:.2%}',
                        'ratio': float(liquidity_ratio),
                        'daily_volume': float(daily_volume)
                    }
                
                return {
                    'passed': True,
                    'reason': '流动性充足',
                    'ratio': float(liquidity_ratio),
                    'daily_volume': float(daily_volume)
                }
                
        except Exception as e:
            return {
                'passed': False,
                'reason': f'流动性检查失败: {e}',
                'ratio': 1.0,
                'daily_volume': 0
            }
    
    async def _check_price_deviation(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """检查价格偏差"""
        try:
            # 计算价格偏差
            price_diff = opportunity.sell_price - opportunity.buy_price
            avg_price = (opportunity.sell_price + opportunity.buy_price) / 2
            deviation = price_diff / avg_price
            
            # 检查偏差是否异常（可能是数据错误）
            max_deviation = Decimal('0.1')  # 10%
            if deviation > max_deviation:
                return {
                    'passed': False,
                    'reason': f'价格偏差异常: {deviation:.2%} > {max_deviation:.2%}',
                    'deviation': float(deviation),
                    'buy_price': float(opportunity.buy_price),
                    'sell_price': float(opportunity.sell_price)
                }
            
            # 检查最小利润率
            min_profit_rate = Decimal('0.001')  # 0.1%
            if deviation < min_profit_rate:
                return {
                    'passed': False,
                    'reason': f'利润率过低: {deviation:.2%} < {min_profit_rate:.2%}',
                    'deviation': float(deviation),
                    'buy_price': float(opportunity.buy_price),
                    'sell_price': float(opportunity.sell_price)
                }
            
            return {
                'passed': True,
                'reason': '价格偏差正常',
                'deviation': float(deviation),
                'buy_price': float(opportunity.buy_price),
                'sell_price': float(opportunity.sell_price)
            }
            
        except Exception as e:
            return {
                'passed': False,
                'reason': f'价格偏差检查失败: {e}',
                'deviation': 0,
                'buy_price': 0,
                'sell_price': 0
            }
    
    async def _check_exchange_risk(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """检查交易所风险"""
        try:
            async with get_async_session() as session:
                # 检查买入交易所状态
                buy_exchange = await session.get(Exchange, opportunity.buy_exchange_id)
                sell_exchange = await session.get(Exchange, opportunity.sell_exchange_id)
                
                if not buy_exchange or not buy_exchange.is_active:
                    return {
                        'passed': False,
                        'reason': '买入交易所不可用',
                        'buy_exchange': buy_exchange.name if buy_exchange else 'Unknown',
                        'sell_exchange': sell_exchange.name if sell_exchange else 'Unknown'
                    }
                
                if not sell_exchange or not sell_exchange.is_active:
                    return {
                        'passed': False,
                        'reason': '卖出交易所不可用',
                        'buy_exchange': buy_exchange.name if buy_exchange else 'Unknown',
                        'sell_exchange': sell_exchange.name if sell_exchange else 'Unknown'
                    }
                
                # 检查交易所信誉评分（如果有的话）
                min_reputation = 0.7
                if (buy_exchange.reputation_score < min_reputation or 
                    sell_exchange.reputation_score < min_reputation):
                    return {
                        'passed': False,
                        'reason': '交易所信誉评分过低',
                        'buy_exchange': buy_exchange.name,
                        'sell_exchange': sell_exchange.name,
                        'buy_reputation': float(buy_exchange.reputation_score),
                        'sell_reputation': float(sell_exchange.reputation_score)
                    }
                
                return {
                    'passed': True,
                    'reason': '交易所状态正常',
                    'buy_exchange': buy_exchange.name,
                    'sell_exchange': sell_exchange.name,
                    'buy_reputation': float(buy_exchange.reputation_score),
                    'sell_reputation': float(sell_exchange.reputation_score)
                }
                
        except Exception as e:
            return {
                'passed': False,
                'reason': f'交易所风险检查失败: {e}',
                'buy_exchange': 'Unknown',
                'sell_exchange': 'Unknown'
            }
    
    async def _check_concentration_risk(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """检查集中度风险"""
        try:
            async with get_async_session() as session:
                # 检查同一交易对的持仓集中度
                total_position = await session.execute(
                    select(func.sum(Trade.quantity))
                    .where(Trade.trading_pair_id == opportunity.trading_pair_id)
                    .where(Trade.status.in_(['pending', 'processing']))
                )
                current_position = total_position.scalar() or Decimal('0')
                
                # 计算新仓位后的集中度
                new_position = current_position + opportunity.quantity
                
                # 获取总资产价值（简化计算）
                total_value = Decimal('100000')  # 假设总资产10万
                position_value = new_position * opportunity.buy_price
                concentration = position_value / total_value
                
                if concentration > self.risk_limits.max_concentration:
                    return {
                        'passed': False,
                        'reason': f'集中度风险过高: {concentration:.2%} > {self.risk_limits.max_concentration:.2%}',
                        'concentration': float(concentration),
                        'current_position': float(current_position),
                        'new_position': float(new_position)
                    }
                
                return {
                    'passed': True,
                    'reason': '集中度风险可控',
                    'concentration': float(concentration),
                    'current_position': float(current_position),
                    'new_position': float(new_position)
                }
                
        except Exception as e:
            return {
                'passed': False,
                'reason': f'集中度风险检查失败: {e}',
                'concentration': 1.0,
                'current_position': 0,
                'new_position': 0
            }
    
    def _calculate_risk_score(self, checks: Dict[str, Dict[str, Any]]) -> float:
        """计算综合风险评分"""
        try:
            total_score = 0.0
            weights = {
                'position_size': 0.2,
                'liquidity': 0.25,
                'price_deviation': 0.2,
                'exchange': 0.2,
                'concentration': 0.15
            }
            
            for check_name, check_result in checks.items():
                if check_name in weights:
                    # 如果检查未通过，给予高风险评分
                    if not check_result.get('passed', False):
                        score = 1.0
                    else:
                        # 根据具体指标计算风险评分
                        score = self._calculate_individual_risk_score(check_name, check_result)
                    
                    total_score += score * weights[check_name]
            
            return min(total_score, 1.0)
            
        except Exception as e:
            logger.error(f"计算风险评分失败: {e}")
            return 1.0
    
    def _calculate_individual_risk_score(self, check_name: str, check_result: Dict[str, Any]) -> float:
        """计算单项风险评分"""
        try:
            if check_name == 'position_size':
                ratio = check_result.get('value', 0) / check_result.get('limit', 1)
                return min(ratio, 1.0)
            
            elif check_name == 'liquidity':
                ratio = check_result.get('ratio', 0)
                return min(ratio * 10, 1.0)  # 流动性比例越高风险越大
            
            elif check_name == 'price_deviation':
                deviation = abs(check_result.get('deviation', 0))
                if deviation > 0.05:  # 5%以上偏差认为高风险
                    return 0.8
                elif deviation < 0.001:  # 0.1%以下偏差认为低利润
                    return 0.6
                else:
                    return 0.2
            
            elif check_name == 'exchange':
                buy_rep = check_result.get('buy_reputation', 1.0)
                sell_rep = check_result.get('sell_reputation', 1.0)
                return 1.0 - min(buy_rep, sell_rep)
            
            elif check_name == 'concentration':
                concentration = check_result.get('concentration', 0)
                return min(concentration * 2, 1.0)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"计算单项风险评分失败: {e}")
            return 1.0
    
    async def calculate_portfolio_risk(self, user_id: int) -> RiskMetrics:
        """计算投资组合风险指标"""
        try:
            async with get_async_session() as session:
                # 获取用户最近的交易记录
                thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                
                trades_result = await session.execute(
                    select(Trade)
                    .where(Trade.user_id == user_id)
                    .where(Trade.created_at > thirty_days_ago)
                    .where(Trade.status == 'completed')
                    .order_by(Trade.created_at)
                )
                trades = trades_result.scalars().all()
                
                if len(trades) < 10:
                    # 交易数据不足，返回默认风险指标
                    return RiskMetrics(
                        max_drawdown=Decimal('0'),
                        volatility=Decimal('0'),
                        sharpe_ratio=Decimal('0'),
                        var_95=Decimal('0'),
                        concentration_risk=Decimal('0'),
                        liquidity_risk=Decimal('0'),
                        correlation_risk=Decimal('0'),
                        timestamp=datetime.utcnow()
                    )
                
                # 计算收益率序列
                returns = []
                cumulative_pnl = Decimal('0')
                peak = Decimal('0')
                max_drawdown = Decimal('0')
                
                for trade in trades:
                    pnl = trade.profit_loss or Decimal('0')
                    cumulative_pnl += pnl
                    
                    # 计算回撤
                    if cumulative_pnl > peak:
                        peak = cumulative_pnl
                    else:
                        drawdown = (peak - cumulative_pnl) / peak if peak > 0 else Decimal('0')
                        if drawdown > max_drawdown:
                            max_drawdown = drawdown
                    
                    # 计算日收益率
                    if len(returns) == 0:
                        returns.append(float(pnl))
                    else:
                        returns.append(float(pnl))
                
                # 计算波动率
                returns_array = np.array(returns)
                volatility = Decimal(str(np.std(returns_array))) if len(returns_array) > 1 else Decimal('0')
                
                # 计算夏普比率
                mean_return = Decimal(str(np.mean(returns_array))) if len(returns_array) > 0 else Decimal('0')
                sharpe_ratio = mean_return / volatility if volatility > 0 else Decimal('0')
                
                # 计算VaR (95%)
                var_95 = Decimal(str(np.percentile(returns_array, 5))) if len(returns_array) > 0 else Decimal('0')
                
                # 计算集中度风险
                concentration_risk = await self._calculate_concentration_risk(session, user_id)
                
                # 计算流动性风险
                liquidity_risk = await self._calculate_liquidity_risk_portfolio(session, user_id)
                
                # 计算相关性风险
                correlation_risk = await self._calculate_correlation_risk(session, user_id)
                
                return RiskMetrics(
                    max_drawdown=max_drawdown,
                    volatility=volatility,
                    sharpe_ratio=sharpe_ratio,
                    var_95=var_95,
                    concentration_risk=concentration_risk,
                    liquidity_risk=liquidity_risk,
                    correlation_risk=correlation_risk,
                    timestamp=datetime.utcnow()
                )
                
        except Exception as e:
            logger.error(f"计算投资组合风险失败: {e}")
            return RiskMetrics(
                max_drawdown=Decimal('1'),
                volatility=Decimal('1'),
                sharpe_ratio=Decimal('0'),
                var_95=Decimal('-1'),
                concentration_risk=Decimal('1'),
                liquidity_risk=Decimal('1'),
                correlation_risk=Decimal('1'),
                timestamp=datetime.utcnow()
            )
    
    async def _calculate_concentration_risk(self, session: AsyncSession, user_id: int) -> Decimal:
        """计算集中度风险"""
        try:
            # 获取当前持仓
            positions = await session.execute(
                select(
                    Trade.trading_pair_id,
                    func.sum(Trade.quantity).label('total_quantity'),
                    func.sum(Trade.quantity * Trade.price).label('total_value')
                )
                .where(Trade.user_id == user_id)
                .where(Trade.status.in_(['pending', 'processing']))
                .group_by(Trade.trading_pair_id)
            )
            
            position_values = []
            total_value = Decimal('0')
            
            for position in positions:
                value = position.total_value or Decimal('0')
                position_values.append(value)
                total_value += value
            
            if total_value == 0:
                return Decimal('0')
            
            # 计算赫芬达尔指数
            hhi = sum((value / total_value) ** 2 for value in position_values)
            return Decimal(str(hhi))
            
        except Exception as e:
            logger.error(f"计算集中度风险失败: {e}")
            return Decimal('1')
    
    async def _calculate_liquidity_risk_portfolio(self, session: AsyncSession, user_id: int) -> Decimal:
        """计算投资组合流动性风险"""
        try:
            # 简化计算：基于交易对的平均交易量
            avg_volume = await session.execute(
                select(func.avg(Trade.quantity))
                .where(Trade.user_id == user_id)
                .where(Trade.created_at > datetime.utcnow() - timedelta(days=7))
            )
            
            volume = avg_volume.scalar() or Decimal('0')
            
            # 流动性风险与交易量成反比
            if volume > 1000:
                return Decimal('0.1')
            elif volume > 100:
                return Decimal('0.3')
            elif volume > 10:
                return Decimal('0.5')
            else:
                return Decimal('0.8')
                
        except Exception as e:
            logger.error(f"计算流动性风险失败: {e}")
            return Decimal('1')
    
    async def _calculate_correlation_risk(self, session: AsyncSession, user_id: int) -> Decimal:
        """计算相关性风险"""
        try:
            # 简化计算：基于交易对的多样性
            unique_pairs = await session.execute(
                select(func.count(func.distinct(Trade.trading_pair_id)))
                .where(Trade.user_id == user_id)
                .where(Trade.status.in_(['pending', 'processing']))
            )
            
            pair_count = unique_pairs.scalar() or 0
            
            # 交易对越多，相关性风险越低
            if pair_count > 10:
                return Decimal('0.1')
            elif pair_count > 5:
                return Decimal('0.3')
            elif pair_count > 2:
                return Decimal('0.5')
            else:
                return Decimal('0.8')
                
        except Exception as e:
            logger.error(f"计算相关性风险失败: {e}")
            return Decimal('1')
    
    async def create_risk_alert(self, alert_type: str, message: str, 
                               severity: str = 'medium', user_id: Optional[int] = None):
        """创建风险警报"""
        try:
            # 检查是否需要限制警报频率
            alert_key = f"{alert_type}_{user_id or 'system'}"
            now = datetime.utcnow()
            
            if alert_key in self.alert_cache:
                last_alert = self.alert_cache[alert_key]
                if (now - last_alert).total_seconds() < 300:  # 5分钟内不重复发送
                    return
            
            async with get_async_session() as session:
                alert = RiskAlert(
                    user_id=user_id,
                    alert_type=alert_type,
                    message=message,
                    severity=severity,
                    is_resolved=False
                )
                session.add(alert)
                await session.commit()
                
                self.alert_cache[alert_key] = now
                logger.warning(f"风险警报: {alert_type} - {message}")
                
        except Exception as e:
            logger.error(f"创建风险警报失败: {e}")


# 全局风险服务实例
risk_service = RiskService()