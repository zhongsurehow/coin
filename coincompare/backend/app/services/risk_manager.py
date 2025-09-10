from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
import logging
from datetime import datetime, timedelta
import numpy as np
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(Enum):
    """警报类型"""
    POSITION_SIZE = "position_size"
    DRAWDOWN = "drawdown"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    CORRELATION = "correlation"
    EXPOSURE = "exposure"
    PERFORMANCE = "performance"
    SYSTEM = "system"

@dataclass
class RiskAlert:
    """风险警报"""
    alert_type: AlertType
    risk_level: RiskLevel
    message: str
    timestamp: datetime
    strategy_id: Optional[str] = None
    exchange: Optional[str] = None
    trading_pair: Optional[str] = None
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    recommended_action: Optional[str] = None

@dataclass
class RiskLimits:
    """风险限制配置"""
    max_position_size: float = 10000.0  # 最大仓位大小
    max_daily_loss: float = 1000.0  # 最大日损失
    max_drawdown: float = 0.1  # 最大回撤 (10%)
    max_correlation: float = 0.8  # 最大相关性
    min_liquidity: float = 100000.0  # 最小流动性
    max_volatility: float = 0.05  # 最大波动率 (5%)
    max_leverage: float = 3.0  # 最大杠杆
    max_exposure_per_exchange: float = 0.3  # 单交易所最大敞口 (30%)
    max_exposure_per_pair: float = 0.2  # 单交易对最大敞口 (20%)
    stop_loss_threshold: float = 0.05  # 止损阈值 (5%)
    position_concentration_limit: float = 0.25  # 仓位集中度限制 (25%)
    
class PositionMonitor:
    """仓位监控器"""
    
    def __init__(self):
        self.positions: Dict[str, Dict[str, float]] = {}  # {exchange: {pair: size}}
        self.total_portfolio_value: float = 0.0
        self.daily_pnl: float = 0.0
        self.max_portfolio_value: float = 0.0
        
    def update_position(self, exchange: str, trading_pair: str, size: float, value: float):
        """更新仓位信息"""
        if exchange not in self.positions:
            self.positions[exchange] = {}
        
        self.positions[exchange][trading_pair] = {
            'size': size,
            'value': value,
            'timestamp': datetime.utcnow()
        }
    
    def get_total_exposure(self) -> float:
        """获取总敞口"""
        total = 0.0
        for exchange_positions in self.positions.values():
            for position in exchange_positions.values():
                total += abs(position.get('value', 0.0))
        return total
    
    def get_exchange_exposure(self, exchange: str) -> float:
        """获取单个交易所敞口"""
        if exchange not in self.positions:
            return 0.0
        
        total = 0.0
        for position in self.positions[exchange].values():
            total += abs(position.get('value', 0.0))
        return total
    
    def get_pair_exposure(self, trading_pair: str) -> float:
        """获取单个交易对敞口"""
        total = 0.0
        for exchange_positions in self.positions.values():
            if trading_pair in exchange_positions:
                total += abs(exchange_positions[trading_pair].get('value', 0.0))
        return total
    
    def calculate_concentration(self) -> Dict[str, float]:
        """计算仓位集中度"""
        total_value = self.get_total_exposure()
        if total_value == 0:
            return {}
        
        concentration = {}
        
        # 按交易所计算集中度
        for exchange in self.positions:
            exchange_value = self.get_exchange_exposure(exchange)
            concentration[f"exchange_{exchange}"] = exchange_value / total_value
        
        # 按交易对计算集中度
        pair_values = {}
        for exchange_positions in self.positions.values():
            for pair, position in exchange_positions.items():
                if pair not in pair_values:
                    pair_values[pair] = 0.0
                pair_values[pair] += abs(position.get('value', 0.0))
        
        for pair, value in pair_values.items():
            concentration[f"pair_{pair}"] = value / total_value
        
        return concentration

class VolatilityCalculator:
    """波动率计算器"""
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}
    
    def add_price(self, symbol: str, price: float, timestamp: datetime = None):
        """添加价格数据"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append((timestamp, price))
        
        # 保持窗口大小
        if len(self.price_history[symbol]) > self.window_size:
            self.price_history[symbol] = self.price_history[symbol][-self.window_size:]
    
    def calculate_volatility(self, symbol: str) -> Optional[float]:
        """计算波动率"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 2:
            return None
        
        prices = [price for _, price in self.price_history[symbol]]
        returns = []
        
        for i in range(1, len(prices)):
            ret = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(ret)
        
        if not returns:
            return None
        
        return float(np.std(returns) * np.sqrt(24 * 365))  # 年化波动率
    
    def calculate_correlation(self, symbol1: str, symbol2: str) -> Optional[float]:
        """计算两个资产的相关性"""
        if (symbol1 not in self.price_history or symbol2 not in self.price_history or
            len(self.price_history[symbol1]) < 2 or len(self.price_history[symbol2]) < 2):
            return None
        
        # 获取共同时间段的价格
        prices1 = [price for _, price in self.price_history[symbol1]]
        prices2 = [price for _, price in self.price_history[symbol2]]
        
        min_len = min(len(prices1), len(prices2))
        if min_len < 2:
            return None
        
        prices1 = prices1[-min_len:]
        prices2 = prices2[-min_len:]
        
        # 计算收益率
        returns1 = [(prices1[i] - prices1[i-1]) / prices1[i-1] for i in range(1, len(prices1))]
        returns2 = [(prices2[i] - prices2[i-1]) / prices2[i-1] for i in range(1, len(prices2))]
        
        if len(returns1) < 2:
            return None
        
        correlation_matrix = np.corrcoef(returns1, returns2)
        return float(correlation_matrix[0, 1])

