"""提现历史追踪服务

提供提现记录管理、状态跟踪、历史查询等功能。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json

from ..services.logging_service import logging_service
from ..services.notification_service import notification_service
from .risk_control_service import WithdrawalStatus, RiskLevel

logger = logging.getLogger(__name__)


class TransactionType(Enum):
    """交易类型"""
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    INTERNAL_TRANSFER = "internal_transfer"
    EXCHANGE_TRANSFER = "exchange_transfer"


class ProcessingStage(Enum):
    """处理阶段"""
    SUBMITTED = "submitted"  # 已提交
    RISK_CHECK = "risk_check"  # 风控检查
    MANUAL_REVIEW = "manual_review"  # 人工审核
    APPROVED = "approved"  # 已批准
    BROADCASTING = "broadcasting"  # 广播中
    CONFIRMING = "confirming"  # 确认中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class WithdrawalRecord:
    """提现记录"""
    withdrawal_id: str
    user_id: int
    exchange: str
    currency: str
    amount: Decimal
    fee: Decimal
    net_amount: Decimal
    destination_address: str
    network: str
    memo: Optional[str]
    tx_hash: Optional[str]
    status: WithdrawalStatus
    processing_stage: ProcessingStage
    risk_level: RiskLevel
    risk_score: float
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    confirmations: int
    required_confirmations: int
    estimated_completion: Optional[datetime]
    failure_reason: Optional[str]
    reviewer_id: Optional[int]
    review_notes: Optional[str]
    batch_id: Optional[str]
    priority: str
    user_ip: str
    user_agent: str
    additional_data: Dict[str, Any]


@dataclass
class WithdrawalStatistics:
    """提现统计"""
    total_count: int
    total_amount: Decimal
    successful_count: int
    successful_amount: Decimal
    failed_count: int
    failed_amount: Decimal
    pending_count: int
    pending_amount: Decimal
    avg_processing_time: Optional[timedelta]
    success_rate: float
    currencies: Dict[str, Dict[str, Any]]
    daily_stats: List[Dict[str, Any]]


@dataclass
class ProcessingTimeline:
    """处理时间线"""
    stage: ProcessingStage
    timestamp: datetime
    duration: Optional[timedelta]
    operator: Optional[str]
    notes: Optional[str]
    system_info: Dict[str, Any]


class WithdrawalHistoryService:
    """提现历史服务"""
    
    def __init__(self):
        # 模拟数据存储（实际应该使用数据库）
        self.withdrawal_records: Dict[str, WithdrawalRecord] = {}
        self.processing_timelines: Dict[str, List[ProcessingTimeline]] = {}
        self.user_withdrawals: Dict[int, List[str]] = {}  # user_id -> withdrawal_ids
    
    async def create_withdrawal_record(
        self,
        withdrawal_id: str,
        user_id: int,
        exchange: str,
        currency: str,
        amount: Decimal,
        fee: Decimal,
        destination_address: str,
        network: str,
        memo: Optional[str] = None,
        batch_id: Optional[str] = None,
        priority: str = "normal",
        user_ip: str = "",
        user_agent: str = "",
        additional_data: Optional[Dict[str, Any]] = None
    ) -> WithdrawalRecord:
        """创建提现记录"""
        try:
            now = datetime.utcnow()
            
            record = WithdrawalRecord(
                withdrawal_id=withdrawal_id,
                user_id=user_id,
                exchange=exchange,
                currency=currency,
                amount=amount,
                fee=fee,
                net_amount=amount - fee,
                destination_address=destination_address,
                network=network,
                memo=memo,
                tx_hash=None,
                status=WithdrawalStatus.PENDING_REVIEW,
                processing_stage=ProcessingStage.SUBMITTED,
                risk_level=RiskLevel.LOW,
                risk_score=0.0,
                created_at=now,
                updated_at=now,
                completed_at=None,
                confirmations=0,
                required_confirmations=self._get_required_confirmations(network),
                estimated_completion=None,
                failure_reason=None,
                reviewer_id=None,
                review_notes=None,
                batch_id=batch_id,
                priority=priority,
                user_ip=user_ip,
                user_agent=user_agent,
                additional_data=additional_data or {}
            )
            
            # 保存记录
            self.withdrawal_records[withdrawal_id] = record
            
            # 更新用户提现列表
            if user_id not in self.user_withdrawals:
                self.user_withdrawals[user_id] = []
            self.user_withdrawals[user_id].append(withdrawal_id)
            
            # 创建初始时间线
            await self._add_timeline_entry(
                withdrawal_id,
                ProcessingStage.SUBMITTED,
                notes="提现请求已提交",
                system_info={
                    "user_ip": user_ip,
                    "user_agent": user_agent,
                    "priority": priority
                }
            )
            
            # 记录日志
            await logging_service.log_withdrawal_created(
                user_id=user_id,
                withdrawal_id=withdrawal_id,
                currency=currency,
                amount=str(amount),
                destination_address=destination_address,
                network=network
            )
            
            # 发送通知
            await notification_service.send_transaction_notification(
                user_id=user_id,
                transaction_type="withdrawal",
                transaction_id=withdrawal_id,
                status="submitted",
                amount=str(amount),
                currency=currency,
                tx_hash=None,
                confirmations=0
            )
            
            return record
            
        except Exception as e:
            logger.error(f"创建提现记录失败: {e}")
            raise
    
    async def update_withdrawal_status(
        self,
        withdrawal_id: str,
        status: WithdrawalStatus,
        processing_stage: Optional[ProcessingStage] = None,
        tx_hash: Optional[str] = None,
        confirmations: Optional[int] = None,
        failure_reason: Optional[str] = None,
        reviewer_id: Optional[int] = None,
        review_notes: Optional[str] = None,
        operator: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """更新提现状态"""
        try:
            if withdrawal_id not in self.withdrawal_records:
                logger.warning(f"提现记录不存在: {withdrawal_id}")
                return False
            
            record = self.withdrawal_records[withdrawal_id]
            old_status = record.status
            old_stage = record.processing_stage
            
            # 更新记录
            record.status = status
            record.updated_at = datetime.utcnow()
            
            if processing_stage:
                record.processing_stage = processing_stage
            
            if tx_hash:
                record.tx_hash = tx_hash
            
            if confirmations is not None:
                record.confirmations = confirmations
            
            if failure_reason:
                record.failure_reason = failure_reason
            
            if reviewer_id:
                record.reviewer_id = reviewer_id
            
            if review_notes:
                record.review_notes = review_notes
            
            # 如果状态变为完成，设置完成时间
            if status == WithdrawalStatus.COMPLETED and not record.completed_at:
                record.completed_at = datetime.utcnow()
            
            # 更新预估完成时间
            if status in [WithdrawalStatus.PROCESSING, WithdrawalStatus.APPROVED]:
                record.estimated_completion = self._calculate_estimated_completion(
                    record.network, record.confirmations, record.required_confirmations
                )
            
            # 添加时间线条目
            if processing_stage and processing_stage != old_stage:
                await self._add_timeline_entry(
                    withdrawal_id,
                    processing_stage,
                    operator=operator,
                    notes=notes or f"状态更新: {old_status.value} -> {status.value}",
                    system_info={
                        "old_status": old_status.value,
                        "new_status": status.value,
                        "tx_hash": tx_hash,
                        "confirmations": confirmations
                    }
                )
            
            # 记录状态变更日志
            await logging_service.log_withdrawal_status_change(
                withdrawal_id=withdrawal_id,
                old_status=old_status.value,
                new_status=status.value,
                operator=operator,
                notes=notes
            )
            
            # 发送状态更新通知
            await notification_service.send_transaction_notification(
                user_id=record.user_id,
                transaction_type="withdrawal",
                transaction_id=withdrawal_id,
                status=status.value,
                amount=str(record.amount),
                currency=record.currency,
                tx_hash=tx_hash,
                confirmations=confirmations or 0
            )
            
            return True
            
        except Exception as e:
            logger.error(f"更新提现状态失败: {e}")
            return False
    
    async def get_withdrawal_record(self, withdrawal_id: str) -> Optional[WithdrawalRecord]:
        """获取提现记录"""
        return self.withdrawal_records.get(withdrawal_id)
    
    async def get_user_withdrawals(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[List[WithdrawalStatus]] = None,
        currency_filter: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[WithdrawalRecord]:
        """获取用户提现记录"""
        try:
            user_withdrawal_ids = self.user_withdrawals.get(user_id, [])
            records = []
            
            for withdrawal_id in user_withdrawal_ids:
                record = self.withdrawal_records.get(withdrawal_id)
                if not record:
                    continue
                
                # 应用过滤条件
                if status_filter and record.status not in status_filter:
                    continue
                
                if currency_filter and record.currency != currency_filter:
                    continue
                
                if start_date and record.created_at < start_date:
                    continue
                
                if end_date and record.created_at > end_date:
                    continue
                
                records.append(record)
            
            # 按创建时间倒序排序
            records.sort(key=lambda x: x.created_at, reverse=True)
            
            # 应用分页
            return records[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"获取用户提现记录失败: {e}")
            return []
    
    async def get_withdrawal_timeline(self, withdrawal_id: str) -> List[ProcessingTimeline]:
        """获取提现处理时间线"""
        return self.processing_timelines.get(withdrawal_id, [])
    
    async def get_withdrawal_statistics(
        self,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> WithdrawalStatistics:
        """获取提现统计"""
        try:
            # 获取符合条件的记录
            records = []
            
            if user_id:
                user_withdrawal_ids = self.user_withdrawals.get(user_id, [])
                for withdrawal_id in user_withdrawal_ids:
                    record = self.withdrawal_records.get(withdrawal_id)
                    if record:
                        records.append(record)
            else:
                records = list(self.withdrawal_records.values())
            
            # 应用日期过滤
            if start_date:
                records = [r for r in records if r.created_at >= start_date]
            if end_date:
                records = [r for r in records if r.created_at <= end_date]
            
            # 计算统计数据
            total_count = len(records)
            total_amount = sum(r.amount for r in records)
            
            successful_records = [r for r in records if r.status == WithdrawalStatus.COMPLETED]
            successful_count = len(successful_records)
            successful_amount = sum(r.amount for r in successful_records)
            
            failed_records = [r for r in records if r.status == WithdrawalStatus.FAILED]
            failed_count = len(failed_records)
            failed_amount = sum(r.amount for r in failed_records)
            
            pending_records = [r for r in records if r.status in [
                WithdrawalStatus.PENDING_REVIEW,
                WithdrawalStatus.APPROVED,
                WithdrawalStatus.PROCESSING
            ]]
            pending_count = len(pending_records)
            pending_amount = sum(r.amount for r in pending_records)
            
            # 计算平均处理时间
            completed_records = [r for r in successful_records if r.completed_at]
            if completed_records:
                processing_times = [
                    r.completed_at - r.created_at for r in completed_records
                ]
                avg_processing_time = sum(processing_times, timedelta()) / len(processing_times)
            else:
                avg_processing_time = None
            
            # 计算成功率
            success_rate = successful_count / total_count if total_count > 0 else 0.0
            
            # 按币种统计
            currencies = {}
            for record in records:
                currency = record.currency
                if currency not in currencies:
                    currencies[currency] = {
                        "count": 0,
                        "amount": Decimal("0"),
                        "successful_count": 0,
                        "successful_amount": Decimal("0")
                    }
                
                currencies[currency]["count"] += 1
                currencies[currency]["amount"] += record.amount
                
                if record.status == WithdrawalStatus.COMPLETED:
                    currencies[currency]["successful_count"] += 1
                    currencies[currency]["successful_amount"] += record.amount
            
            # 按日统计（最近30天）
            daily_stats = self._calculate_daily_stats(records)
            
            return WithdrawalStatistics(
                total_count=total_count,
                total_amount=total_amount,
                successful_count=successful_count,
                successful_amount=successful_amount,
                failed_count=failed_count,
                failed_amount=failed_amount,
                pending_count=pending_count,
                pending_amount=pending_amount,
                avg_processing_time=avg_processing_time,
                success_rate=success_rate,
                currencies=currencies,
                daily_stats=daily_stats
            )
            
        except Exception as e:
            logger.error(f"获取提现统计失败: {e}")
            raise
    
    async def cancel_withdrawal(
        self,
        withdrawal_id: str,
        operator: Optional[str] = None,
        reason: Optional[str] = None
    ) -> bool:
        """取消提现"""
        try:
            record = self.withdrawal_records.get(withdrawal_id)
            if not record:
                return False
            
            # 只有特定状态可以取消
            if record.status not in [
                WithdrawalStatus.PENDING_REVIEW,
                WithdrawalStatus.APPROVED
            ]:
                logger.warning(f"提现状态不允许取消: {record.status}")
                return False
            
            # 更新状态
            await self.update_withdrawal_status(
                withdrawal_id=withdrawal_id,
                status=WithdrawalStatus.CANCELLED,
                processing_stage=ProcessingStage.CANCELLED,
                failure_reason=reason or "用户取消",
                operator=operator,
                notes=f"提现已取消: {reason or '用户取消'}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"取消提现失败: {e}")
            return False
    
    async def retry_failed_withdrawal(
        self,
        withdrawal_id: str,
        operator: Optional[str] = None
    ) -> bool:
        """重试失败的提现"""
        try:
            record = self.withdrawal_records.get(withdrawal_id)
            if not record:
                return False
            
            if record.status != WithdrawalStatus.FAILED:
                logger.warning(f"只能重试失败的提现: {record.status}")
                return False
            
            # 重置状态
            await self.update_withdrawal_status(
                withdrawal_id=withdrawal_id,
                status=WithdrawalStatus.PENDING_REVIEW,
                processing_stage=ProcessingStage.SUBMITTED,
                failure_reason=None,
                operator=operator,
                notes="重试失败的提现"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"重试提现失败: {e}")
            return False
    
    async def _add_timeline_entry(
        self,
        withdrawal_id: str,
        stage: ProcessingStage,
        operator: Optional[str] = None,
        notes: Optional[str] = None,
        system_info: Optional[Dict[str, Any]] = None
    ):
        """添加时间线条目"""
        if withdrawal_id not in self.processing_timelines:
            self.processing_timelines[withdrawal_id] = []
        
        timeline = self.processing_timelines[withdrawal_id]
        now = datetime.utcnow()
        
        # 计算持续时间
        duration = None
        if timeline:
            last_entry = timeline[-1]
            duration = now - last_entry.timestamp
        
        entry = ProcessingTimeline(
            stage=stage,
            timestamp=now,
            duration=duration,
            operator=operator,
            notes=notes,
            system_info=system_info or {}
        )
        
        timeline.append(entry)
    
    def _get_required_confirmations(self, network: str) -> int:
        """获取所需确认数"""
        confirmations_map = {
            "BTC": 3,
            "ETH": 12,
            "TRX": 20,
            "BSC": 15,
            "POLYGON": 30
        }
        return confirmations_map.get(network, 6)
    
    def _calculate_estimated_completion(
        self,
        network: str,
        current_confirmations: int,
        required_confirmations: int
    ) -> datetime:
        """计算预估完成时间"""
        remaining_confirmations = max(0, required_confirmations - current_confirmations)
        
        # 不同网络的平均出块时间（分钟）
        block_times = {
            "BTC": 10,
            "ETH": 2,
            "TRX": 3,
            "BSC": 3,
            "POLYGON": 2
        }
        
        block_time = block_times.get(network, 5)
        estimated_minutes = remaining_confirmations * block_time
        
        return datetime.utcnow() + timedelta(minutes=estimated_minutes)
    
    def _calculate_daily_stats(self, records: List[WithdrawalRecord]) -> List[Dict[str, Any]]:
        """计算每日统计"""
        daily_stats = {}
        
        for record in records:
            date_key = record.created_at.date()
            
            if date_key not in daily_stats:
                daily_stats[date_key] = {
                    "date": date_key.isoformat(),
                    "count": 0,
                    "amount": Decimal("0"),
                    "successful_count": 0,
                    "successful_amount": Decimal("0")
                }
            
            daily_stats[date_key]["count"] += 1
            daily_stats[date_key]["amount"] += record.amount
            
            if record.status == WithdrawalStatus.COMPLETED:
                daily_stats[date_key]["successful_count"] += 1
                daily_stats[date_key]["successful_amount"] += record.amount
        
        # 转换为列表并排序
        stats_list = list(daily_stats.values())
        stats_list.sort(key=lambda x: x["date"], reverse=True)
        
        # 只返回最近30天
        return stats_list[:30]
    
    async def export_withdrawal_history(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format_type: str = "json"
    ) -> Dict[str, Any]:
        """导出提现历史"""
        try:
            records = await self.get_user_withdrawals(
                user_id=user_id,
                limit=1000,  # 导出限制
                start_date=start_date,
                end_date=end_date
            )
            
            if format_type == "json":
                return {
                    "user_id": user_id,
                    "export_time": datetime.utcnow().isoformat(),
                    "total_records": len(records),
                    "records": [
                        {
                            **asdict(record),
                            "amount": str(record.amount),
                            "fee": str(record.fee),
                            "net_amount": str(record.net_amount),
                            "created_at": record.created_at.isoformat(),
                            "updated_at": record.updated_at.isoformat(),
                            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                            "estimated_completion": record.estimated_completion.isoformat() if record.estimated_completion else None,
                            "status": record.status.value,
                            "processing_stage": record.processing_stage.value,
                            "risk_level": record.risk_level.value
                        }
                        for record in records
                    ]
                }
            
            # 其他格式可以在这里添加
            raise ValueError(f"不支持的导出格式: {format_type}")
            
        except Exception as e:
            logger.error(f"导出提现历史失败: {e}")
            raise


# 全局提现历史服务实例
withdrawal_history_service = WithdrawalHistoryService()


# 便捷函数
async def create_withdrawal_record(**kwargs) -> WithdrawalRecord:
    """创建提现记录"""
    return await withdrawal_history_service.create_withdrawal_record(**kwargs)


async def update_withdrawal_status(**kwargs) -> bool:
    """更新提现状态"""
    return await withdrawal_history_service.update_withdrawal_status(**kwargs)


async def get_withdrawal_record(withdrawal_id: str) -> Optional[WithdrawalRecord]:
    """获取提现记录"""
    return await withdrawal_history_service.get_withdrawal_record(withdrawal_id)


async def get_user_withdrawals(**kwargs) -> List[WithdrawalRecord]:
    """获取用户提现记录"""
    return await withdrawal_history_service.get_user_withdrawals(**kwargs)