import asyncio
import aiohttp
import hashlib
import hmac
import time
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass

from ..config import settings
from ..models.user import User
from ..database import get_redis_client

logger = logging.getLogger(__name__)

class TransactionType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"

class TransactionStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CONFIRMING = "confirming"

class NetworkType(Enum):
    ERC20 = "ERC20"
    TRC20 = "TRC20"
    BEP20 = "BEP20"
    NATIVE = "NATIVE"
    POLYGON = "POLYGON"
    ARBITRUM = "ARBITRUM"
    OPTIMISM = "OPTIMISM"

@dataclass
class DepositAddress:
    """Deposit address information"""
    address: str
    network: NetworkType
    currency: str
    tag: Optional[str] = None
    memo: Optional[str] = None
    min_deposit: Optional[Decimal] = None
    confirmations_required: int = 6

@dataclass
class WithdrawalRequest:
    """Withdrawal request information"""
    currency: str
    amount: Decimal
    address: str
    network: NetworkType
    tag: Optional[str] = None
    memo: Optional[str] = None
    fee: Optional[Decimal] = None
    user_id: int
    two_fa_code: Optional[str] = None

@dataclass
class Transaction:
    """Transaction record"""
    id: str
    user_id: int
    exchange: str
    currency: str
    amount: Decimal
    fee: Decimal
    status: TransactionStatus
    transaction_type: TransactionType
    network: NetworkType
    address: str
    tag: Optional[str]
    memo: Optional[str]
    tx_hash: Optional[str]
    confirmations: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]

class ExchangeAPI:
    """Base class for exchange API integration"""
    
    def __init__(self, exchange_name: str, api_key: str, api_secret: str, passphrase: str = None):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _generate_signature(self, method: str, endpoint: str, params: Dict = None, body: str = "") -> Dict[str, str]:
        """Generate API signature - to be implemented by each exchange"""
        raise NotImplementedError
    
    async def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict:
        """Make authenticated API request"""
        if not self.session:
            raise RuntimeError("Session not initialized")
        
        headers = self._generate_signature(method, endpoint, params, json.dumps(data) if data else "")
        
        try:
            async with self.session.request(
                method, 
                endpoint, 
                params=params, 
                json=data, 
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"API request failed for {self.exchange_name}: {e}")
            raise
    
    async def get_deposit_address(self, currency: str, network: str = None) -> DepositAddress:
        """Get deposit address for currency"""
        raise NotImplementedError
    
    async def withdraw(self, request: WithdrawalRequest) -> str:
        """Submit withdrawal request"""
        raise NotImplementedError
    
    async def get_deposit_history(self, currency: str = None, limit: int = 100) -> List[Transaction]:
        """Get deposit history"""
        raise NotImplementedError
    
    async def get_withdrawal_history(self, currency: str = None, limit: int = 100) -> List[Transaction]:
        """Get withdrawal history"""
        raise NotImplementedError
    
    async def get_transaction_status(self, transaction_id: str) -> Transaction:
        """Get transaction status"""
        raise NotImplementedError
    
    async def get_withdrawal_fee(self, currency: str, network: str = None) -> Decimal:
        """Get withdrawal fee"""
        raise NotImplementedError
    
    async def get_supported_currencies(self) -> List[Dict[str, Any]]:
        """Get supported currencies and networks"""
        raise NotImplementedError

