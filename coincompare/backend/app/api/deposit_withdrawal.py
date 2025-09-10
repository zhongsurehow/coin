from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.security import HTTPBearer
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum
import logging

from ..services.deposit_withdrawal import deposit_withdrawal_service, WithdrawalRequest, NetworkType
from ..services.enhanced_deposit_withdrawal_service import enhanced_deposit_withdrawal_service
from ..services.risk_control_service import (
    risk_control_service, WithdrawalRequest as RiskWithdrawalRequest, BatchWithdrawalRequest,
    RiskLevel, RiskType, WithdrawalStatus
)
from ..services.withdrawal_history_service import (
    withdrawal_history_service, TransactionType, ProcessingStage
)
from ..database import get_db_session
from pydantic import BaseModel, Field, validator
from ..core.auth import get_current_user

logger = logging.getLogger(__name__)
security = HTTPBearer()

router = APIRouter()

# Pydantic models for API
class DepositAddressRequest(BaseModel):
    exchange: str = Field(..., description="Exchange name")
    currency: str = Field(..., description="Currency symbol")
    network: Optional[str] = Field(None, description="Network type")

class DepositAddressResponse(BaseModel):
    address: str
    network: str
    currency: str
    tag: Optional[str] = None
    memo: Optional[str] = None
    min_deposit: Optional[float] = None
    confirmations_required: int = 6
    qr_code: Optional[str] = None  # Base64 encoded QR code

class WithdrawalRequestModel(BaseModel):
    exchange: str = Field(..., description="Exchange name")
    currency: str = Field(..., description="Currency symbol")
    amount: float = Field(..., gt=0, description="Withdrawal amount")
    address: str = Field(..., description="Destination address")
    network: str = Field(..., description="Network type")
    tag: Optional[str] = Field(None, description="Address tag/memo")
    memo: Optional[str] = Field(None, description="Transaction memo")
    two_fa_code: Optional[str] = Field(None, description="2FA verification code")
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v

class WithdrawalResponse(BaseModel):
    transaction_id: str
    status: str
    estimated_arrival: Optional[datetime] = None
    fee: Optional[float] = None
    network_fee: Optional[float] = None
    total_deducted: Optional[float] = None

class TransactionResponse(BaseModel):
    id: str
    exchange: str
    currency: str
    amount: float
    fee: float
    status: str
    transaction_type: str
    network: str
    address: str
    tag: Optional[str]
    memo: Optional[str]
    tx_hash: Optional[str]
    confirmations: int
    required_confirmations: Optional[int]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    estimated_arrival: Optional[datetime]

class UnifiedTransferRequest(BaseModel):
    source_exchange: str = Field(..., description="Source exchange")
    target_exchange: str = Field(..., description="Target exchange")
    currency: str = Field(..., description="Currency symbol")
    amount: float = Field(..., gt=0, description="Transfer amount")
    network: Optional[str] = Field(None, description="Network type")
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v

class UnifiedTransferResponse(BaseModel):
    withdrawal_id: str
    deposit_address: str
    estimated_completion: datetime
    total_fee: float
    status: str
    tracking_url: Optional[str]

class FeeCalculationRequest(BaseModel):
    exchange: str = Field(..., description="Exchange name")
    currency: str = Field(..., description="Currency symbol")
    network: str = Field(..., description="Network type")
    amount: float = Field(..., gt=0, description="Withdrawal amount")

class ArrivalEstimationRequest(BaseModel):
    exchange: str = Field(..., description="Exchange name")
    currency: str = Field(..., description="Currency symbol")
    network: str = Field(..., description="Network type")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")

class TransactionMonitoringRequest(BaseModel):
    transaction_id: str = Field(..., description="Transaction ID")
    tx_hash: str = Field(..., description="Transaction hash")
    network: str = Field(..., description="Network type")

class WithdrawalRiskCheckRequest(BaseModel):
    """提现风控检查请求"""
    exchange: str
    currency: str
    amount: Decimal
    destination_address: str
    network: str
    memo: Optional[str] = None
    withdrawal_password: Optional[str] = None
    two_fa_code: Optional[str] = None

class BatchWithdrawalRequestModel(BaseModel):
    """批量提现请求"""
    withdrawals: List[WithdrawalRiskCheckRequest]
    priority: str = "normal"

