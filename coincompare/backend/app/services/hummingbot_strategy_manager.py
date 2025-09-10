from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
import json
import logging
from datetime import datetime, timedelta

from ..models.strategy import Strategy, StrategyType, StrategyStatus
from .hummingbot_client import HummingbotClient, HummingbotManager

logger = logging.getLogger(__name__)

class StrategyTemplate(Enum):
    """预定义的策略模板"""
    PURE_MARKET_MAKING = "pure_market_making"
    CROSS_EXCHANGE_MARKET_MAKING = "cross_exchange_market_making"
    ARBITRAGE = "arbitrage"
    PERPETUAL_MARKET_MAKING = "perpetual_market_making"
    LIQUIDITY_MINING = "liquidity_mining"
    SPOT_PERPETUAL_ARBITRAGE = "spot_perpetual_arbitrage"
    AMMS_ARBITRAGE = "amm_arb"
    UNISWAP_V3_LP = "uniswap_v3_lp"

@dataclass
class StrategyConfig:
    """策略配置数据类"""
    strategy_name: str
    template: StrategyTemplate
    exchange: str
    trading_pair: str
    bid_spread: float = 0.01
    ask_spread: float = 0.01
    order_amount: float = 100.0
    order_levels: int = 1
    order_level_amount: float = 0.0
    order_level_spread: float = 0.01
    inventory_skew_enabled: bool = False
    target_base_pct: float = 50.0
    filled_order_delay: float = 60.0
    hanging_orders_enabled: bool = False
    hanging_orders_cancel_pct: float = 10.0
    order_optimization_enabled: bool = False
    add_transaction_costs: bool = False
    price_ceiling: float = -1
    price_floor: float = -1
    ping_pong_enabled: bool = False
    order_refresh_time: float = 30.0
    max_order_age: float = 1800.0
    order_refresh_tolerance_pct: float = 0.0
    filled_order_replenish_wait_time: float = 10.0
    enable_order_filled_stop_cancellation: bool = False
    best_bid_ask_jump_mode: bool = False
    best_bid_ask_jump_orders_depth: float = 0.0
    add_transaction_costs_to_orders: bool = True
    volatility_interval: int = 300
    avg_volatility_period: int = 10
    volatility_to_spread_multiplier: float = 1.0
    max_spread: float = -1
    max_order_age: float = 1800.0
    
    # 套利策略特定参数
    min_profitability: float = 0.3  # 最小盈利率 (%)
    market_1: str = ""
    market_2: str = ""
    order_amount_1: float = 0.0
    order_amount_2: float = 0.0
    
    # 风险管理参数
    stop_loss_pct: float = -1  # 止损百分比
    take_profit_pct: float = -1  # 止盈百分比
    max_order_size: float = -1  # 最大订单大小
    inventory_target_base_pct: float = 50.0  # 目标基础资产百分比
    
    def to_hummingbot_config(self) -> Dict[str, Any]:
        """转换为Hummingbot配置格式"""
        config = {
            "strategy": self.template.value,
            "exchange": self.exchange,
            "market": self.trading_pair,
            "bid_spread": self.bid_spread,
            "ask_spread": self.ask_spread,
            "order_amount": self.order_amount,
            "order_levels": self.order_levels,
            "order_level_amount": self.order_level_amount,
            "order_level_spread": self.order_level_spread,
            "inventory_skew_enabled": self.inventory_skew_enabled,
            "target_base_pct": self.target_base_pct,
            "filled_order_delay": self.filled_order_delay,
            "hanging_orders_enabled": self.hanging_orders_enabled,
            "hanging_orders_cancel_pct": self.hanging_orders_cancel_pct,
            "order_optimization_enabled": self.order_optimization_enabled,
            "add_transaction_costs": self.add_transaction_costs,
            "order_refresh_time": self.order_refresh_time,
            "max_order_age": self.max_order_age,
            "order_refresh_tolerance_pct": self.order_refresh_tolerance_pct,
            "filled_order_replenish_wait_time": self.filled_order_replenish_wait_time,
            "enable_order_filled_stop_cancellation": self.enable_order_filled_stop_cancellation,
            "best_bid_ask_jump_mode": self.best_bid_ask_jump_mode,
            "best_bid_ask_jump_orders_depth": self.best_bid_ask_jump_orders_depth,
            "add_transaction_costs_to_orders": self.add_transaction_costs_to_orders,
            "volatility_interval": self.volatility_interval,
            "avg_volatility_period": self.avg_volatility_period,
            "volatility_to_spread_multiplier": self.volatility_to_spread_multiplier,
        }
        
        # 添加条件参数
        if self.price_ceiling > 0:
            config["price_ceiling"] = self.price_ceiling
        if self.price_floor > 0:
            config["price_floor"] = self.price_floor
        if self.max_spread > 0:
            config["max_spread"] = self.max_spread
            
        # 套利策略特定参数
        if self.template == StrategyTemplate.ARBITRAGE:
            config.update({
                "min_profitability": self.min_profitability,
                "market_1": self.market_1,
                "market_2": self.market_2,
                "order_amount_1": self.order_amount_1,
                "order_amount_2": self.order_amount_2,
            })
            
        # 风险管理参数
        if self.stop_loss_pct > 0:
            config["stop_loss_pct"] = self.stop_loss_pct
        if self.take_profit_pct > 0:
            config["take_profit_pct"] = self.take_profit_pct
        if self.max_order_size > 0:
            config["max_order_size"] = self.max_order_size
            
        return config