class LiquidityMonitor:
    """流动性监控器"""
    
    def __init__(self):
        self.orderbook_data: Dict[str, Dict[str, Any]] = {}  # {exchange_pair: orderbook}
    
    def update_orderbook(self, exchange: str, trading_pair: str, orderbook: Dict[str, Any]):
        """更新订单簿数据"""
        key = f"{exchange}_{trading_pair}"
        self.orderbook_data[key] = {
            'bids': orderbook.get('bids', []),
            'asks': orderbook.get('asks', []),
            'timestamp': datetime.utcnow()
        }
    
    def calculate_liquidity(self, exchange: str, trading_pair: str, depth_usd: float = 10000) -> Dict[str, float]:
        """计算流动性指标"""
        key = f"{exchange}_{trading_pair}"
        if key not in self.orderbook_data:
            return {}
        
        orderbook = self.orderbook_data[key]
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return {}
        
        # 计算买卖价差
        best_bid = float(bids[0][0]) if bids else 0
        best_ask = float(asks[0][0]) if asks else 0
        spread = (best_ask - best_bid) / best_bid if best_bid > 0 else 0
        
        # 计算深度
        bid_depth = self._calculate_depth(bids, depth_usd, 'bid')
        ask_depth = self._calculate_depth(asks, depth_usd, 'ask')
        
        # 计算流动性评分
        liquidity_score = min(bid_depth, ask_depth) / depth_usd
        
        return {
            'spread': spread,
            'bid_depth': bid_depth,
            'ask_depth': ask_depth,
            'liquidity_score': liquidity_score,
            'best_bid': best_bid,
            'best_ask': best_ask
        }
    
    def _calculate_depth(self, orders: List[List], target_usd: float, side: str) -> float:
        """计算指定深度的流动性"""
        total_usd = 0.0
        
        for price_str, size_str in orders:
            price = float(price_str)
            size = float(size_str)
            order_usd = price * size
            
            if total_usd + order_usd >= target_usd:
                return target_usd
            
            total_usd += order_usd
        
        return total_usd

