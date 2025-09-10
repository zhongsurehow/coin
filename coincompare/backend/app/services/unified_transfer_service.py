from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio
import logging
from collections import defaultdict

from .enhanced_deposit_withdrawal_service import enhanced_deposit_withdrawal_service
from .risk_control_service import risk_control_service
from .notification_service import notification_service

logger = logging.getLogger(__name__)

class TransferType(Enum):
    """转账类型"""
    INTERNAL = "internal"  # 内部转账
    CROSS_EXCHANGE = "cross_exchange"  # 跨交易所转账
    ARBITRAGE = "arbitrage"  # 套利转账
    REBALANCE = "rebalance"  # 再平衡转账

class TransferStatus(Enum):
    """转账状态"""
    PENDING = "pending"
    CALCULATING = "calculating"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class RouteType(Enum):
    """路径类型"""
    DIRECT = "direct"  # 直接转账
    BRIDGE = "bridge"  # 跨链桥
    INTERMEDIATE = "intermediate"  # 中间交易所
    MULTI_HOP = "multi_hop"  # 多跳转账

@dataclass
class TransferRoute:
    """转账路径"""
    route_id: str
    route_type: RouteType
    source_exchange: str
    destination_exchange: str
    currency: str
    amount: Decimal
    estimated_fee: Decimal
    estimated_time: timedelta
    confidence_score: float  # 路径可靠性评分
    steps: List[Dict[str, Any]] = field(default_factory=list)
    risk_level: str = "medium"
    
    @property
    def net_amount(self) -> Decimal:
        """净到账金额"""
        return self.amount - self.estimated_fee
    
    @property
    def fee_rate(self) -> float:
        """手续费率"""
        if self.amount > 0:
            return float(self.estimated_fee / self.amount)
        return 0.0

@dataclass
class TransferRequest:
    """转账请求"""
    user_id: str
    transfer_id: str
    transfer_type: TransferType
    source_exchange: str
    destination_exchange: str
    currency: str
    amount: Decimal
    destination_address: Optional[str] = None
    network: Optional[str] = None
    memo: Optional[str] = None
    priority: str = "normal"  # low, normal, high
    max_fee_rate: Optional[float] = None
    max_time: Optional[timedelta] = None
    auto_execute: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class TransferResult:
    """转账结果"""
    transfer_id: str
    status: TransferStatus
    selected_route: Optional[TransferRoute] = None
    actual_fee: Optional[Decimal] = None
    actual_time: Optional[timedelta] = None
    tx_hashes: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None

@dataclass
class BalanceInfo:
    """余额信息"""
    exchange: str
    currency: str
    available: Decimal
    frozen: Decimal
    total: Decimal
    last_updated: datetime