class WithdrawalHistoryRequest(BaseModel):
    """提现历史查询请求"""
    limit: int = Field(default=50, le=100)
    offset: int = Field(default=0, ge=0)
    status_filter: Optional[List[str]] = None
    currency_filter: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class WithdrawalCancelRequest(BaseModel):
    """取消提现请求"""
    withdrawal_id: str
    reason: Optional[str] = None

class ExchangeAPIRequest(BaseModel):
    exchange: str = Field(..., description="Exchange name")
    api_key: str = Field(..., description="API key")
    api_secret: str = Field(..., description="API secret")
    passphrase: Optional[str] = Field(None, description="API passphrase (for some exchanges)")
    
class SupportedCurrencyResponse(BaseModel):
    currency: str
    name: str
    networks: List[Dict[str, Any]]
    min_deposit: Optional[float]
    min_withdrawal: Optional[float]
    withdrawal_fee: Optional[float]
    deposit_enabled: bool
    withdrawal_enabled: bool

class WithdrawalFeeResponse(BaseModel):
    currency: str
    network: str
    fee: float
    min_withdrawal: float
    max_withdrawal: Optional[float]
    daily_limit: Optional[float]
    precision: int

# Helper function to get user_id from token
def get_user_id_from_token(token: str) -> int:
    # This would decode the JWT token and extract user_id
    # For now, return a dummy user_id
    return 1

@router.post("/add-exchange-api")
async def add_exchange_api(
    request: ExchangeAPIRequest,
    token: str = Depends(security)
):
    """Add exchange API credentials for a user"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        await deposit_withdrawal_service.add_exchange_api(
            user_id=user_id,
            exchange=request.exchange,
            api_key=request.api_key,
            api_secret=request.api_secret,
            passphrase=request.passphrase
        )
        
        return {"message": f"Successfully added {request.exchange} API credentials"}
    
    except Exception as e:
        logger.error(f"Error adding exchange API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deposit-address", response_model=DepositAddressResponse)
async def get_deposit_address(
    request: DepositAddressRequest,
    token: str = Depends(security)
):
    """Get deposit address for a currency"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        address = await deposit_withdrawal_service.get_deposit_address(
            user_id=user_id,
            exchange=request.exchange,
            currency=request.currency,
            network=request.network
        )
        
        # Generate QR code for the address
        qr_code = None
        try:
            import qrcode
            import io
            import base64
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr_data = address.address
            if address.tag:
                qr_data += f"?tag={address.tag}"
            if address.memo:
                qr_data += f"&memo={address.memo}" if "?" in qr_data else f"?memo={address.memo}"
            
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            qr_code = base64.b64encode(buffer.getvalue()).decode()
        except ImportError:
            logger.warning("QR code generation not available - qrcode package not installed")
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
        
        return DepositAddressResponse(
            address=address.address,
            network=address.network.value,
            currency=address.currency,
            tag=address.tag,
            memo=address.memo,
            min_deposit=float(address.min_deposit) if address.min_deposit else None,
            confirmations_required=address.confirmations_required,
            qr_code=qr_code
        )
    
    except Exception as e:
        logger.error(f"Error getting deposit address: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/withdraw", response_model=WithdrawalResponse)