class BinanceAPI(ExchangeAPI):
    """Binance API implementation"""
    
    def __init__(self, api_key: str, api_secret: str):
        super().__init__("binance", api_key, api_secret)
        self.base_url = "https://api.binance.com"
    
    def _generate_signature(self, method: str, endpoint: str, params: Dict = None, body: str = "") -> Dict[str, str]:
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        
        if params:
            query_string += "&" + "&".join([f"{k}={v}" for k, v in params.items()])
        
        if body:
            query_string += "&" + body
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json",
            "signature": signature,
            "timestamp": str(timestamp)
        }
    
    async def get_deposit_address(self, currency: str, network: str = None) -> DepositAddress:
        endpoint = f"{self.base_url}/sapi/v1/capital/deposit/address"
        params = {"coin": currency}
        if network:
            params["network"] = network
        
        response = await self._make_request("GET", endpoint, params)
        
        return DepositAddress(
            address=response["address"],
            network=NetworkType(response.get("network", "NATIVE")),
            currency=currency,
            tag=response.get("tag"),
            memo=response.get("memo")
        )
    
    async def withdraw(self, request: WithdrawalRequest) -> str:
        endpoint = f"{self.base_url}/sapi/v1/capital/withdraw/apply"
        data = {
            "coin": request.currency,
            "address": request.address,
            "amount": str(request.amount),
            "network": request.network.value
        }
        
        if request.tag:
            data["addressTag"] = request.tag
        if request.memo:
            data["memo"] = request.memo
        
        response = await self._make_request("POST", endpoint, data=data)
        return response["id"]
    
    async def get_deposit_history(self, currency: str = None, limit: int = 100) -> List[Transaction]:
        endpoint = f"{self.base_url}/sapi/v1/capital/deposit/hisrec"
        params = {"limit": limit}
        if currency:
            params["coin"] = currency
        
        response = await self._make_request("GET", endpoint, params)
        
        transactions = []
        for item in response:
            transactions.append(Transaction(
                id=item["id"],
                user_id=0,  # Will be set by service
                exchange="binance",
                currency=item["coin"],
                amount=Decimal(item["amount"]),
                fee=Decimal("0"),
                status=TransactionStatus(item["status"].lower()),
                transaction_type=TransactionType.DEPOSIT,
                network=NetworkType(item.get("network", "NATIVE")),
                address=item["address"],
                tag=item.get("addressTag"),
                memo=item.get("memo"),
                tx_hash=item.get("txId"),
                confirmations=item.get("confirmTimes", 0),
                created_at=datetime.fromtimestamp(item["insertTime"] / 1000),
                updated_at=datetime.now(),
                completed_at=datetime.fromtimestamp(item["insertTime"] / 1000) if item["status"] == "1" else None,
                error_message=None
            ))
        
        return transactions