class UnifiedTransferService:
    """统一转账服务"""
    
    def __init__(self):
        self.active_transfers: Dict[str, TransferRequest] = {}
        self.transfer_results: Dict[str, TransferResult] = {}
        self.exchange_balances: Dict[str, Dict[str, BalanceInfo]] = defaultdict(dict)
        self.route_cache: Dict[str, List[TransferRoute]] = {}
        self.cache_ttl = timedelta(minutes=5)
        
        # 交易所配置
        self.exchange_configs = {
            "binance": {
                "withdrawal_fees": {
                    "BTC": Decimal("0.0005"),
                    "ETH": Decimal("0.005"),
                    "USDT": Decimal("1.0")
                },
                "min_withdrawal": {
                    "BTC": Decimal("0.001"),
                    "ETH": Decimal("0.01"),
                    "USDT": Decimal("10.0")
                },
                "networks": ["BTC", "ETH", "BSC", "TRX"]
            },
            "okx": {
                "withdrawal_fees": {
                    "BTC": Decimal("0.0004"),
                    "ETH": Decimal("0.004"),
                    "USDT": Decimal("0.8")
                },
                "min_withdrawal": {
                    "BTC": Decimal("0.001"),
                    "ETH": Decimal("0.01"),
                    "USDT": Decimal("10.0")
                },
                "networks": ["BTC", "ETH", "BSC", "TRX", "POLYGON"]
            },
            "huobi": {
                "withdrawal_fees": {
                    "BTC": Decimal("0.0006"),
                    "ETH": Decimal("0.006"),
                    "USDT": Decimal("1.2")
                },
                "min_withdrawal": {
                    "BTC": Decimal("0.002"),
                    "ETH": Decimal("0.02"),
                    "USDT": Decimal("20.0")
                },
                "networks": ["BTC", "ETH", "TRX"]
            }
        }
    
    async def calculate_optimal_routes(
        self,
        source_exchange: str,
        destination_exchange: str,
        currency: str,
        amount: Decimal,
        max_routes: int = 5
    ) -> List[TransferRoute]:
        """计算最优转账路径"""
        try:
            cache_key = f"{source_exchange}_{destination_exchange}_{currency}_{amount}"
            
            # 检查缓存
            if cache_key in self.route_cache:
                cached_routes = self.route_cache[cache_key]
                if cached_routes and (datetime.utcnow() - cached_routes[0].steps[0].get('calculated_at', datetime.utcnow())) < self.cache_ttl:
                    return cached_routes[:max_routes]
            
            routes = []
            
            # 1. 直接转账路径
            direct_route = await self._calculate_direct_route(
                source_exchange, destination_exchange, currency, amount
            )
            if direct_route:
                routes.append(direct_route)
            
            # 2. 中间交易所路径
            intermediate_routes = await self._calculate_intermediate_routes(
                source_exchange, destination_exchange, currency, amount
            )
            routes.extend(intermediate_routes)
            
            # 3. 跨链桥路径（如果支持）
            bridge_routes = await self._calculate_bridge_routes(
                source_exchange, destination_exchange, currency, amount
            )
            routes.extend(bridge_routes)
            
            # 按综合评分排序
            routes.sort(key=lambda r: self._calculate_route_score(r), reverse=True)
            
            # 缓存结果
            self.route_cache[cache_key] = routes
            
            return routes[:max_routes]
            
        except Exception as e:
            logger.error(f"计算最优路径失败: {e}")
            return []
    
    async def _calculate_direct_route(
        self,
        source_exchange: str,
        destination_exchange: str,
        currency: str,
        amount: Decimal
    ) -> Optional[TransferRoute]:
        """计算直接转账路径"""
        try:
            if source_exchange == destination_exchange:
                return None
            
            # 检查源交易所是否支持提现到目标交易所
            source_config = self.exchange_configs.get(source_exchange, {})
            dest_config = self.exchange_configs.get(destination_exchange, {})
            
            if not source_config or not dest_config:
                return None
            
            # 找到共同支持的网络
            common_networks = set(source_config.get('networks', [])) & set(dest_config.get('networks', []))
            if not common_networks:
                return None
            
            # 选择最优网络（通常是手续费最低的）
            best_network = min(common_networks, key=lambda n: self._get_network_fee(currency, n))
            
            # 计算手续费
            withdrawal_fee = source_config.get('withdrawal_fees', {}).get(currency, Decimal("0"))
            network_fee = self._get_network_fee(currency, best_network)
            total_fee = withdrawal_fee + network_fee
            
            # 估算时间
            estimated_time = self._estimate_transfer_time(source_exchange, destination_exchange, best_network)
            
            route = TransferRoute(
                route_id=f"direct_{source_exchange}_{destination_exchange}_{best_network}",
                route_type=RouteType.DIRECT,
                source_exchange=source_exchange,
                destination_exchange=destination_exchange,
                currency=currency,
                amount=amount,
                estimated_fee=total_fee,
                estimated_time=estimated_time,
                confidence_score=0.9,
                steps=[
                    {
                        "step": 1,
                        "action": "withdraw",
                        "exchange": source_exchange,
                        "network": best_network,
                        "fee": withdrawal_fee,
                        "calculated_at": datetime.utcnow()
                    },
                    {
                        "step": 2,
                        "action": "deposit",
                        "exchange": destination_exchange,
                        "network": best_network,
                        "fee": network_fee
                    }
                ]
            )
            
            return route
            
        except Exception as e:
            logger.error(f"计算直接路径失败: {e}")
            return None
    
    async def _calculate_intermediate_routes(
        self,
        source_exchange: str,
        destination_exchange: str,
        currency: str,
        amount: Decimal
    ) -> List[TransferRoute]:
        """计算中间交易所路径"""
        routes = []
        
        try:
            # 获取所有可用的中间交易所
            all_exchanges = set(self.exchange_configs.keys())
            intermediate_exchanges = all_exchanges - {source_exchange, destination_exchange}
            
            for intermediate in intermediate_exchanges:
                # 检查是否可以从源到中间，再从中间到目标
                route1 = await self._calculate_direct_route(source_exchange, intermediate, currency, amount)
                if not route1:
                    continue
                
                # 计算中间交易所的净到账金额
                intermediate_amount = route1.net_amount
                
                route2 = await self._calculate_direct_route(intermediate, destination_exchange, currency, intermediate_amount)
                if not route2:
                    continue
                
                # 合并路径
                total_fee = route1.estimated_fee + route2.estimated_fee
                total_time = route1.estimated_time + route2.estimated_time + timedelta(minutes=10)  # 额外处理时间
                
                combined_route = TransferRoute(
                    route_id=f"intermediate_{source_exchange}_{intermediate}_{destination_exchange}",
                    route_type=RouteType.INTERMEDIATE,
                    source_exchange=source_exchange,
                    destination_exchange=destination_exchange,
                    currency=currency,
                    amount=amount,
                    estimated_fee=total_fee,
                    estimated_time=total_time,
                    confidence_score=0.7,  # 中间路径可靠性较低
                    steps=route1.steps + route2.steps,
                    risk_level="high"
                )
                
                routes.append(combined_route)
            
        except Exception as e:
            logger.error(f"计算中间路径失败: {e}")
        
        return routes
    
    async def _calculate_bridge_routes(
        self,
        source_exchange: str,
        destination_exchange: str,
        currency: str,
        amount: Decimal
    ) -> List[TransferRoute]:
        """计算跨链桥路径"""
        # 这里可以集成各种跨链桥的API
        # 目前返回空列表，后续可以扩展
        return []
    
    def _get_network_fee(self, currency: str, network: str) -> Decimal:
        """获取网络手续费"""
        network_fees = {
            "BTC": Decimal("0.0001"),
            "ETH": Decimal("0.002"),
            "BSC": Decimal("0.0005"),
            "TRX": Decimal("1.0"),
            "POLYGON": Decimal("0.001")
        }
        return network_fees.get(network, Decimal("0.001"))
    
    def _estimate_transfer_time(self, source_exchange: str, destination_exchange: str, network: str) -> timedelta:
        """估算转账时间"""
        base_times = {
            "BTC": timedelta(hours=1),
            "ETH": timedelta(minutes=15),
            "BSC": timedelta(minutes=5),
            "TRX": timedelta(minutes=3),
            "POLYGON": timedelta(minutes=2)
        }
        
        base_time = base_times.get(network, timedelta(minutes=30))
        
        # 添加交易所处理时间
        processing_time = timedelta(minutes=10)
        
        return base_time + processing_time
    
    def _calculate_route_score(self, route: TransferRoute) -> float:
        """计算路径综合评分"""
        # 评分因素：手续费率、时间、可靠性
        fee_score = max(0, 1 - route.fee_rate * 10)  # 手续费越低分数越高
        time_score = max(0, 1 - route.estimated_time.total_seconds() / 3600 / 24)  # 时间越短分数越高
        confidence_score = route.confidence_score
        
        # 加权平均
        total_score = (fee_score * 0.4 + time_score * 0.3 + confidence_score * 0.3)
        
        return total_score
    
    async def submit_transfer_request(self, request: TransferRequest) -> TransferResult:
        """提交转账请求"""
        try:
            # 存储请求
            self.active_transfers[request.transfer_id] = request
            
            # 创建初始结果
            result = TransferResult(
                transfer_id=request.transfer_id,
                status=TransferStatus.CALCULATING
            )
            self.transfer_results[request.transfer_id] = result
            
            # 发送状态通知
            await notification_service.send_transaction_notification(
                user_id=request.user_id,
                transaction_id=request.transfer_id,
                transaction_type="transfer",
                status="calculating",
                amount=str(request.amount),
                currency=request.currency
            )
            
            # 异步处理转账
            asyncio.create_task(self._process_transfer(request))
            
            return result
            
        except Exception as e:
            logger.error(f"提交转账请求失败: {e}")
            result = TransferResult(
                transfer_id=request.transfer_id,
                status=TransferStatus.FAILED,
                error_message=str(e)
            )
            self.transfer_results[request.transfer_id] = result
            return result
    
    async def _process_transfer(self, request: TransferRequest):
        """处理转账请求"""
        try:
            result = self.transfer_results[request.transfer_id]
            
            # 1. 计算最优路径
            routes = await self.calculate_optimal_routes(
                request.source_exchange,
                request.destination_exchange,
                request.currency,
                request.amount
            )
            
            if not routes:
                result.status = TransferStatus.FAILED
                result.error_message = "未找到可用的转账路径"
                return
            
            # 2. 选择最优路径
            selected_route = routes[0]
            
            # 检查用户限制条件
            if request.max_fee_rate and selected_route.fee_rate > request.max_fee_rate:
                result.status = TransferStatus.FAILED
                result.error_message = f"手续费率 {selected_route.fee_rate:.4f} 超过限制 {request.max_fee_rate:.4f}"
                return
            
            if request.max_time and selected_route.estimated_time > request.max_time:
                result.status = TransferStatus.FAILED
                result.error_message = f"预估时间 {selected_route.estimated_time} 超过限制 {request.max_time}"
                return
            
            result.selected_route = selected_route
            result.status = TransferStatus.APPROVED
            
            # 发送审批通知
            await notification_service.send_transaction_notification(
                user_id=request.user_id,
                transaction_id=request.transfer_id,
                transaction_type="transfer",
                status="approved",
                amount=str(request.amount),
                currency=request.currency,
                details={
                    "route": selected_route.route_type.value,
                    "estimated_fee": str(selected_route.estimated_fee),
                    "estimated_time": str(selected_route.estimated_time)
                }
            )
            
            # 3. 如果设置了自动执行，则开始执行
            if request.auto_execute:
                await self._execute_transfer(request)
            
        except Exception as e:
            logger.error(f"处理转账请求失败: {e}")
            result = self.transfer_results[request.transfer_id]
            result.status = TransferStatus.FAILED
            result.error_message = str(e)
    
    async def _execute_transfer(self, request: TransferRequest):
        """执行转账"""
        try:
            result = self.transfer_results[request.transfer_id]
            result.status = TransferStatus.EXECUTING
            
            route = result.selected_route
            if not route:
                raise ValueError("未找到选定的转账路径")
            
            start_time = datetime.utcnow()
            tx_hashes = []
            
            # 发送执行通知
            await notification_service.send_transaction_notification(
                user_id=request.user_id,
                transaction_id=request.transfer_id,
                transaction_type="transfer",
                status="executing",
                amount=str(request.amount),
                currency=request.currency
            )
            
            # 执行路径中的每个步骤
            for step in route.steps:
                if step["action"] == "withdraw":
                    # 执行提现
                    tx_hash = await self._execute_withdrawal(
                        exchange=step["exchange"],
                        currency=request.currency,
                        amount=request.amount,
                        network=step["network"],
                        destination_address=request.destination_address
                    )
                    if tx_hash:
                        tx_hashes.append(tx_hash)
                
                elif step["action"] == "deposit":
                    # 监控充值
                    await self._monitor_deposit(
                        exchange=step["exchange"],
                        currency=request.currency,
                        network=step["network"],
                        tx_hash=tx_hashes[-1] if tx_hashes else None
                    )
            
            # 计算实际费用和时间
            end_time = datetime.utcnow()
            actual_time = end_time - start_time
            actual_fee = route.estimated_fee  # 实际应该从交易记录中获取
            
            result.status = TransferStatus.COMPLETED
            result.actual_fee = actual_fee
            result.actual_time = actual_time
            result.tx_hashes = tx_hashes
            result.completed_at = end_time
            
            # 发送完成通知
            await notification_service.send_transaction_notification(
                user_id=request.user_id,
                transaction_id=request.transfer_id,
                transaction_type="transfer",
                status="completed",
                amount=str(request.amount),
                currency=request.currency,
                details={
                    "actual_fee": str(actual_fee),
                    "actual_time": str(actual_time),
                    "tx_hashes": tx_hashes
                }
            )
            
        except Exception as e:
            logger.error(f"执行转账失败: {e}")
            result = self.transfer_results[request.transfer_id]
            result.status = TransferStatus.FAILED
            result.error_message = str(e)
            
            # 发送失败通知
            await notification_service.send_transaction_notification(
                user_id=request.user_id,
                transaction_id=request.transfer_id,
                transaction_type="transfer",
                status="failed",
                amount=str(request.amount),
                currency=request.currency,
                details={"error": str(e)}
            )
    
    async def _execute_withdrawal(self, exchange: str, currency: str, amount: Decimal, network: str, destination_address: str) -> Optional[str]:
        """执行提现"""
        # 这里应该调用具体交易所的API
        # 目前返回模拟的交易哈希
        import uuid
        return f"0x{uuid.uuid4().hex}"
    
    async def _monitor_deposit(self, exchange: str, currency: str, network: str, tx_hash: Optional[str]):
        """监控充值"""
        # 这里应该监控充值状态
        # 目前只是等待一段时间模拟
        await asyncio.sleep(10)
    
    async def get_transfer_status(self, transfer_id: str) -> Optional[TransferResult]:
        """获取转账状态"""
        return self.transfer_results.get(transfer_id)
    
    async def cancel_transfer(self, transfer_id: str, user_id: str) -> bool:
        """取消转账"""
        try:
            if transfer_id not in self.active_transfers:
                return False
            
            request = self.active_transfers[transfer_id]
            if request.user_id != user_id:
                return False
            
            result = self.transfer_results.get(transfer_id)
            if not result or result.status in [TransferStatus.COMPLETED, TransferStatus.FAILED, TransferStatus.CANCELLED]:
                return False
            
            result.status = TransferStatus.CANCELLED
            
            # 发送取消通知
            await notification_service.send_transaction_notification(
                user_id=user_id,
                transaction_id=transfer_id,
                transaction_type="transfer",
                status="cancelled",
                amount=str(request.amount),
                currency=request.currency
            )
            
            return True
            
        except Exception as e:
            logger.error(f"取消转账失败: {e}")
            return False
    
    async def get_balance_overview(self, user_id: str) -> Dict[str, Dict[str, BalanceInfo]]:
        """获取余额概览"""
        # 这里应该从各个交易所获取实时余额
        # 目前返回模拟数据
        return self.exchange_balances
    
    async def suggest_rebalance(self, user_id: str, target_distribution: Dict[str, Dict[str, float]]) -> List[TransferRequest]:
        """建议再平衡操作"""
        suggestions = []
        
        try:
            # 获取当前余额分布
            current_balances = await self.get_balance_overview(user_id)
            
            # 计算需要的转账操作
            for currency, target_dist in target_distribution.items():
                total_balance = sum(
                    balance_info.total 
                    for exchange_balances in current_balances.values() 
                    for curr, balance_info in exchange_balances.items() 
                    if curr == currency
                )
                
                for exchange, target_ratio in target_dist.items():
                    target_amount = total_balance * Decimal(str(target_ratio))
                    current_amount = current_balances.get(exchange, {}).get(currency, BalanceInfo(
                        exchange=exchange, currency=currency, available=Decimal("0"), 
                        frozen=Decimal("0"), total=Decimal("0"), last_updated=datetime.utcnow()
                    )).total
                    
                    diff = target_amount - current_amount
                    
                    if abs(diff) > Decimal("10"):  # 只有差异超过阈值才建议转账
                        if diff > 0:
                            # 需要转入
                            source_exchange = self._find_best_source_exchange(currency, diff, current_balances, exchange)
                            if source_exchange:
                                suggestion = TransferRequest(
                                    user_id=user_id,
                                    transfer_id=f"rebalance_{user_id}_{currency}_{source_exchange}_{exchange}_{int(datetime.utcnow().timestamp())}",
                                    transfer_type=TransferType.REBALANCE,
                                    source_exchange=source_exchange,
                                    destination_exchange=exchange,
                                    currency=currency,
                                    amount=diff
                                )
                                suggestions.append(suggestion)
            
        except Exception as e:
            logger.error(f"生成再平衡建议失败: {e}")
        
        return suggestions
    
    def _find_best_source_exchange(self, currency: str, amount: Decimal, balances: Dict, exclude_exchange: str) -> Optional[str]:
        """找到最佳的源交易所"""
        best_exchange = None
        max_available = Decimal("0")
        
        for exchange, exchange_balances in balances.items():
            if exchange == exclude_exchange:
                continue
            
            balance_info = exchange_balances.get(currency)
            if balance_info and balance_info.available >= amount and balance_info.available > max_available:
                max_available = balance_info.available
                best_exchange = exchange
        
        return best_exchange

# 全局服务实例
unified_transfer_service = UnifiedTransferService()

# 便捷函数
async def calculate_transfer_routes(source_exchange: str, destination_exchange: str, currency: str, amount: Decimal) -> List[TransferRoute]:
    """计算转账路径"""
    return await unified_transfer_service.calculate_optimal_routes(source_exchange, destination_exchange, currency, amount)

async def submit_transfer(request: TransferRequest) -> TransferResult:
    """提交转账请求"""
    return await unified_transfer_service.submit_transfer_request(request)

async def get_transfer_status(transfer_id: str) -> Optional[TransferResult]:
    """获取转账状态"""
    return await unified_transfer_service.get_transfer_status(transfer_id)

async def cancel_transfer(transfer_id: str, user_id: str) -> bool:
    """取消转账"""
    return await unified_transfer_service.cancel_transfer(transfer_id, user_id)