async def submit_withdrawal(
    request: WithdrawalRequestModel,
    token: str = Depends(security)
):
    """Submit a withdrawal request"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # Get withdrawal fee first
        fee = await deposit_withdrawal_service.get_withdrawal_fee(
            user_id=user_id,
            exchange=request.exchange,
            currency=request.currency,
            network=request.network
        )
        
        # Create withdrawal request
        withdrawal_request = WithdrawalRequest(
            currency=request.currency,
            amount=Decimal(str(request.amount)),
            address=request.address,
            network=NetworkType(request.network),
            tag=request.tag,
            memo=request.memo,
            fee=fee,
            user_id=user_id,
            two_fa_code=request.two_fa_code
        )
        
        transaction_id = await deposit_withdrawal_service.submit_withdrawal(
            user_id=user_id,
            exchange=request.exchange,
            request=withdrawal_request
        )
        
        # Calculate estimated arrival time (this would be more sophisticated in reality)
        from datetime import timedelta
        estimated_arrival = datetime.now() + timedelta(minutes=30)  # Default 30 minutes
        
        return WithdrawalResponse(
            transaction_id=transaction_id,
            status="pending",
            estimated_arrival=estimated_arrival,
            fee=float(fee),
            network_fee=float(fee),  # Simplified - in reality this might be different
            total_deducted=float(Decimal(str(request.amount)) + fee)
        )
    
    except Exception as e:
        logger.error(f"Error submitting withdrawal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deposit-history", response_model=List[TransactionResponse])
async def get_deposit_history(
    exchange: str = Query(..., description="Exchange name"),
    currency: Optional[str] = Query(None, description="Currency filter"),
    limit: int = Query(50, ge=1, le=200, description="Number of records to return"),
    token: str = Depends(security)
):
    """Get deposit history"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        transactions = await deposit_withdrawal_service.get_deposit_history(
            user_id=user_id,
            exchange=exchange,
            currency=currency,
            limit=limit
        )
        
        return [
            TransactionResponse(
                id=tx.id,
                exchange=tx.exchange,
                currency=tx.currency,
                amount=float(tx.amount),
                fee=float(tx.fee),
                status=tx.status.value,
                transaction_type=tx.transaction_type.value,
                network=tx.network.value,
                address=tx.address,
                tag=tx.tag,
                memo=tx.memo,
                tx_hash=tx.tx_hash,
                confirmations=tx.confirmations,
                required_confirmations=6,  # Default value
                created_at=tx.created_at,
                updated_at=tx.updated_at,
                completed_at=tx.completed_at,
                error_message=tx.error_message,
                estimated_arrival=tx.completed_at  # Simplified
            )
            for tx in transactions
        ]
    
    except Exception as e:
        logger.error(f"Error getting deposit history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/withdrawal-history", response_model=List[TransactionResponse])
async def get_withdrawal_history(
    exchange: str = Query(..., description="Exchange name"),
    currency: Optional[str] = Query(None, description="Currency filter"),
    limit: int = Query(50, ge=1, le=200, description="Number of records to return"),
    token: str = Depends(security)
):
    """Get withdrawal history"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        transactions = await deposit_withdrawal_service.get_withdrawal_history(
            user_id=user_id,
            exchange=exchange,
            currency=currency,
            limit=limit
        )
        
        return [
            TransactionResponse(
                id=tx.id,
                exchange=tx.exchange,
                currency=tx.currency,
                amount=float(tx.amount),
                fee=float(tx.fee),
                status=tx.status.value,
                transaction_type=tx.transaction_type.value,
                network=tx.network.value,
                address=tx.address,
                tag=tx.tag,
                memo=tx.memo,
                tx_hash=tx.tx_hash,
                confirmations=tx.confirmations,
                required_confirmations=6,  # Default value
                created_at=tx.created_at,
                updated_at=tx.updated_at,
                completed_at=tx.completed_at,
                error_message=tx.error_message,
                estimated_arrival=tx.completed_at  # Simplified
            )
            for tx in transactions
        ]
    
    except Exception as e:
        logger.error(f"Error getting withdrawal history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transaction/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_status(
    transaction_id: str,
    exchange: str = Query(..., description="Exchange name"),
    token: str = Depends(security)
):
    """Get transaction status"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        transaction = await deposit_withdrawal_service.get_transaction_status(
            user_id=user_id,
            exchange=exchange,
            transaction_id=transaction_id
        )
        
        return TransactionResponse(
            id=transaction.id,
            exchange=transaction.exchange,
            currency=transaction.currency,
            amount=float(transaction.amount),
            fee=float(transaction.fee),
            status=transaction.status.value,
            transaction_type=transaction.transaction_type.value,
            network=transaction.network.value,
            address=transaction.address,
            tag=transaction.tag,
            memo=transaction.memo,
            tx_hash=transaction.tx_hash,
            confirmations=transaction.confirmations,
            required_confirmations=6,  # Default value
            created_at=transaction.created_at,
            updated_at=transaction.updated_at,
            completed_at=transaction.completed_at,
            error_message=transaction.error_message,
            estimated_arrival=transaction.completed_at  # Simplified
        )
    
    except Exception as e:
        logger.error(f"Error getting transaction status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/withdrawal-fee", response_model=WithdrawalFeeResponse)