class RiskManager:
    """风险管理器"""
    
    def __init__(self, risk_limits: RiskLimits = None):
        self.risk_limits = risk_limits or RiskLimits()
        self.position_monitor = PositionMonitor()
        self.volatility_calculator = VolatilityCalculator()
        self.liquidity_monitor = LiquidityMonitor()
        self.alerts: List[RiskAlert] = []
        self.emergency_stop_triggered = False
        
    async def check_all_risks(self) -> List[RiskAlert]:
        """检查所有风险指标"""
        alerts = []
        
        # 检查仓位风险
        alerts.extend(await self._check_position_risks())
        
        # 检查波动率风险
        alerts.extend(await self._check_volatility_risks())
        
        # 检查流动性风险
        alerts.extend(await self._check_liquidity_risks())
        
        # 检查相关性风险
        alerts.extend(await self._check_correlation_risks())
        
        # 检查敞口风险
        alerts.extend(await self._check_exposure_risks())
        
        # 检查性能风险
        alerts.extend(await self._check_performance_risks())
        
        # 更新警报列表
        self.alerts.extend(alerts)
        
        # 检查是否需要紧急停止
        await self._check_emergency_stop(alerts)
        
        return alerts
    
    async def _check_position_risks(self) -> List[RiskAlert]:
        """检查仓位风险"""
        alerts = []
        
        # 检查单个仓位大小
        for exchange, positions in self.position_monitor.positions.items():
            for pair, position in positions.items():
                position_value = abs(position.get('value', 0.0))
                
                if position_value > self.risk_limits.max_position_size:
                    alerts.append(RiskAlert(
                        alert_type=AlertType.POSITION_SIZE,
                        risk_level=RiskLevel.HIGH,
                        message=f"Position size exceeds limit: {position_value:.2f} > {self.risk_limits.max_position_size:.2f}",
                        timestamp=datetime.utcnow(),
                        exchange=exchange,
                        trading_pair=pair,
                        current_value=position_value,
                        threshold_value=self.risk_limits.max_position_size,
                        recommended_action="Reduce position size"
                    ))
        
        # 检查仓位集中度
        concentration = self.position_monitor.calculate_concentration()
        for key, ratio in concentration.items():
            if ratio > self.risk_limits.position_concentration_limit:
                alerts.append(RiskAlert(
                    alert_type=AlertType.EXPOSURE,
                    risk_level=RiskLevel.MEDIUM,
                    message=f"High concentration in {key}: {ratio:.2%}",
                    timestamp=datetime.utcnow(),
                    current_value=ratio,
                    threshold_value=self.risk_limits.position_concentration_limit,
                    recommended_action="Diversify positions"
                ))
        
        return alerts
    
    async def _check_volatility_risks(self) -> List[RiskAlert]:
        """检查波动率风险"""
        alerts = []
        
        for symbol in self.volatility_calculator.price_history:
            volatility = self.volatility_calculator.calculate_volatility(symbol)
            
            if volatility and volatility > self.risk_limits.max_volatility:
                risk_level = RiskLevel.HIGH if volatility > self.risk_limits.max_volatility * 1.5 else RiskLevel.MEDIUM
                
                alerts.append(RiskAlert(
                    alert_type=AlertType.VOLATILITY,
                    risk_level=risk_level,
                    message=f"High volatility detected for {symbol}: {volatility:.2%}",
                    timestamp=datetime.utcnow(),
                    trading_pair=symbol,
                    current_value=volatility,
                    threshold_value=self.risk_limits.max_volatility,
                    recommended_action="Reduce position size or increase spreads"
                ))
        
        return alerts
    
    async def _check_liquidity_risks(self) -> List[RiskAlert]:
        """检查流动性风险"""
        alerts = []
        
        for key, orderbook in self.liquidity_monitor.orderbook_data.items():
            exchange, pair = key.split('_', 1)
            liquidity_metrics = self.liquidity_monitor.calculate_liquidity(exchange, pair)
            
            if liquidity_metrics:
                liquidity_score = liquidity_metrics.get('liquidity_score', 0)
                spread = liquidity_metrics.get('spread', 0)
                
                # 检查流动性不足
                if liquidity_score < 0.5:  # 流动性评分低于50%
                    alerts.append(RiskAlert(
                        alert_type=AlertType.LIQUIDITY,
                        risk_level=RiskLevel.MEDIUM,
                        message=f"Low liquidity for {exchange} {pair}: score {liquidity_score:.2%}",
                        timestamp=datetime.utcnow(),
                        exchange=exchange,
                        trading_pair=pair,
                        current_value=liquidity_score,
                        threshold_value=0.5,
                        recommended_action="Reduce order size or avoid trading"
                    ))
                
                # 检查价差过大
                if spread > 0.01:  # 价差超过1%
                    alerts.append(RiskAlert(
                        alert_type=AlertType.LIQUIDITY,
                        risk_level=RiskLevel.MEDIUM,
                        message=f"Wide spread for {exchange} {pair}: {spread:.2%}",
                        timestamp=datetime.utcnow(),
                        exchange=exchange,
                        trading_pair=pair,
                        current_value=spread,
                        threshold_value=0.01,
                        recommended_action="Wait for better market conditions"
                    ))
        
        return alerts
    
    async def _check_correlation_risks(self) -> List[RiskAlert]:
        """检查相关性风险"""
        alerts = []
        
        symbols = list(self.volatility_calculator.price_history.keys())
        
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                correlation = self.volatility_calculator.calculate_correlation(symbols[i], symbols[j])
                
                if correlation and abs(correlation) > self.risk_limits.max_correlation:
                    alerts.append(RiskAlert(
                        alert_type=AlertType.CORRELATION,
                        risk_level=RiskLevel.MEDIUM,
                        message=f"High correlation between {symbols[i]} and {symbols[j]}: {correlation:.2f}",
                        timestamp=datetime.utcnow(),
                        current_value=abs(correlation),
                        threshold_value=self.risk_limits.max_correlation,
                        recommended_action="Reduce correlated positions"
                    ))
        
        return alerts
    
    async def _check_exposure_risks(self) -> List[RiskAlert]:
        """检查敞口风险"""
        alerts = []
        
        total_exposure = self.position_monitor.get_total_exposure()
        
        # 检查单交易所敞口
        for exchange in self.position_monitor.positions:
            exchange_exposure = self.position_monitor.get_exchange_exposure(exchange)
            exposure_ratio = exchange_exposure / total_exposure if total_exposure > 0 else 0
            
            if exposure_ratio > self.risk_limits.max_exposure_per_exchange:
                alerts.append(RiskAlert(
                    alert_type=AlertType.EXPOSURE,
                    risk_level=RiskLevel.HIGH,
                    message=f"High exposure to {exchange}: {exposure_ratio:.2%}",
                    timestamp=datetime.utcnow(),
                    exchange=exchange,
                    current_value=exposure_ratio,
                    threshold_value=self.risk_limits.max_exposure_per_exchange,
                    recommended_action="Diversify across exchanges"
                ))
        
        return alerts
    
    async def _check_performance_risks(self) -> List[RiskAlert]:
        """检查性能风险"""
        alerts = []
        
        # 检查日损失
        if self.position_monitor.daily_pnl < -self.risk_limits.max_daily_loss:
            alerts.append(RiskAlert(
                alert_type=AlertType.PERFORMANCE,
                risk_level=RiskLevel.CRITICAL,
                message=f"Daily loss exceeds limit: {self.position_monitor.daily_pnl:.2f}",
                timestamp=datetime.utcnow(),
                current_value=abs(self.position_monitor.daily_pnl),
                threshold_value=self.risk_limits.max_daily_loss,
                recommended_action="Stop trading and review strategy"
            ))
        
        # 检查最大回撤
        if self.position_monitor.max_portfolio_value > 0:
            current_drawdown = (self.position_monitor.max_portfolio_value - self.position_monitor.total_portfolio_value) / self.position_monitor.max_portfolio_value
            
            if current_drawdown > self.risk_limits.max_drawdown:
                alerts.append(RiskAlert(
                    alert_type=AlertType.DRAWDOWN,
                    risk_level=RiskLevel.CRITICAL,
                    message=f"Drawdown exceeds limit: {current_drawdown:.2%}",
                    timestamp=datetime.utcnow(),
                    current_value=current_drawdown,
                    threshold_value=self.risk_limits.max_drawdown,
                    recommended_action="Emergency stop and risk assessment"
                ))
        
        return alerts
    
    async def _check_emergency_stop(self, alerts: List[RiskAlert]):
        """检查是否需要紧急停止"""
        critical_alerts = [alert for alert in alerts if alert.risk_level == RiskLevel.CRITICAL]
        
        if critical_alerts and not self.emergency_stop_triggered:
            self.emergency_stop_triggered = True
            logger.critical(f"Emergency stop triggered due to {len(critical_alerts)} critical alerts")
            
            # 这里可以添加紧急停止逻辑，比如停止所有策略
            await self._trigger_emergency_stop(critical_alerts)
    
    async def _trigger_emergency_stop(self, critical_alerts: List[RiskAlert]):
        """触发紧急停止"""
        logger.critical("Triggering emergency stop procedures")
        
        # 发送紧急通知
        for alert in critical_alerts:
            logger.critical(f"CRITICAL ALERT: {alert.message}")
        
        # 这里可以集成策略停止逻辑
        # await strategy_manager.stop_all_strategies()
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """获取风险摘要"""
        recent_alerts = [alert for alert in self.alerts 
                        if alert.timestamp > datetime.utcnow() - timedelta(hours=24)]
        
        alert_counts = {
            'critical': len([a for a in recent_alerts if a.risk_level == RiskLevel.CRITICAL]),
            'high': len([a for a in recent_alerts if a.risk_level == RiskLevel.HIGH]),
            'medium': len([a for a in recent_alerts if a.risk_level == RiskLevel.MEDIUM]),
            'low': len([a for a in recent_alerts if a.risk_level == RiskLevel.LOW])
        }
        
        return {
            'emergency_stop_active': self.emergency_stop_triggered,
            'total_exposure': self.position_monitor.get_total_exposure(),
            'daily_pnl': self.position_monitor.daily_pnl,
            'alert_counts': alert_counts,
            'risk_limits': {
                'max_position_size': self.risk_limits.max_position_size,
                'max_daily_loss': self.risk_limits.max_daily_loss,
                'max_drawdown': self.risk_limits.max_drawdown,
                'max_volatility': self.risk_limits.max_volatility
            },
            'last_check': datetime.utcnow().isoformat()
        }
    
    def update_risk_limits(self, new_limits: Dict[str, Any]):
        """更新风险限制"""
        for key, value in new_limits.items():
            if hasattr(self.risk_limits, key):
                setattr(self.risk_limits, key, value)
                logger.info(f"Updated risk limit {key} to {value}")
    
    def reset_emergency_stop(self):
        """重置紧急停止状态"""
        self.emergency_stop_triggered = False
        logger.info("Emergency stop reset")

# 全局风险管理器实例
risk_manager: Optional[RiskManager] = None

def get_risk_manager() -> RiskManager:
    """获取风险管理器实例"""
    global risk_manager
    if risk_manager is None:
        risk_manager = RiskManager()
    return risk_manager