class OKXAPI(ExchangeAPI):
    """OKX API implementation"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str):
        super().__init__("okx", api_key, api_secret, passphrase)
        self.base_url = "https://www.okx.com"
    
    def _generate_signature(self, method: str, endpoint: str, params: Dict = None, body: str = "") -> Dict[str, str]:
        timestamp = datetime.utcnow().isoformat() + "Z"
        message = timestamp + method + endpoint + body
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        import base64
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature_b64,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
    
    async def get_deposit_address(self, currency: str, network: str = None) -> DepositAddress:
        endpoint = f"{self.base_url}/api/v5/asset/deposit-address"
        params = {"ccy": currency}
        if network:
            params["chain"] = network
        
        response = await self._make_request("GET", endpoint, params)
        data = response["data"][0]
        
        return DepositAddress(
            address=data["addr"],
            network=NetworkType(data.get("chain", "NATIVE")),
            currency=currency,
            tag=data.get("tag"),
            memo=data.get("memo")
        )

class DepositWithdrawalService:
    """Service for managing deposits and withdrawals across multiple exchanges"""
    
    def __init__(self):
        self.exchanges: Dict[str, ExchangeAPI] = {}
        self.redis_client = None
        self.transaction_cache_ttl = 3600  # 1 hour
        
    async def initialize(self):
        """Initialize the service"""
        self.redis_client = await get_redis_client()
        
        # Initialize exchange APIs based on user configurations
        # This would be loaded from user settings in a real implementation
        await self._load_exchange_apis()
        
        logger.info("Deposit/Withdrawal service initialized")
    
    async def _load_exchange_apis(self):
        """Load exchange API configurations"""
        # This would load from database/config in real implementation
        # For now, we'll use placeholder configurations
        pass
    
    async def add_exchange_api(self, user_id: int, exchange: str, api_key: str, api_secret: str, passphrase: str = None):
        """Add exchange API for a user"""
        key = f"{user_id}:{exchange}"
        
        if exchange.lower() == "binance":
            self.exchanges[key] = BinanceAPI(api_key, api_secret)
        elif exchange.lower() == "okx":
            self.exchanges[key] = OKXAPI(api_key, api_secret, passphrase)
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")
        
        logger.info(f"Added {exchange} API for user {user_id}")
    
    async def get_deposit_address(self, user_id: int, exchange: str, currency: str, network: str = None) -> DepositAddress:
        """Get deposit address for user"""
        api = self._get_exchange_api(user_id, exchange)
        
        # Check cache first
        cache_key = f"deposit_address:{user_id}:{exchange}:{currency}:{network or 'default'}"
        cached = await self.redis_client.get(cache_key)
        
        if cached:
            data = json.loads(cached)
            return DepositAddress(**data)
        
        # Get from exchange
        async with api:
            address = await api.get_deposit_address(currency, network)
        
        # Cache the result
        await self.redis_client.setex(
            cache_key,
            self.transaction_cache_ttl,
            json.dumps({
                "address": address.address,
                "network": address.network.value,
                "currency": address.currency,
                "tag": address.tag,
                "memo": address.memo,
                "min_deposit": str(address.min_deposit) if address.min_deposit else None,
                "confirmations_required": address.confirmations_required
            })
        )
        
        return address
    
    async def submit_withdrawal(self, user_id: int, exchange: str, request: WithdrawalRequest) -> str:
        """Submit withdrawal request"""
        api = self._get_exchange_api(user_id, exchange)
        
        # Validate withdrawal request
        await self._validate_withdrawal_request(user_id, request)
        
        # Submit withdrawal
        async with api:
            transaction_id = await api.withdraw(request)
        
        # Store transaction record
        await self._store_transaction_record(user_id, exchange, transaction_id, request)
        
        logger.info(f"Withdrawal submitted for user {user_id}: {transaction_id}")
        return transaction_id
    
    async def get_deposit_history(self, user_id: int, exchange: str, currency: str = None, limit: int = 100) -> List[Transaction]:
        """Get deposit history for user"""
        api = self._get_exchange_api(user_id, exchange)
        
        async with api:
            transactions = await api.get_deposit_history(currency, limit)
        
        # Set user_id for all transactions
        for tx in transactions:
            tx.user_id = user_id
        
        return transactions
    
    async def get_withdrawal_history(self, user_id: int, exchange: str, currency: str = None, limit: int = 100) -> List[Transaction]:
        """Get withdrawal history for user"""
        api = self._get_exchange_api(user_id, exchange)
        
        async with api:
            transactions = await api.get_withdrawal_history(currency, limit)
        
        # Set user_id for all transactions
        for tx in transactions:
            tx.user_id = user_id
        
        return transactions
    
    async def get_transaction_status(self, user_id: int, exchange: str, transaction_id: str) -> Transaction:
        """Get transaction status"""
        api = self._get_exchange_api(user_id, exchange)
        
        async with api:
            transaction = await api.get_transaction_status(transaction_id)
        
        transaction.user_id = user_id
        return transaction
    
    async def get_withdrawal_fee(self, user_id: int, exchange: str, currency: str, network: str = None) -> Decimal:
        """Get withdrawal fee"""
        api = self._get_exchange_api(user_id, exchange)
        
        # Check cache first
        cache_key = f"withdrawal_fee:{exchange}:{currency}:{network or 'default'}"
        cached = await self.redis_client.get(cache_key)
        
        if cached:
            return Decimal(cached)
        
        # Get from exchange
        async with api:
            fee = await api.get_withdrawal_fee(currency, network)
        
        # Cache for 1 hour
        await self.redis_client.setex(cache_key, 3600, str(fee))
        
        return fee
    
    async def get_supported_currencies(self, user_id: int, exchange: str) -> List[Dict[str, Any]]:
        """Get supported currencies for exchange"""
        api = self._get_exchange_api(user_id, exchange)
        
        # Check cache first
        cache_key = f"supported_currencies:{exchange}"
        cached = await self.redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        # Get from exchange
        async with api:
            currencies = await api.get_supported_currencies()
        
        # Cache for 24 hours
        await self.redis_client.setex(cache_key, 86400, json.dumps(currencies))
        
        return currencies
    
    async def unified_deposit_withdrawal(self, user_id: int, source_exchange: str, target_exchange: str, 
                                       currency: str, amount: Decimal, network: str = None) -> Tuple[str, str]:
        """Unified deposit/withdrawal: withdraw from source and deposit to target"""
        # Get deposit address for target exchange
        target_address = await self.get_deposit_address(user_id, target_exchange, currency, network)
        
        # Create withdrawal request
        withdrawal_request = WithdrawalRequest(
            currency=currency,
            amount=amount,
            address=target_address.address,
            network=target_address.network,
            tag=target_address.tag,
            memo=target_address.memo,
            user_id=user_id
        )
        
        # Submit withdrawal from source
        withdrawal_id = await self.submit_withdrawal(user_id, source_exchange, withdrawal_request)
        
        # Monitor the transaction
        monitor_task = asyncio.create_task(
            self._monitor_unified_transaction(user_id, source_exchange, target_exchange, withdrawal_id)
        )
        
        logger.info(f"Unified transfer initiated: {source_exchange} -> {target_exchange}, amount: {amount} {currency}")
        
        return withdrawal_id, target_address.address
    
    async def _monitor_unified_transaction(self, user_id: int, source_exchange: str, target_exchange: str, transaction_id: str):
        """Monitor unified transaction progress"""
        max_attempts = 720  # 1 hour with 5-second intervals
        attempt = 0
        
        while attempt < max_attempts:
            try:
                transaction = await self.get_transaction_status(user_id, source_exchange, transaction_id)
                
                if transaction.status == TransactionStatus.COMPLETED:
                    logger.info(f"Unified transaction completed: {transaction_id}")
                    break
                elif transaction.status == TransactionStatus.FAILED:
                    logger.error(f"Unified transaction failed: {transaction_id} - {transaction.error_message}")
                    break
                
                await asyncio.sleep(5)
                attempt += 1
                
            except Exception as e:
                logger.error(f"Error monitoring transaction {transaction_id}: {e}")
                await asyncio.sleep(10)
                attempt += 2
    
    def _get_exchange_api(self, user_id: int, exchange: str) -> ExchangeAPI:
        """Get exchange API for user"""
        key = f"{user_id}:{exchange}"
        if key not in self.exchanges:
            raise ValueError(f"Exchange API not configured for user {user_id} and exchange {exchange}")
        return self.exchanges[key]
    
    async def _validate_withdrawal_request(self, user_id: int, request: WithdrawalRequest):
        """Validate withdrawal request"""
        # Check minimum withdrawal amount
        if request.amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        
        # Check withdrawal fee
        fee = await self.get_withdrawal_fee(user_id, "binance", request.currency, request.network.value)
        if request.amount <= fee:
            raise ValueError(f"Withdrawal amount must be greater than fee: {fee}")
        
        # Additional validations can be added here
        # - Check user balance
        # - Check daily withdrawal limits
        # - Verify address format
        # - Check 2FA if required
    
    async def _store_transaction_record(self, user_id: int, exchange: str, transaction_id: str, request: WithdrawalRequest):
        """Store transaction record in database"""
        # This would store the transaction in the database
        # For now, we'll just log it
        logger.info(f"Transaction record stored: {transaction_id} for user {user_id}")

# Global service instance
deposit_withdrawal_service = DepositWithdrawalService()