async def get_withdrawal_fee(
    exchange: str = Query(..., description="Exchange name"),
    currency: str = Query(..., description="Currency symbol"),
    network: Optional[str] = Query(None, description="Network type"),
    token: str = Depends(security)
):
    """Get withdrawal fee for a currency"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        fee = await deposit_withdrawal_service.get_withdrawal_fee(
            user_id=user_id,
            exchange=exchange,
            currency=currency,
            network=network
        )
        
        return WithdrawalFeeResponse(
            currency=currency,
            network=network or "default",
            fee=float(fee),
            min_withdrawal=10.0,  # Default values - would come from exchange
            max_withdrawal=None,
            daily_limit=None,
            precision=8
        )
    
    except Exception as e:
        logger.error(f"Error getting withdrawal fee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/supported-currencies", response_model=List[SupportedCurrencyResponse])
async def get_supported_currencies(
    exchange: str = Query(..., description="Exchange name"),
    token: str = Depends(security)
):
    """Get supported currencies for an exchange"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        currencies = await deposit_withdrawal_service.get_supported_currencies(
            user_id=user_id,
            exchange=exchange
        )
        
        return [
            SupportedCurrencyResponse(
                currency=currency["currency"],
                name=currency.get("name", currency["currency"]),
                networks=currency.get("networks", []),
                min_deposit=currency.get("min_deposit"),
                min_withdrawal=currency.get("min_withdrawal"),
                withdrawal_fee=currency.get("withdrawal_fee"),
                deposit_enabled=currency.get("deposit_enabled", True),
                withdrawal_enabled=currency.get("withdrawal_enabled", True)
            )
            for currency in currencies
        ]
    
    except Exception as e:
        logger.error(f"Error getting supported currencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/unified-transfer", response_model=UnifiedTransferResponse)
async def unified_transfer(
    request: UnifiedTransferRequest,
    token: str = Depends(security)
):
    """Perform unified deposit/withdrawal between exchanges"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        withdrawal_id, deposit_address = await deposit_withdrawal_service.unified_deposit_withdrawal(
            user_id=user_id,
            source_exchange=request.source_exchange,
            target_exchange=request.target_exchange,
            currency=request.currency,
            amount=Decimal(str(request.amount)),
            network=request.network
        )
        
        # Get withdrawal fee for total cost calculation
        fee = await deposit_withdrawal_service.get_withdrawal_fee(
            user_id=user_id,
            exchange=request.source_exchange,
            currency=request.currency,
            network=request.network
        )
        
        # Estimate completion time (this would be more sophisticated)
        from datetime import timedelta
        estimated_completion = datetime.now() + timedelta(hours=1)  # Default 1 hour
        
        return UnifiedTransferResponse(
            withdrawal_id=withdrawal_id,
            deposit_address=deposit_address,
            estimated_completion=estimated_completion,
            total_fee=float(fee),
            status="initiated",
            tracking_url=f"/api/deposit-withdrawal/transaction/{withdrawal_id}?exchange={request.source_exchange}"
        )
    
    except Exception as e:
        logger.error(f"Error in unified transfer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transfer-routes")
async def get_transfer_routes(
    currency: str = Query(..., description="Currency symbol"),
    token: str = Depends(security)
):
    """Get available transfer routes for a currency"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # This would analyze available exchanges and networks
        # For now, return a simplified response
        routes = [
            {
                "source": "binance",
                "target": "okx",
                "networks": ["ERC20", "TRC20", "BEP20"],
                "estimated_time": "30-60 minutes",
                "fee_range": "0.1-2.0 USDT"
            },
            {
                "source": "okx",
                "target": "binance",
                "networks": ["ERC20", "TRC20", "BEP20"],
                "estimated_time": "30-60 minutes",
                "fee_range": "0.1-2.0 USDT"
            }
        ]
        
        return {"currency": currency, "routes": routes}
    
    except Exception as e:
        logger.error(f"Error getting transfer routes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/network-status")
