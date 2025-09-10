from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta
import logging

from ..core.auth import get_current_user
from ..services.unified_transfer_service import (
    unified_transfer_service, TransferRequest, TransferType, 
    TransferRoute, TransferResult, BalanceInfo
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/unified-transfer", tags=["unified-transfer"])

# Pydantic 模型
class RouteCalculationRequest(BaseModel):
    """路径计算请求"""
    source_exchange: str = Field(..., description="源交易所")
    destination_exchange: str = Field(..., description="目标交易所")
    currency: str = Field(..., description="币种")
    amount: str = Field(..., description="金额")
    max_routes: int = Field(5, description="最大路径数量")

class TransferSubmissionRequest(BaseModel):
    """转账提交请求"""
    transfer_type: str = Field(..., description="转账类型")
    source_exchange: str = Field(..., description="源交易所")
    destination_exchange: str = Field(..., description="目标交易所")
    currency: str = Field(..., description="币种")
    amount: str = Field(..., description="金额")
    destination_address: Optional[str] = Field(None, description="目标地址")
    network: Optional[str] = Field(None, description="网络")
    memo: Optional[str] = Field(None, description="备注")
    priority: str = Field("normal", description="优先级")
    max_fee_rate: Optional[float] = Field(None, description="最大手续费率")
    max_time_hours: Optional[float] = Field(None, description="最大时间（小时）")
    auto_execute: bool = Field(False, description="是否自动执行")

class TransferExecutionRequest(BaseModel):
    """转账执行请求"""
    transfer_id: str = Field(..., description="转账ID")

class TransferCancelRequest(BaseModel):
    """转账取消请求"""
    reason: Optional[str] = Field(None, description="取消原因")

class RebalanceRequest(BaseModel):
    """再平衡请求"""
    target_distribution: Dict[str, Dict[str, float]] = Field(..., description="目标分布")
    auto_execute: bool = Field(False, description="是否自动执行")

class RouteResponse(BaseModel):
    """路径响应"""
    route_id: str
    route_type: str
    source_exchange: str
    destination_exchange: str
    currency: str
    amount: str
    estimated_fee: str
    estimated_time_seconds: float
    confidence_score: float
    net_amount: str
    fee_rate: float
    risk_level: str
    steps: List[Dict[str, Any]]

@router.post("/calculate-routes")
async def calculate_transfer_routes(
    request: RouteCalculationRequest,
    current_user: dict = Depends(get_current_user)
):
    """计算转账路径"""
    try:
        amount = Decimal(request.amount)
        
        routes = await unified_transfer_service.calculate_optimal_routes(
            source_exchange=request.source_exchange,
            destination_exchange=request.destination_exchange,
            currency=request.currency,
            amount=amount,
            max_routes=request.max_routes
        )
        
        route_responses = []
        for route in routes:
            route_response = RouteResponse(
                route_id=route.route_id,
                route_type=route.route_type.value,
                source_exchange=route.source_exchange,
                destination_exchange=route.destination_exchange,
                currency=route.currency,
                amount=str(route.amount),
                estimated_fee=str(route.estimated_fee),
                estimated_time_seconds=route.estimated_time.total_seconds(),
                confidence_score=route.confidence_score,
                net_amount=str(route.net_amount),
                fee_rate=route.fee_rate,
                risk_level=route.risk_level,
                steps=route.steps
            )
            route_responses.append(route_response)
        
        return {
            "success": True,
            "data": {
                "routes": [r.dict() for r in route_responses],
                "total_routes": len(route_responses),
                "calculation_time": datetime.utcnow().isoformat()
            }
        }
    
    except Exception as e:
        logger.error(f"计算转账路径失败: {e}")
        raise HTTPException(status_code=500, detail=f"计算转账路径失败: {str(e)}")

@router.post("/submit")
async def submit_transfer(
    request: TransferSubmissionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """提交转账请求"""
    try:
        user_id = current_user["user_id"]
        
        # 生成转账ID
        transfer_id = f"transfer_{user_id}_{request.currency}_{int(datetime.utcnow().timestamp())}"
        
        # 转换请求参数
        max_time = None
        if request.max_time_hours:
            max_time = timedelta(hours=request.max_time_hours)
        
        transfer_request = TransferRequest(
            user_id=user_id,
            transfer_id=transfer_id,
            transfer_type=TransferType(request.transfer_type),
            source_exchange=request.source_exchange,
            destination_exchange=request.destination_exchange,
            currency=request.currency,
            amount=Decimal(request.amount),
            destination_address=request.destination_address,
            network=request.network,
            memo=request.memo,
            priority=request.priority,
            max_fee_rate=request.max_fee_rate,
            max_time=max_time,
            auto_execute=request.auto_execute
        )
        
        result = await unified_transfer_service.submit_transfer_request(transfer_request)
        
        return {
            "success": True,
            "data": {
                "transfer_id": result.transfer_id,
                "status": result.status.value,
                "selected_route": {
                    "route_id": result.selected_route.route_id,
                    "route_type": result.selected_route.route_type.value,
                    "estimated_fee": str(result.selected_route.estimated_fee),
                    "estimated_time_seconds": result.selected_route.estimated_time.total_seconds(),
                    "confidence_score": result.selected_route.confidence_score
                } if result.selected_route else None,
                "error_message": result.error_message
            }
        }
    
    except Exception as e:
        logger.error(f"提交转账请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"提交转账请求失败: {str(e)}")

@router.post("/execute/{transfer_id}")
async def execute_transfer(
    transfer_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """执行转账"""
    try:
        user_id = current_user["user_id"]
        
        # 验证转账请求属于当前用户
        if transfer_id not in unified_transfer_service.active_transfers:
            raise HTTPException(status_code=404, detail="转账请求不存在")
        
        request = unified_transfer_service.active_transfers[transfer_id]
        if request.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权限执行此转账")
        
        # 检查状态
        result = await unified_transfer_service.get_transfer_status(transfer_id)
        if not result or result.status.value not in ["approved", "pending"]:
            raise HTTPException(status_code=400, detail="转账状态不允许执行")
        
        # 异步执行转账
        background_tasks.add_task(unified_transfer_service._execute_transfer, request)
        
        return {
            "success": True,
            "data": {
                "transfer_id": transfer_id,
                "status": "executing",
                "message": "转账已开始执行"
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行转账失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行转账失败: {str(e)}")

@router.get("/status/{transfer_id}")
async def get_transfer_status(
    transfer_id: str,
    current_user: dict = Depends(get_current_user)
):
    """获取转账状态"""
    try:
        user_id = current_user["user_id"]
        
        # 验证权限
        if transfer_id in unified_transfer_service.active_transfers:
            request = unified_transfer_service.active_transfers[transfer_id]
            if request.user_id != user_id:
                raise HTTPException(status_code=403, detail="无权限查看此转账")
        
        result = await unified_transfer_service.get_transfer_status(transfer_id)
        if not result:
            raise HTTPException(status_code=404, detail="转账记录不存在")
        
        response_data = {
            "transfer_id": result.transfer_id,
            "status": result.status.value,
            "error_message": result.error_message,
            "completed_at": result.completed_at.isoformat() if result.completed_at else None
        }
        
        if result.selected_route:
            response_data["selected_route"] = {
                "route_id": result.selected_route.route_id,
                "route_type": result.selected_route.route_type.value,
                "estimated_fee": str(result.selected_route.estimated_fee),
                "estimated_time_seconds": result.selected_route.estimated_time.total_seconds(),
                "confidence_score": result.selected_route.confidence_score,
                "steps": result.selected_route.steps
            }
        
        if result.actual_fee:
            response_data["actual_fee"] = str(result.actual_fee)
        
        if result.actual_time:
            response_data["actual_time_seconds"] = result.actual_time.total_seconds()
        
        if result.tx_hashes:
            response_data["tx_hashes"] = result.tx_hashes
        
        return {
            "success": True,
            "data": response_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取转账状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取转账状态失败: {str(e)}")

@router.post("/cancel/{transfer_id}")
async def cancel_transfer(
    transfer_id: str,
    request: TransferCancelRequest,
    current_user: dict = Depends(get_current_user)
):
    """取消转账"""
    try:
        user_id = current_user["user_id"]
        
        success = await unified_transfer_service.cancel_transfer(transfer_id, user_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="无法取消该转账")
        
        return {
            "success": True,
            "data": {
                "transfer_id": transfer_id,
                "status": "cancelled",
                "cancelled_at": datetime.utcnow().isoformat(),
                "reason": request.reason
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消转账失败: {e}")
        raise HTTPException(status_code=500, detail=f"取消转账失败: {str(e)}")

@router.get("/balance-overview")
async def get_balance_overview(
    current_user: dict = Depends(get_current_user)
):
    """获取余额概览"""
    try:
        user_id = current_user["user_id"]
        
        balances = await unified_transfer_service.get_balance_overview(user_id)
        
        # 转换为响应格式
        formatted_balances = {}
        for exchange, exchange_balances in balances.items():
            formatted_balances[exchange] = {}
            for currency, balance_info in exchange_balances.items():
                formatted_balances[exchange][currency] = {
                    "available": str(balance_info.available),
                    "frozen": str(balance_info.frozen),
                    "total": str(balance_info.total),
                    "last_updated": balance_info.last_updated.isoformat()
                }
        
        return {
            "success": True,
            "data": {
                "balances": formatted_balances,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    
    except Exception as e:
        logger.error(f"获取余额概览失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取余额概览失败: {str(e)}")

@router.post("/suggest-rebalance")
async def suggest_rebalance(
    request: RebalanceRequest,
    current_user: dict = Depends(get_current_user)
):
    """建议再平衡操作"""
    try:
        user_id = current_user["user_id"]
        
        suggestions = await unified_transfer_service.suggest_rebalance(
            user_id=user_id,
            target_distribution=request.target_distribution
        )
        
        # 转换为响应格式
        suggestion_responses = []
        for suggestion in suggestions:
            suggestion_responses.append({
                "transfer_id": suggestion.transfer_id,
                "transfer_type": suggestion.transfer_type.value,
                "source_exchange": suggestion.source_exchange,
                "destination_exchange": suggestion.destination_exchange,
                "currency": suggestion.currency,
                "amount": str(suggestion.amount),
                "priority": suggestion.priority
            })
        
        # 如果设置了自动执行，则提交所有建议的转账
        if request.auto_execute:
            executed_transfers = []
            for suggestion in suggestions:
                result = await unified_transfer_service.submit_transfer_request(suggestion)
                executed_transfers.append({
                    "transfer_id": result.transfer_id,
                    "status": result.status.value
                })
            
            return {
                "success": True,
                "data": {
                    "suggestions": suggestion_responses,
                    "executed_transfers": executed_transfers,
                    "auto_executed": True
                }
            }
        
        return {
            "success": True,
            "data": {
                "suggestions": suggestion_responses,
                "total_suggestions": len(suggestion_responses),
                "auto_executed": False
            }
        }
    
    except Exception as e:
        logger.error(f"生成再平衡建议失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成再平衡建议失败: {str(e)}")

@router.get("/history")
async def get_transfer_history(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    transfer_type_filter: Optional[str] = None,
    currency_filter: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user)
):
    """获取转账历史"""
    try:
        user_id = current_user["user_id"]
        
        # 从活跃转账和结果中筛选用户的转账记录
        user_transfers = []
        
        for transfer_id, request in unified_transfer_service.active_transfers.items():
            if request.user_id != user_id:
                continue
            
            result = unified_transfer_service.transfer_results.get(transfer_id)
            if not result:
                continue
            
            # 应用过滤条件
            if status_filter and result.status.value != status_filter:
                continue
            
            if transfer_type_filter and request.transfer_type.value != transfer_type_filter:
                continue
            
            if currency_filter and request.currency != currency_filter:
                continue
            
            if start_date and request.created_at < start_date:
                continue
            
            if end_date and request.created_at > end_date:
                continue
            
            transfer_data = {
                "transfer_id": transfer_id,
                "transfer_type": request.transfer_type.value,
                "source_exchange": request.source_exchange,
                "destination_exchange": request.destination_exchange,
                "currency": request.currency,
                "amount": str(request.amount),
                "status": result.status.value,
                "created_at": request.created_at.isoformat(),
                "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                "priority": request.priority
            }
            
            if result.selected_route:
                transfer_data["estimated_fee"] = str(result.selected_route.estimated_fee)
                transfer_data["route_type"] = result.selected_route.route_type.value
            
            if result.actual_fee:
                transfer_data["actual_fee"] = str(result.actual_fee)
            
            if result.actual_time:
                transfer_data["actual_time_seconds"] = result.actual_time.total_seconds()
            
            if result.tx_hashes:
                transfer_data["tx_hashes"] = result.tx_hashes
            
            if result.error_message:
                transfer_data["error_message"] = result.error_message
            
            user_transfers.append(transfer_data)
        
        # 按创建时间排序
        user_transfers.sort(key=lambda x: x["created_at"], reverse=True)
        
        # 分页
        total_count = len(user_transfers)
        paginated_transfers = user_transfers[offset:offset + limit]
        
        return {
            "success": True,
            "data": {
                "transfers": paginated_transfers,
                "total_count": total_count,
                "limit": limit,
                "offset": offset
            }
        }
    
    except Exception as e:
        logger.error(f"获取转账历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取转账历史失败: {str(e)}")