class HummingbotStrategyManager:
    """Hummingbot策略管理器"""
    
    def __init__(self, hummingbot_client: HummingbotClient):
        self.client = hummingbot_client
        self.active_strategies: Dict[str, Strategy] = {}
        self.strategy_configs: Dict[str, StrategyConfig] = {}
        self.performance_data: Dict[str, Dict] = {}
        
    async def create_strategy_from_template(
        self, 
        template: StrategyTemplate, 
        name: str,
        exchange: str,
        trading_pair: str,
        **kwargs
    ) -> StrategyConfig:
        """从模板创建策略配置"""
        
        # 根据模板设置默认参数
        template_defaults = self._get_template_defaults(template)
        
        config = StrategyConfig(
            strategy_name=name,
            template=template,
            exchange=exchange,
            trading_pair=trading_pair,
            **{**template_defaults, **kwargs}
        )
        
        self.strategy_configs[name] = config
        return config
    
    def _get_template_defaults(self, template: StrategyTemplate) -> Dict[str, Any]:
        """获取模板默认参数"""
        defaults = {
            StrategyTemplate.PURE_MARKET_MAKING: {
                "bid_spread": 0.01,
                "ask_spread": 0.01,
                "order_amount": 100.0,
                "order_levels": 1,
                "inventory_skew_enabled": True,
                "filled_order_delay": 60.0,
                "order_refresh_time": 30.0,
            },
            StrategyTemplate.CROSS_EXCHANGE_MARKET_MAKING: {
                "bid_spread": 0.002,
                "ask_spread": 0.002,
                "order_amount": 50.0,
                "order_levels": 1,
                "min_profitability": 0.1,
                "order_refresh_time": 10.0,
            },
            StrategyTemplate.ARBITRAGE: {
                "min_profitability": 0.3,
                "order_amount": 100.0,
                "max_order_age": 300.0,
            },
            StrategyTemplate.PERPETUAL_MARKET_MAKING: {
                "bid_spread": 0.008,
                "ask_spread": 0.008,
                "order_amount": 200.0,
                "leverage": 1,
                "position_mode": "One-way",
            },
            StrategyTemplate.LIQUIDITY_MINING: {
                "bid_spread": 0.01,
                "ask_spread": 0.01,
                "order_amount": 50.0,
                "order_levels": 3,
                "order_level_spread": 0.005,
            },
            StrategyTemplate.SPOT_PERPETUAL_ARBITRAGE: {
                "min_profitability": 0.2,
                "order_amount": 100.0,
                "leverage": 1,
            },
            StrategyTemplate.AMMS_ARBITRAGE: {
                "min_profitability": 0.5,
                "order_amount": 100.0,
                "concurrent_orders_submission": True,
            },
            StrategyTemplate.UNISWAP_V3_LP: {
                "fee_tier": "MEDIUM",
                "price_spread": 0.01,
                "amount": 100.0,
                "min_profitability": 0.1,
            },
        }
        
        return defaults.get(template, {})
    
    async def deploy_strategy(self, strategy_name: str) -> bool:
        """部署策略到Hummingbot"""
        try:
            if strategy_name not in self.strategy_configs:
                raise ValueError(f"Strategy {strategy_name} not found")
            
            config = self.strategy_configs[strategy_name]
            hb_config = config.to_hummingbot_config()
            
            # 创建策略配置文件
            success = await self.client.create_strategy(strategy_name, hb_config)
            
            if success:
                logger.info(f"Strategy {strategy_name} deployed successfully")
                return True
            else:
                logger.error(f"Failed to deploy strategy {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error deploying strategy {strategy_name}: {e}")
            return False
    
    async def start_strategy(self, strategy_name: str) -> bool:
        """启动策略"""
        try:
            success = await self.client.start_strategy(strategy_name)
            
            if success:
                # 更新本地状态
                if strategy_name in self.active_strategies:
                    self.active_strategies[strategy_name].status = StrategyStatus.RUNNING
                
                logger.info(f"Strategy {strategy_name} started successfully")
                return True
            else:
                logger.error(f"Failed to start strategy {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error starting strategy {strategy_name}: {e}")
            return False
    
    async def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略"""
        try:
            success = await self.client.stop_strategy(strategy_name)
            
            if success:
                # 更新本地状态
                if strategy_name in self.active_strategies:
                    self.active_strategies[strategy_name].status = StrategyStatus.STOPPED
                
                logger.info(f"Strategy {strategy_name} stopped successfully")
                return True
            else:
                logger.error(f"Failed to stop strategy {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error stopping strategy {strategy_name}: {e}")
            return False
    
    async def get_strategy_status(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """获取策略状态"""
        try:
            status = await self.client.get_strategy_status(strategy_name)
            return status
        except Exception as e:
            logger.error(f"Error getting strategy status for {strategy_name}: {e}")
            return None
    
    async def get_strategy_performance(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """获取策略性能数据"""
        try:
            performance = await self.client.get_performance_data(strategy_name)
            
            if performance:
                self.performance_data[strategy_name] = performance
            
            return performance
        except Exception as e:
            logger.error(f"Error getting strategy performance for {strategy_name}: {e}")
            return None
    
    async def update_strategy_config(
        self, 
        strategy_name: str, 
        config_updates: Dict[str, Any]
    ) -> bool:
        """更新策略配置"""
        try:
            if strategy_name not in self.strategy_configs:
                raise ValueError(f"Strategy {strategy_name} not found")
            
            # 更新本地配置
            config = self.strategy_configs[strategy_name]
            for key, value in config_updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            # 如果策略正在运行，需要重新部署
            status = await self.get_strategy_status(strategy_name)
            if status and status.get('is_running', False):
                await self.stop_strategy(strategy_name)
                await asyncio.sleep(2)  # 等待策略完全停止
                await self.deploy_strategy(strategy_name)
                await self.start_strategy(strategy_name)
            else:
                await self.deploy_strategy(strategy_name)
            
            logger.info(f"Strategy {strategy_name} configuration updated")
            return True
            
        except Exception as e:
            logger.error(f"Error updating strategy config for {strategy_name}: {e}")
            return False
    
    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        """获取所有策略信息"""
        try:
            strategies = await self.client.list_strategies()
            return strategies or []
        except Exception as e:
            logger.error(f"Error getting all strategies: {e}")
            return []
    
    async def delete_strategy(self, strategy_name: str) -> bool:
        """删除策略"""
        try:
            # 先停止策略
            await self.stop_strategy(strategy_name)
            
            # 删除策略配置
            success = await self.client.delete_strategy(strategy_name)
            
            if success:
                # 清理本地数据
                self.strategy_configs.pop(strategy_name, None)
                self.active_strategies.pop(strategy_name, None)
                self.performance_data.pop(strategy_name, None)
                
                logger.info(f"Strategy {strategy_name} deleted successfully")
                return True
            else:
                logger.error(f"Failed to delete strategy {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting strategy {strategy_name}: {e}")
            return False
    
    async def optimize_strategy(
        self, 
        strategy_name: str, 
        optimization_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """策略优化"""
        try:
            # 获取历史性能数据
            performance = await self.get_strategy_performance(strategy_name)
            
            if not performance:
                raise ValueError("No performance data available for optimization")
            
            # 基于性能数据进行参数优化
            optimized_params = self._optimize_parameters(
                performance, 
                optimization_params
            )
            
            # 应用优化后的参数
            await self.update_strategy_config(strategy_name, optimized_params)
            
            return {
                "strategy_name": strategy_name,
                "optimized_params": optimized_params,
                "optimization_timestamp": datetime.utcnow().isoformat(),
                "performance_improvement_estimate": self._estimate_improvement(
                    performance, optimized_params
                )
            }
            
        except Exception as e:
            logger.error(f"Error optimizing strategy {strategy_name}: {e}")
            return {}
    
    def _optimize_parameters(
        self, 
        performance: Dict[str, Any], 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于性能数据优化参数"""
        optimized = {}
        
        # 获取关键性能指标
        total_pnl = performance.get('total_pnl', 0)
        win_rate = performance.get('win_rate', 0)
        avg_profit = performance.get('avg_profit', 0)
        max_drawdown = performance.get('max_drawdown', 0)
        
        # 基于盈利情况调整spread
        if 'bid_spread' in params and 'ask_spread' in params:
            if total_pnl > 0 and win_rate > 0.6:
                # 表现良好，可以适当降低spread增加成交量
                optimized['bid_spread'] = max(params['bid_spread'] * 0.9, 0.001)
                optimized['ask_spread'] = max(params['ask_spread'] * 0.9, 0.001)
            elif total_pnl < 0 or win_rate < 0.4:
                # 表现不佳，增加spread提高盈利率
                optimized['bid_spread'] = params['bid_spread'] * 1.1
                optimized['ask_spread'] = params['ask_spread'] * 1.1
        
        # 基于最大回撤调整订单大小
        if 'order_amount' in params:
            if max_drawdown > 0.1:  # 回撤超过10%
                optimized['order_amount'] = params['order_amount'] * 0.8
            elif max_drawdown < 0.05:  # 回撤小于5%
                optimized['order_amount'] = params['order_amount'] * 1.1
        
        # 基于成交情况调整刷新时间
        if 'order_refresh_time' in params:
            fill_rate = performance.get('fill_rate', 0)
            if fill_rate > 0.8:
                # 成交率高，可以延长刷新时间
                optimized['order_refresh_time'] = min(params['order_refresh_time'] * 1.2, 300)
            elif fill_rate < 0.3:
                # 成交率低，缩短刷新时间
                optimized['order_refresh_time'] = max(params['order_refresh_time'] * 0.8, 10)
        
        return optimized
    
    def _estimate_improvement(
        self, 
        performance: Dict[str, Any], 
        optimized_params: Dict[str, Any]
    ) -> float:
        """估算优化后的性能改进"""
        # 简单的改进估算逻辑
        base_score = performance.get('total_pnl', 0) * performance.get('win_rate', 0)
        
        # 基于参数变化估算改进
        improvement_factor = 1.0
        
        for param, value in optimized_params.items():
            if 'spread' in param:
                # spread降低通常能增加成交量
                improvement_factor *= 1.05
            elif param == 'order_amount':
                # 订单大小优化能改善风险收益比
                improvement_factor *= 1.03
        
        return (improvement_factor - 1.0) * 100  # 返回百分比改进

# 全局策略管理器实例
strategy_manager: Optional[HummingbotStrategyManager] = None

def get_strategy_manager() -> HummingbotStrategyManager:
    """获取策略管理器实例"""
    global strategy_manager
    if strategy_manager is None:
        from .hummingbot_client import get_hummingbot_client
        client = get_hummingbot_client()
        strategy_manager = HummingbotStrategyManager(client)
    return strategy_manager