async def get_network_status():
    """Get blockchain network status"""
    try:
        # This would check network congestion, fees, etc.
        # For now, return mock data
        networks = [
            {
                "network": "ERC20",
                "status": "normal",
                "congestion": "low",
                "avg_confirmation_time": "15 minutes",
                "current_fee": "15 GWEI"
            },
            {
                "network": "TRC20",
                "status": "normal",
                "congestion": "low",
                "avg_confirmation_time": "3 minutes",
                "current_fee": "1 TRX"
            },
            {
                "network": "BEP20",
                "status": "normal",
                "congestion": "low",
                "avg_confirmation_time": "5 minutes",
                "current_fee": "0.001 BNB"
            }
        ]
        
        return {"networks": networks, "last_updated": datetime.now()}
    
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calculate-fee")
async def calculate_withdrawal_fee(
    request: FeeCalculationRequest,
    token: str = Depends(security)
):
    """Calculate withdrawal fee with real-time data"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        fee_info = await enhanced_deposit_withdrawal_service.calculate_withdrawal_fee(
            user_id=user_id,
            exchange=request.exchange,
            currency=request.currency,
            network=request.network,
            amount=Decimal(str(request.amount))
        )
        
        return fee_info
    
    except Exception as e:
        logger.error(f"Error calculating withdrawal fee: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/estimate-arrival")
async def estimate_arrival_time(
    request: ArrivalEstimationRequest,
    token: str = Depends(security)
):
    """Estimate transaction arrival time"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        estimation = await enhanced_deposit_withdrawal_service.estimate_arrival_time(
            user_id=user_id,
            exchange=request.exchange,
            currency=request.currency,
            network=request.network,
            tx_hash=request.tx_hash
        )
        
        return estimation
    
    except Exception as e:
        logger.error(f"Error estimating arrival time: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monitor-transaction")
async def start_transaction_monitoring(
    request: TransactionMonitoringRequest,
    background_tasks: BackgroundTasks,
    token: str = Depends(security)
):
    """Start real-time transaction monitoring"""
    try:
        user_id = get_user_id_from_token(token.credentials)
        
        # Start background monitoring task
        background_tasks.add_task(
            enhanced_deposit_withdrawal_service.monitor_transaction,
            user_id=user_id,
            transaction_id=request.transaction_id,
            tx_hash=request.tx_hash,
            network=request.network
        )
        
        return {"message": "Transaction monitoring started", "transaction_id": request.transaction_id}
    
    except Exception as e:
        logger.error(f"Error starting transaction monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transaction/{transaction_id}/status")
