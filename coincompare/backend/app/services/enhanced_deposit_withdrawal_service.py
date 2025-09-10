"""增强的充值提现服务

提供实时状态监控、手续费计算、到账时间预估等功能。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_async_session
from ..models.deposit_withdrawal import DepositWithdrawal, TransactionStatus
from ..services.exchange_service import exchange_service
from ..services.notification_service import notification_service
from ..services.logging_service import logging_service
from ..core.config import settings

logger = logging.getLogger(__name__)


class NetworkStatus(Enum):
    """网络状态枚举"""
    NORMAL = "normal"
    CONGESTED = "congested"
    MAINTENANCE = "maintenance"
    SUSPENDED = "suspended"


@dataclass
class FeeCalculation:
    """手续费计算结果"""
    network_fee: Decimal
    exchange_fee: Decimal
    total_fee: Decimal
    estimated_arrival_time: datetime
    confidence_level: float  # 0-1之间，表示预估的可信度


@dataclass
class TransactionMonitoring:
    """交易监控信息"""
    transaction_id: str
    current_status: TransactionStatus
    confirmations: int
    required_confirmations: int
    estimated_completion: datetime
    last_updated: datetime
    blockchain_url: Optional[str] = None


@dataclass
class NetworkInfo:
    """网络信息"""
    name: str
    status: NetworkStatus
    avg_confirmation_time: timedelta
    current_congestion: float  # 0-1之间，0表示无拥堵
    fee_multiplier: float  # 费用倍数
    min_confirmations: int
    max_confirmations: int


class EnhancedDepositWithdrawalService:
    """增强的充值提现服务"""
    
    def __init__(self):
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.network_cache: Dict[str, NetworkInfo] = {}
        self.fee_cache: Dict[str, FeeCalculation] = {}
        self.cache_ttl = 300  # 5分钟缓存
        
    async def start_monitoring(self):
        """启动监控服务"""
        logger.info("启动增强充值提现监控服务")
        
        # 启动网络状态监控
        asyncio.create_task(self._monitor_network_status())
        
        # 启动交易状态监控
        asyncio.create_task(self._monitor_pending_transactions())
        
        # 启动费用更新
        asyncio.create_task(self._update_fee_estimates())
    
    async def calculate_withdrawal_fee(
        self,
        user_id: int,
        exchange: str,
        currency: str,
        network: str,
        amount: Decimal
    ) -> FeeCalculation:
        """计算提现手续费"""
        cache_key = f"{exchange}:{currency}:{network}:{amount}"
        
        # 检查缓存
        if cache_key in self.fee_cache:
            cached_fee = self.fee_cache[cache_key]
            if (datetime.now() - cached_fee.estimated_arrival_time).seconds < self.cache_ttl:
                return cached_fee
        
        try:
            # 获取网络信息
            network_info = await self._get_network_info(network)
            
            # 获取交易所基础费用
            base_fee = await exchange_service.get_withdrawal_fee(
                exchange, currency, network
            )
            
            # 计算网络费用（考虑拥堵情况）
            network_fee = Decimal(str(base_fee.get('network_fee', 0))) * Decimal(str(network_info.fee_multiplier))
            
            # 交易所手续费
            exchange_fee = Decimal(str(base_fee.get('exchange_fee', 0)))
            
            # 总费用
            total_fee = network_fee + exchange_fee
            
            # 预估到账时间
            base_time = datetime.now()
            estimated_time = base_time + network_info.avg_confirmation_time
            
            # 根据网络拥堵调整时间
            if network_info.current_congestion > 0.7:
                estimated_time += timedelta(hours=2)
            elif network_info.current_congestion > 0.5:
                estimated_time += timedelta(hours=1)
            
            # 计算可信度
            confidence = self._calculate_confidence(
                network_info.status,
                network_info.current_congestion
            )
            
            fee_calc = FeeCalculation(
                network_fee=network_fee,
                exchange_fee=exchange_fee,
                total_fee=total_fee,
                estimated_arrival_time=estimated_time,
                confidence_level=confidence
            )
            
            # 缓存结果
            self.fee_cache[cache_key] = fee_calc
            
            return fee_calc
            
        except Exception as e:
            logger.error(f"计算提现手续费失败: {e}")
            raise
    
    async def estimate_arrival_time(
        self,
        user_id: int,
        exchange: str,
        currency: str,
        network: str,
        tx_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """预估充值到账时间"""
        try:
            network_info = await self._get_network_info(network)
            
            # 基础预估时间
            base_time = datetime.now()
            estimated_time = base_time + network_info.avg_confirmation_time
            
            # 如果有交易哈希，获取当前确认数
            current_confirmations = 0
            if tx_hash:
                current_confirmations = await self._get_transaction_confirmations(
                    tx_hash, network
                )
            
            # 计算剩余确认数
            required_confirmations = await exchange_service.get_required_confirmations(
                exchange, currency, network
            )
            
            remaining_confirmations = max(0, required_confirmations - current_confirmations)
            
            # 根据剩余确认数调整时间
            if remaining_confirmations > 0:
                avg_block_time = network_info.avg_confirmation_time / network_info.min_confirmations
                estimated_time = base_time + (avg_block_time * remaining_confirmations)
            
            # 考虑网络拥堵
            if network_info.current_congestion > 0.7:
                estimated_time += timedelta(hours=1)
            elif network_info.current_congestion > 0.5:
                estimated_time += timedelta(minutes=30)
            
            return {
                "estimated_arrival": estimated_time,
                "current_confirmations": current_confirmations,
                "required_confirmations": required_confirmations,
                "network_status": network_info.status.value,
                "confidence_level": self._calculate_confidence(
                    network_info.status,
                    network_info.current_congestion
                )
            }
            
        except Exception as e:
            logger.error(f"预估充值到账时间失败: {e}")
            raise
    
    async def monitor_transaction(
        self,
        user_id: int,
        transaction_id: str,
        tx_hash: str,
        network: str
    ):
        """开始监控交易状态"""
        if transaction_id in self.monitoring_tasks:
            # 如果已经在监控，先取消
            self.monitoring_tasks[transaction_id].cancel()
        
        # 创建新的监控任务
        task = asyncio.create_task(
            self._monitor_transaction(
                transaction_id, tx_hash, network, user_id
            )
        )
        self.monitoring_tasks[transaction_id] = task
        
        logger.info(f"开始监控交易: {transaction_id}")
    
    async def stop_transaction_monitoring(self, transaction_id: str):
        """停止监控交易"""
        if transaction_id in self.monitoring_tasks:
            self.monitoring_tasks[transaction_id].cancel()
            del self.monitoring_tasks[transaction_id]
            logger.info(f"停止监控交易: {transaction_id}")
    
    async def get_real_time_status(
        self,
        user_id: int,
        transaction_id: str
    ) -> Optional[TransactionMonitoring]:
        """获取实时交易状态"""
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(DepositWithdrawal).where(
                        DepositWithdrawal.id == transaction_id
                    )
                )
                transaction = result.scalar_one_or_none()
                
                if not transaction:
                    return None
                
                # 获取最新确认数
                current_confirmations = 0
                if transaction.tx_hash:
                    current_confirmations = await self._get_transaction_confirmations(
                        transaction.tx_hash, transaction.network
                    )
                
                # 更新预估完成时间
                estimated_completion = await self._calculate_estimated_completion(
                    transaction, current_confirmations
                )
                
                return TransactionMonitoring(
                    transaction_id=transaction_id,
                    current_status=transaction.status,
                    confirmations=current_confirmations,
                    required_confirmations=transaction.required_confirmations or 6,
                    estimated_completion=estimated_completion,
                    last_updated=datetime.now(),
                    blockchain_url=self._get_blockchain_url(
                        transaction.tx_hash, transaction.network
                    )
                )
                
        except Exception as e:
            logger.error(f"获取实时交易状态失败: {e}")
            return None
    
    async def _monitor_network_status(self):
        """监控网络状态"""
        while True:
            try:
                # 更新主要网络状态
                networks = ['BTC', 'ETH', 'BSC', 'TRX', 'POLYGON']
                
                for network in networks:
                    network_info = await self._fetch_network_status(network)
                    self.network_cache[network] = network_info
                
                await asyncio.sleep(60)  # 每分钟更新一次
                
            except Exception as e:
                logger.error(f"网络状态监控错误: {e}")
                await asyncio.sleep(60)
    
    async def _monitor_pending_transactions(self):
        """监控待处理交易"""
        while True:
            try:
                async with get_async_session() as session:
                    # 查询待处理的交易
                    result = await session.execute(
                        select(DepositWithdrawal).where(
                            and_(
                                DepositWithdrawal.status.in_([
                                    TransactionStatus.PENDING,
                                    TransactionStatus.CONFIRMING
                                ]),
                                DepositWithdrawal.tx_hash.isnot(None)
                            )
                        )
                    )
                    
                    pending_transactions = result.scalars().all()
                    
                    for transaction in pending_transactions:
                        # 检查是否已在监控
                        if transaction.id not in self.monitoring_tasks:
                            await self.start_transaction_monitoring(
                                transaction.id,
                                transaction.tx_hash,
                                transaction.network,
                                transaction.user_id
                            )
                
                await asyncio.sleep(30)  # 每30秒检查一次
                
            except Exception as e:
                logger.error(f"待处理交易监控错误: {e}")
                await asyncio.sleep(30)
    
    async def _monitor_transaction(
        self,
        transaction_id: str,
        tx_hash: str,
        network: str,
        user_id: int
    ):
        """监控单个交易"""
        try:
            while True:
                # 获取当前确认数
                confirmations = await self._get_transaction_confirmations(
                    tx_hash, network
                )
                
                # 更新数据库
                async with get_async_session() as session:
                    await session.execute(
                        update(DepositWithdrawal)
                        .where(DepositWithdrawal.id == transaction_id)
                        .values(
                            confirmations=confirmations,
                            updated_at=datetime.now()
                        )
                    )
                    await session.commit()
                
                # 检查是否完成
                result = await session.execute(
                    select(DepositWithdrawal).where(
                        DepositWithdrawal.id == transaction_id
                    )
                )
                transaction = result.scalar_one_or_none()
                
                if not transaction:
                    break
                
                required_confirmations = transaction.required_confirmations or 6
                
                if confirmations >= required_confirmations:
                    # 交易完成
                    await session.execute(
                        update(DepositWithdrawal)
                        .where(DepositWithdrawal.id == transaction_id)
                        .values(
                            status=TransactionStatus.COMPLETED,
                            completed_at=datetime.now()
                        )
                    )
                    await session.commit()
                    
                    # 发送通知
                    await notification_service.send_transaction_notification(
                        user_id=user_id,
                        transaction_type=transaction.transaction_type.value if hasattr(transaction.transaction_type, 'value') else str(transaction.transaction_type),
                        currency=transaction.currency,
                        amount=float(transaction.amount),
                        status="completed",
                        tx_hash=tx_hash,
                        confirmations=confirmations
                    )
                    
                    # 记录日志
                    await logging_service.log_transaction_completion(
                        transaction_id=transaction_id,
                        confirmations=confirmations
                    )
                    
                    break
                
                await asyncio.sleep(30)  # 每30秒检查一次
                
        except asyncio.CancelledError:
            logger.info(f"交易监控已取消: {transaction_id}")
        except Exception as e:
            logger.error(f"交易监控错误 {transaction_id}: {e}")
        finally:
            # 清理监控任务
            if transaction_id in self.monitoring_tasks:
                del self.monitoring_tasks[transaction_id]
    
    async def _update_fee_estimates(self):
        """更新手续费预估"""
        while True:
            try:
                # 清理过期缓存
                current_time = datetime.now()
                expired_keys = [
                    key for key, fee_calc in self.fee_cache.items()
                    if (current_time - fee_calc.estimated_arrival_time).seconds > self.cache_ttl
                ]
                
                for key in expired_keys:
                    del self.fee_cache[key]
                
                await asyncio.sleep(300)  # 每5分钟清理一次
                
            except Exception as e:
                logger.error(f"手续费缓存更新错误: {e}")
                await asyncio.sleep(300)
    
    async def _get_network_info(self, network: str) -> NetworkInfo:
        """获取网络信息"""
        if network in self.network_cache:
            return self.network_cache[network]
        
        # 如果缓存中没有，获取默认值
        return await self._fetch_network_status(network)
    
    async def _fetch_network_status(self, network: str) -> NetworkInfo:
        """获取网络状态"""
        # 这里应该调用实际的区块链API
        # 暂时返回模拟数据
        network_configs = {
            'BTC': NetworkInfo(
                name='Bitcoin',
                status=NetworkStatus.NORMAL,
                avg_confirmation_time=timedelta(minutes=60),
                current_congestion=0.3,
                fee_multiplier=1.0,
                min_confirmations=1,
                max_confirmations=6
            ),
            'ETH': NetworkInfo(
                name='Ethereum',
                status=NetworkStatus.NORMAL,
                avg_confirmation_time=timedelta(minutes=15),
                current_congestion=0.5,
                fee_multiplier=1.2,
                min_confirmations=12,
                max_confirmations=35
            ),
            'BSC': NetworkInfo(
                name='Binance Smart Chain',
                status=NetworkStatus.NORMAL,
                avg_confirmation_time=timedelta(minutes=3),
                current_congestion=0.2,
                fee_multiplier=1.0,
                min_confirmations=15,
                max_confirmations=30
            )
        }
        
        return network_configs.get(network, NetworkInfo(
            name=network,
            status=NetworkStatus.NORMAL,
            avg_confirmation_time=timedelta(minutes=30),
            current_congestion=0.3,
            fee_multiplier=1.0,
            min_confirmations=6,
            max_confirmations=20
        ))
    
    async def _get_transaction_confirmations(
        self,
        tx_hash: str,
        network: str
    ) -> int:
        """获取交易确认数"""
        # 这里应该调用实际的区块链API
        # 暂时返回模拟数据
        import random
        return random.randint(0, 20)
    
    async def _calculate_estimated_completion(
        self,
        transaction: DepositWithdrawal,
        current_confirmations: int
    ) -> datetime:
        """计算预估完成时间"""
        required_confirmations = transaction.required_confirmations or 6
        remaining_confirmations = max(0, required_confirmations - current_confirmations)
        
        if remaining_confirmations == 0:
            return datetime.now()
        
        network_info = await self._get_network_info(transaction.network)
        avg_block_time = network_info.avg_confirmation_time / network_info.min_confirmations
        
        return datetime.now() + (avg_block_time * remaining_confirmations)
    
    def _get_blockchain_url(self, tx_hash: str, network: str) -> Optional[str]:
        """获取区块链浏览器URL"""
        if not tx_hash:
            return None
        
        urls = {
            'BTC': f'https://blockstream.info/tx/{tx_hash}',
            'ETH': f'https://etherscan.io/tx/{tx_hash}',
            'BSC': f'https://bscscan.com/tx/{tx_hash}',
            'TRX': f'https://tronscan.org/#/transaction/{tx_hash}',
            'POLYGON': f'https://polygonscan.com/tx/{tx_hash}'
        }
        
        return urls.get(network)
    
    def _calculate_confidence(
        self,
        network_status: NetworkStatus,
        congestion: float
    ) -> float:
        """计算预估可信度"""
        base_confidence = 0.9
        
        # 根据网络状态调整
        if network_status == NetworkStatus.MAINTENANCE:
            base_confidence *= 0.5
        elif network_status == NetworkStatus.CONGESTED:
            base_confidence *= 0.7
        elif network_status == NetworkStatus.SUSPENDED:
            base_confidence *= 0.3
        
        # 根据拥堵程度调整
        congestion_penalty = congestion * 0.3
        base_confidence *= (1 - congestion_penalty)
        
        return max(0.1, min(1.0, base_confidence))


# 全局服务实例
enhanced_deposit_withdrawal_service = EnhancedDepositWithdrawalService()