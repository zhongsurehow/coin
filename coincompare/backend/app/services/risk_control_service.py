"""风控服务

提供提现风控检查、风险评估、异常检测等功能。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from ..services.logging_service import logging_service
from ..services.notification_service import notification_service

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskType(Enum):
    """风险类型"""
    AMOUNT_LIMIT = "amount_limit"  # 金额限制
    FREQUENCY_LIMIT = "frequency_limit"  # 频率限制
    SUSPICIOUS_ADDRESS = "suspicious_address"  # 可疑地址
    UNUSUAL_PATTERN = "unusual_pattern"  # 异常模式
    BLACKLIST = "blacklist"  # 黑名单
    COMPLIANCE = "compliance"  # 合规检查
    BALANCE_INSUFFICIENT = "balance_insufficient"  # 余额不足
    NETWORK_CONGESTION = "network_congestion"  # 网络拥堵


class WithdrawalStatus(Enum):
    """提现状态"""
    PENDING_REVIEW = "pending_review"  # 待审核
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class RiskCheckResult:
    """风险检查结果"""
    risk_level: RiskLevel
    risk_types: List[RiskType]
    risk_score: float  # 0-100
    is_approved: bool
    rejection_reason: Optional[str]
    required_actions: List[str]
    additional_verification: bool
    estimated_review_time: Optional[timedelta]
    details: Dict[str, Any]


@dataclass
class WithdrawalRequest:
    """提现请求"""
    user_id: int
    exchange: str
    currency: str
    amount: Decimal
    destination_address: str
    network: str
    memo: Optional[str]
    user_ip: str
    user_agent: str
    request_time: datetime
    two_fa_code: Optional[str]
    withdrawal_password: Optional[str]


@dataclass
class BatchWithdrawalRequest:
    """批量提现请求"""
    user_id: int
    withdrawals: List[WithdrawalRequest]
    total_amount: Decimal
    currency: str
    batch_id: str
    priority: str  # normal, high, urgent


class RiskControlService:
    """风控服务"""
    
    def __init__(self):
        self.daily_limits = {
            "BTC": Decimal("10"),
            "ETH": Decimal("100"),
            "USDT": Decimal("50000")
        }
        self.single_limits = {
            "BTC": Decimal("5"),
            "ETH": Decimal("50"),
            "USDT": Decimal("20000")
        }
        self.frequency_limits = {
            "hourly": 5,
            "daily": 20
        }
        
        # 黑名单地址（示例）
        self.blacklist_addresses = set([
            "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # 示例地址
        ])
        
        # 可疑地址模式
        self.suspicious_patterns = [
            r"^1[A-Za-z0-9]{25,34}$",  # 示例比特币地址模式
        ]
    
    async def check_withdrawal_risk(
        self,
        request: WithdrawalRequest
    ) -> RiskCheckResult:
        """检查提现风险"""
        try:
            risk_types = []
            risk_score = 0.0
            details = {}
            
            # 1. 金额限制检查
            amount_risk = await self._check_amount_limits(request)
            if amount_risk:
                risk_types.extend(amount_risk["types"])
                risk_score += amount_risk["score"]
                details.update(amount_risk["details"])
            
            # 2. 频率限制检查
            frequency_risk = await self._check_frequency_limits(request)
            if frequency_risk:
                risk_types.extend(frequency_risk["types"])
                risk_score += frequency_risk["score"]
                details.update(frequency_risk["details"])
            
            # 3. 地址安全检查
            address_risk = await self._check_address_security(request)
            if address_risk:
                risk_types.extend(address_risk["types"])
                risk_score += address_risk["score"]
                details.update(address_risk["details"])
            
            # 4. 用户行为模式检查
            behavior_risk = await self._check_user_behavior(request)
            if behavior_risk:
                risk_types.extend(behavior_risk["types"])
                risk_score += behavior_risk["score"]
                details.update(behavior_risk["details"])
            
            # 5. 余额检查
            balance_risk = await self._check_balance_sufficiency(request)
            if balance_risk:
                risk_types.extend(balance_risk["types"])
                risk_score += balance_risk["score"]
                details.update(balance_risk["details"])
            
            # 6. 网络状态检查
            network_risk = await self._check_network_status(request)
            if network_risk:
                risk_types.extend(network_risk["types"])
                risk_score += network_risk["score"]
                details.update(network_risk["details"])
            
            # 确定风险等级
            risk_level = self._calculate_risk_level(risk_score)
            
            # 确定是否批准
            is_approved, rejection_reason = self._determine_approval(
                risk_level, risk_types, request
            )
            
            # 确定所需操作
            required_actions = self._determine_required_actions(
                risk_level, risk_types
            )
            
            # 是否需要额外验证
            additional_verification = risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
            
            # 预估审核时间
            estimated_review_time = self._estimate_review_time(risk_level)
            
            result = RiskCheckResult(
                risk_level=risk_level,
                risk_types=risk_types,
                risk_score=risk_score,
                is_approved=is_approved,
                rejection_reason=rejection_reason,
                required_actions=required_actions,
                additional_verification=additional_verification,
                estimated_review_time=estimated_review_time,
                details=details
            )
            
            # 记录风控检查日志
            await logging_service.log_risk_check(
                user_id=request.user_id,
                check_type="withdrawal",
                risk_level=risk_level.value,
                risk_score=risk_score,
                is_approved=is_approved,
                details={
                    "currency": request.currency,
                    "amount": str(request.amount),
                    "destination_address": request.destination_address,
                    "risk_types": [rt.value for rt in risk_types]
                }
            )
            
            # 高风险情况发送通知
            if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                await notification_service.send_risk_alert(
                    user_id=request.user_id,
                    risk_type="withdrawal_risk",
                    risk_level=risk_level.value,
                    message=f"检测到高风险提现请求：{request.currency} {request.amount}",
                    details=details
                )
            
            return result
            
        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            # 默认拒绝
            return RiskCheckResult(
                risk_level=RiskLevel.CRITICAL,
                risk_types=[RiskType.COMPLIANCE],
                risk_score=100.0,
                is_approved=False,
                rejection_reason="系统错误，请稍后重试",
                required_actions=["联系客服"],
                additional_verification=True,
                estimated_review_time=timedelta(hours=24),
                details={"error": str(e)}
            )
    
    async def _check_amount_limits(self, request: WithdrawalRequest) -> Optional[Dict]:
        """检查金额限制"""
        currency = request.currency
        amount = request.amount
        
        risk_types = []
        score = 0.0
        details = {}
        
        # 检查单笔限额
        single_limit = self.single_limits.get(currency, Decimal("0"))
        if amount > single_limit:
            risk_types.append(RiskType.AMOUNT_LIMIT)
            score += 30.0
            details["single_limit_exceeded"] = {
                "limit": str(single_limit),
                "requested": str(amount),
                "excess": str(amount - single_limit)
            }
        
        # 检查日限额（需要查询当日已提现金额）
        daily_limit = self.daily_limits.get(currency, Decimal("0"))
        daily_withdrawn = await self._get_daily_withdrawn_amount(
            request.user_id, currency
        )
        
        if daily_withdrawn + amount > daily_limit:
            risk_types.append(RiskType.AMOUNT_LIMIT)
            score += 25.0
            details["daily_limit_exceeded"] = {
                "limit": str(daily_limit),
                "already_withdrawn": str(daily_withdrawn),
                "requested": str(amount),
                "total_would_be": str(daily_withdrawn + amount)
            }
        
        if risk_types:
            return {
                "types": risk_types,
                "score": score,
                "details": details
            }
        
        return None
    
    async def _check_frequency_limits(self, request: WithdrawalRequest) -> Optional[Dict]:
        """检查频率限制"""
        user_id = request.user_id
        
        # 检查小时频率
        hourly_count = await self._get_withdrawal_count(
            user_id, timedelta(hours=1)
        )
        
        # 检查日频率
        daily_count = await self._get_withdrawal_count(
            user_id, timedelta(days=1)
        )
        
        risk_types = []
        score = 0.0
        details = {}
        
        if hourly_count >= self.frequency_limits["hourly"]:
            risk_types.append(RiskType.FREQUENCY_LIMIT)
            score += 20.0
            details["hourly_limit_exceeded"] = {
                "limit": self.frequency_limits["hourly"],
                "current_count": hourly_count
            }
        
        if daily_count >= self.frequency_limits["daily"]:
            risk_types.append(RiskType.FREQUENCY_LIMIT)
            score += 15.0
            details["daily_limit_exceeded"] = {
                "limit": self.frequency_limits["daily"],
                "current_count": daily_count
            }
        
        if risk_types:
            return {
                "types": risk_types,
                "score": score,
                "details": details
            }
        
        return None
    
    async def _check_address_security(self, request: WithdrawalRequest) -> Optional[Dict]:
        """检查地址安全性"""
        address = request.destination_address
        
        risk_types = []
        score = 0.0
        details = {}
        
        # 检查黑名单
        if address in self.blacklist_addresses:
            risk_types.append(RiskType.BLACKLIST)
            score += 50.0
            details["blacklist_address"] = True
        
        # 检查是否为新地址
        is_new_address = await self._is_new_address(request.user_id, address)
        if is_new_address:
            risk_types.append(RiskType.SUSPICIOUS_ADDRESS)
            score += 10.0
            details["new_address"] = True
        
        # 检查地址格式
        if not await self._validate_address_format(address, request.network):
            risk_types.append(RiskType.SUSPICIOUS_ADDRESS)
            score += 15.0
            details["invalid_format"] = True
        
        if risk_types:
            return {
                "types": risk_types,
                "score": score,
                "details": details
            }
        
        return None
    
    async def _check_user_behavior(self, request: WithdrawalRequest) -> Optional[Dict]:
        """检查用户行为模式"""
        user_id = request.user_id
        
        risk_types = []
        score = 0.0
        details = {}
        
        # 检查IP地址变化
        recent_ips = await self._get_recent_user_ips(user_id)
        if request.user_ip not in recent_ips:
            risk_types.append(RiskType.UNUSUAL_PATTERN)
            score += 15.0
            details["new_ip_address"] = request.user_ip
        
        # 检查提现时间模式
        is_unusual_time = await self._check_unusual_timing(user_id, request.request_time)
        if is_unusual_time:
            risk_types.append(RiskType.UNUSUAL_PATTERN)
            score += 10.0
            details["unusual_timing"] = True
        
        # 检查账户活跃度
        account_age = await self._get_account_age(user_id)
        if account_age < timedelta(days=7):
            risk_types.append(RiskType.UNUSUAL_PATTERN)
            score += 20.0
            details["new_account"] = True
        
        if risk_types:
            return {
                "types": risk_types,
                "score": score,
                "details": details
            }
        
        return None
    
    async def _check_balance_sufficiency(self, request: WithdrawalRequest) -> Optional[Dict]:
        """检查余额充足性"""
        # 这里应该查询实际余额
        # 暂时使用模拟数据
        available_balance = Decimal("1000")  # 模拟余额
        
        if request.amount > available_balance:
            return {
                "types": [RiskType.BALANCE_INSUFFICIENT],
                "score": 100.0,  # 余额不足直接拒绝
                "details": {
                    "available_balance": str(available_balance),
                    "requested_amount": str(request.amount),
                    "shortfall": str(request.amount - available_balance)
                }
            }
        
        return None
    
    async def _check_network_status(self, request: WithdrawalRequest) -> Optional[Dict]:
        """检查网络状态"""
        # 检查网络拥堵情况
        network_congestion = await self._get_network_congestion(request.network)
        
        if network_congestion > 0.8:  # 80%以上拥堵
            return {
                "types": [RiskType.NETWORK_CONGESTION],
                "score": 5.0,
                "details": {
                    "network": request.network,
                    "congestion_level": network_congestion,
                    "estimated_delay": "2-4小时"
                }
            }
        
        return None
    
    def _calculate_risk_level(self, risk_score: float) -> RiskLevel:
        """计算风险等级"""
        if risk_score >= 80:
            return RiskLevel.CRITICAL
        elif risk_score >= 50:
            return RiskLevel.HIGH
        elif risk_score >= 20:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _determine_approval(
        self,
        risk_level: RiskLevel,
        risk_types: List[RiskType],
        request: WithdrawalRequest
    ) -> tuple[bool, Optional[str]]:
        """确定是否批准"""
        # 余额不足直接拒绝
        if RiskType.BALANCE_INSUFFICIENT in risk_types:
            return False, "余额不足"
        
        # 黑名单地址直接拒绝
        if RiskType.BLACKLIST in risk_types:
            return False, "目标地址存在安全风险"
        
        # 高风险和极高风险需要人工审核
        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            return False, "需要人工审核"
        
        # 中等风险可能需要额外验证
        if risk_level == RiskLevel.MEDIUM:
            return True, None  # 可以批准但需要额外验证
        
        # 低风险直接批准
        return True, None
    
    def _determine_required_actions(self, risk_level: RiskLevel, risk_types: List[RiskType]) -> List[str]:
        """确定所需操作"""
        actions = []
        
        if RiskType.BALANCE_INSUFFICIENT in risk_types:
            actions.append("充值足够资金")
        
        if RiskType.BLACKLIST in risk_types:
            actions.append("更换提现地址")
        
        if RiskType.AMOUNT_LIMIT in risk_types:
            actions.append("降低提现金额")
        
        if RiskType.FREQUENCY_LIMIT in risk_types:
            actions.append("稍后重试")
        
        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            actions.append("等待人工审核")
            actions.append("准备身份验证材料")
        
        if RiskType.SUSPICIOUS_ADDRESS in risk_types:
            actions.append("验证提现地址")
        
        return actions
    
    def _estimate_review_time(self, risk_level: RiskLevel) -> Optional[timedelta]:
        """预估审核时间"""
        if risk_level == RiskLevel.LOW:
            return None  # 自动处理
        elif risk_level == RiskLevel.MEDIUM:
            return timedelta(minutes=30)
        elif risk_level == RiskLevel.HIGH:
            return timedelta(hours=2)
        else:  # CRITICAL
            return timedelta(hours=24)
    
    # 辅助方法（这些方法在实际实现中应该查询数据库）
    async def _get_daily_withdrawn_amount(self, user_id: int, currency: str) -> Decimal:
        """获取当日已提现金额"""
        # 这里应该查询数据库
        return Decimal("0")  # 模拟数据
    
    async def _get_withdrawal_count(self, user_id: int, period: timedelta) -> int:
        """获取指定时间段内的提现次数"""
        # 这里应该查询数据库
        return 0  # 模拟数据
    
    async def _is_new_address(self, user_id: int, address: str) -> bool:
        """检查是否为新地址"""
        # 这里应该查询数据库
        return True  # 模拟数据
    
    async def _validate_address_format(self, address: str, network: str) -> bool:
        """验证地址格式"""
        # 这里应该实现具体的地址格式验证
        return len(address) > 20  # 简单验证
    
    async def _get_recent_user_ips(self, user_id: int) -> List[str]:
        """获取用户最近使用的IP地址"""
        # 这里应该查询数据库
        return ["192.168.1.1"]  # 模拟数据
    
    async def _check_unusual_timing(self, user_id: int, request_time: datetime) -> bool:
        """检查是否为异常时间"""
        # 检查是否在用户常用时间段外
        hour = request_time.hour
        return hour < 6 or hour > 23  # 简单检查
    
    async def _get_account_age(self, user_id: int) -> timedelta:
        """获取账户年龄"""
        # 这里应该查询数据库
        return timedelta(days=30)  # 模拟数据
    
    async def _get_network_congestion(self, network: str) -> float:
        """获取网络拥堵程度"""
        # 这里应该查询实际网络状态
        return 0.3  # 模拟30%拥堵
    
    async def process_batch_withdrawal(
        self,
        batch_request: BatchWithdrawalRequest
    ) -> Dict[str, Any]:
        """处理批量提现"""
        try:
            results = []
            total_risk_score = 0.0
            approved_count = 0
            rejected_count = 0
            
            for withdrawal in batch_request.withdrawals:
                risk_result = await self.check_withdrawal_risk(withdrawal)
                
                results.append({
                    "withdrawal_id": f"{batch_request.batch_id}_{len(results) + 1}",
                    "currency": withdrawal.currency,
                    "amount": str(withdrawal.amount),
                    "destination_address": withdrawal.destination_address,
                    "risk_level": risk_result.risk_level.value,
                    "risk_score": risk_result.risk_score,
                    "is_approved": risk_result.is_approved,
                    "rejection_reason": risk_result.rejection_reason,
                    "required_actions": risk_result.required_actions
                })
                
                total_risk_score += risk_result.risk_score
                if risk_result.is_approved:
                    approved_count += 1
                else:
                    rejected_count += 1
            
            avg_risk_score = total_risk_score / len(batch_request.withdrawals)
            batch_risk_level = self._calculate_risk_level(avg_risk_score)
            
            # 记录批量提现日志
            await logging_service.log_batch_operation(
                user_id=batch_request.user_id,
                operation_type="batch_withdrawal",
                batch_id=batch_request.batch_id,
                total_count=len(batch_request.withdrawals),
                approved_count=approved_count,
                rejected_count=rejected_count,
                avg_risk_score=avg_risk_score
            )
            
            return {
                "batch_id": batch_request.batch_id,
                "total_count": len(batch_request.withdrawals),
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "avg_risk_score": avg_risk_score,
                "batch_risk_level": batch_risk_level.value,
                "results": results,
                "estimated_processing_time": self._estimate_batch_processing_time(
                    len(batch_request.withdrawals), batch_risk_level
                )
            }
            
        except Exception as e:
            logger.error(f"批量提现处理失败: {e}")
            raise
    
    def _estimate_batch_processing_time(
        self,
        count: int,
        risk_level: RiskLevel
    ) -> str:
        """预估批量处理时间"""
        base_time = count * 2  # 每笔2分钟基础时间
        
        if risk_level == RiskLevel.HIGH:
            base_time *= 3
        elif risk_level == RiskLevel.CRITICAL:
            base_time *= 5
        
        if base_time < 60:
            return f"{base_time}分钟"
        else:
            hours = base_time // 60
            minutes = base_time % 60
            return f"{hours}小时{minutes}分钟"


# 全局风控服务实例
risk_control_service = RiskControlService()


# 便捷函数
async def check_withdrawal_risk(request: WithdrawalRequest) -> RiskCheckResult:
    """检查提现风险"""
    return await risk_control_service.check_withdrawal_risk(request)


async def process_batch_withdrawal(batch_request: BatchWithdrawalRequest) -> Dict[str, Any]:
    """处理批量提现"""
    return await risk_control_service.process_batch_withdrawal(batch_request)