async def get_real_time_transaction_status(
    transaction_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get real-time transaction status with detailed information"""
    try:
        user_id = current_user["user_id"]
        
        status = await enhanced_deposit_withdrawal_service.get_real_time_status(
            user_id=user_id,
            transaction_id=transaction_id
        )
        
        return {
            "success": True,
            "data": {
                "transaction_id": status.transaction_id,
                "current_status": status.current_status,
                "confirmations": status.confirmations,
                "required_confirmations": status.required_confirmations,
                "estimated_completion": status.estimated_completion,
                "last_updated": status.last_updated,
                "blockchain_url": status.blockchain_url
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting real-time transaction status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/withdrawal/risk-check")
async def check_withdrawal_risk(
    request: WithdrawalRiskCheckRequest,
    current_user: dict = Depends(get_current_user)
):
    """提现风控检查"""
    try:
        user_id = current_user["user_id"]
        
        # 创建风控检查请求
        risk_request = RiskWithdrawalRequest(
            user_id=user_id,
            exchange=request.exchange,
            currency=request.currency,
            amount=request.amount,
            destination_address=request.destination_address,
            network=request.network,
            memo=request.memo,
            user_ip="127.0.0.1",  # 应该从请求中获取
            user_agent="",  # 应该从请求中获取
            request_time=datetime.utcnow(),
            two_fa_code=request.two_fa_code,
            withdrawal_password=request.withdrawal_password
        )
        
        risk_result = await risk_control_service.check_withdrawal_risk(risk_request)
        
        return {
            "success": True,
            "data": {
                "risk_level": risk_result.risk_level.value,
                "risk_score": risk_result.risk_score,
                "risk_types": [rt.value for rt in risk_result.risk_types],
                "is_approved": risk_result.is_approved,
                "rejection_reason": risk_result.rejection_reason,
                "required_actions": risk_result.required_actions,
                "additional_verification": risk_result.additional_verification,
                "estimated_review_time": risk_result.estimated_review_time.total_seconds() if risk_result.estimated_review_time else None,
                "details": risk_result.details
            }
        }
    
    except Exception as e:
        logger.error(f"风控检查失败: {e}")
        raise HTTPException(status_code=500, detail=f"风控检查失败: {str(e)}")

@router.post("/withdrawal/batch")
async def batch_withdrawal(
    request: BatchWithdrawalRequestModel,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """批量提现"""
    try:
        user_id = current_user["user_id"]
        
        # 转换为风控服务的请求格式
        withdrawals = []
        for w in request.withdrawals:
            withdrawal_req = RiskWithdrawalRequest(
                user_id=user_id,
                exchange=w.exchange,
                currency=w.currency,
                amount=w.amount,
                destination_address=w.destination_address,
                network=w.network,
                memo=w.memo,
                user_ip="127.0.0.1",
                user_agent="",
                request_time=datetime.utcnow(),
                two_fa_code=w.two_fa_code,
                withdrawal_password=w.withdrawal_password
            )
            withdrawals.append(withdrawal_req)
        
        batch_request = BatchWithdrawalRequest(
            user_id=user_id,
            withdrawals=withdrawals,
            total_amount=sum(w.amount for w in withdrawals),
            currency=withdrawals[0].currency if withdrawals else "USDT",
            batch_id=f"batch_{user_id}_{int(datetime.utcnow().timestamp())}",
            priority=request.priority
        )
        
        batch_result = await risk_control_service.process_batch_withdrawal(batch_request)
        
        return {
            "success": True,
            "data": batch_result
        }
    
    except Exception as e:
        logger.error(f"批量提现失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量提现失败: {str(e)}")

@router.get("/withdrawal/history")
async def get_withdrawal_history_enhanced(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    currency_filter: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user)
):
    """获取增强的提现历史"""
    try:
        user_id = current_user["user_id"]
        
        # 转换状态过滤器
        status_list = None
        if status_filter:
            status_list = [WithdrawalStatus(s) for s in status_filter.split(",")]
        
        records = await withdrawal_history_service.get_user_withdrawals(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status_filter=status_list,
            currency_filter=currency_filter,
            start_date=start_date,
            end_date=end_date
        )
        
        # 获取统计信息
        statistics = await withdrawal_history_service.get_withdrawal_statistics(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return {
            "success": True,
            "data": {
                "records": [
                    {
                        "withdrawal_id": r.withdrawal_id,
                        "currency": r.currency,
                        "amount": str(r.amount),
                        "fee": str(r.fee),
                        "net_amount": str(r.net_amount),
                        "destination_address": r.destination_address,
                        "network": r.network,
                        "status": r.status.value,
                        "processing_stage": r.processing_stage.value,
                        "risk_level": r.risk_level.value,
                        "created_at": r.created_at.isoformat(),
                        "updated_at": r.updated_at.isoformat(),
                        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                        "tx_hash": r.tx_hash,
                        "confirmations": r.confirmations,
                        "required_confirmations": r.required_confirmations
                    }
                    for r in records
                ],
                "statistics": {
                    "total_count": statistics.total_count,
                    "total_amount": str(statistics.total_amount),
                    "successful_count": statistics.successful_count,
                    "successful_amount": str(statistics.successful_amount),
                    "success_rate": statistics.success_rate,
                    "avg_processing_time": statistics.avg_processing_time.total_seconds() if statistics.avg_processing_time else None
                }
            }
        }
    
    except Exception as e:
        logger.error(f"获取提现历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取提现历史失败: {str(e)}")

@router.post("/withdrawal/{withdrawal_id}/cancel")
async def cancel_withdrawal(
    withdrawal_id: str,
    request: WithdrawalCancelRequest,
    current_user: dict = Depends(get_current_user)
):
    """取消提现"""
    try:
        user_id = current_user["user_id"]
        
        # 验证提现记录属于当前用户
        record = await withdrawal_history_service.get_withdrawal_record(withdrawal_id)
        if not record or record.user_id != user_id:
            raise HTTPException(status_code=404, detail="提现记录不存在")
        
        result = await withdrawal_history_service.cancel_withdrawal(
            withdrawal_id=withdrawal_id,
            operator=f"user_{user_id}",
            reason=request.reason
        )
        
        if not result:
            raise HTTPException(status_code=400, detail="无法取消该提现")
        
        return {
            "success": True,
            "data": {
                "withdrawal_id": withdrawal_id,
                "status": "cancelled",
                "cancelled_at": datetime.utcnow().isoformat()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消提现失败: {e}")
        raise HTTPException(status_code=500, detail=f"取消提现失败: {str(e)}")