from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import uuid

from .database import Base

# 枚举定义
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    TRADER = "trader"
    VIEWER = "viewer"

class StrategyStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"

class TradeStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"

class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"

class TransactionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(str, Enum):
    POSITION_SIZE = "position_size"
    DRAWDOWN = "drawdown"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    PRICE_DEVIATION = "price_deviation"
    SYSTEM_ERROR = "system_error"

# 数据库模型
class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(String(20), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 个人信息
    first_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # 配置
    api_keys: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    risk_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    notification_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ui_preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 关系
    strategies = relationship("Strategy", back_populates="user")
    trades = relationship("Trade", back_populates="user")
    deposits_withdraws = relationship("DepositWithdraw", back_populates="user")
    risk_alerts = relationship("RiskAlert", back_populates="user")

class Exchange(Base):
    """交易所模型"""
    __tablename__ = "exchanges"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # API配置
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    websocket_endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    testnet_endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # 功能支持
    supported_features: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    rate_limits: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    fees: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    trading_pairs = relationship("TradingPair", back_populates="exchange")

class TradingPair(Base):
    """交易对模型"""
    __tablename__ = "trading_pairs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    base_asset: Mapped[str] = mapped_column(String(10))
    quote_asset: Mapped[str] = mapped_column(String(10))
    exchange_id: Mapped[int] = mapped_column(Integer, ForeignKey("exchanges.id"), index=True)
    
    # 交易规则
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_trade_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_trade_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_precision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quantity_precision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 统计信息
    volume_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_change_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    exchange = relationship("Exchange", back_populates="trading_pairs")

class ArbitrageOpportunity(Base):
    """套利机会模型"""
    __tablename__ = "arbitrage_opportunities"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    
    # 交易所信息
    buy_exchange: Mapped[str] = mapped_column(String(50))
    sell_exchange: Mapped[str] = mapped_column(String(50))
    
    # 价格信息
    buy_price: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    spread: Mapped[float] = mapped_column(Float)
    
    # 利润信息
    profit_amount: Mapped[float] = mapped_column(Float)
    profit_percentage: Mapped[float] = mapped_column(Float)
    estimated_profit: Mapped[float] = mapped_column(Float)
    
    # 交易量信息
    volume: Mapped[float] = mapped_column(Float)
    max_volume: Mapped[float] = mapped_column(Float)
    
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="detected")
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # 时间信息
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 市场数据
    market_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    execution_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    risk_assessment: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

class Strategy(Base):
    """策略模型"""
    __tablename__ = "strategies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_type: Mapped[str] = mapped_column(String(50))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    
    # 状态
    status: Mapped[StrategyStatus] = mapped_column(String(20), default=StrategyStatus.STOPPED)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # 配置
    config: Mapped[Dict[str, Any]] = mapped_column(JSON)
    risk_parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    trading_pairs: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    exchanges: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    
    # 资金管理
    initial_capital: Mapped[float] = mapped_column(Float, default=0.0)
    current_capital: Mapped[float] = mapped_column(Float, default=0.0)
    max_position_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # 性能指标
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    successful_trades: Mapped[int] = mapped_column(Integer, default=0)
    failed_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_profit: Mapped[float] = mapped_column(Float, default=0.0)
    total_loss: Mapped[float] = mapped_column(Float, default=0.0)
    total_volume: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_trade_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Hummingbot集成
    hummingbot_instance_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hummingbot_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # 关系
    user = relationship("User", back_populates="strategies")
    trades = relationship("Trade", back_populates="strategy")
    risk_alerts = relationship("RiskAlert", back_populates="strategy")

class Trade(Base):
    """交易记录模型"""
    __tablename__ = "trades"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trade_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # 关联
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("strategies.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    arbitrage_opportunity_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("arbitrage_opportunities.id"), nullable=True)
    
    # 交易信息
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[str] = mapped_column(String(10))  # buy/sell
    exchange: Mapped[str] = mapped_column(String(50))
    order_type: Mapped[str] = mapped_column(String(20))
    
    # 价格和数量
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    
    # 金额
    total_amount: Mapped[float] = mapped_column(Float)
    filled_amount: Mapped[float] = mapped_column(Float, default=0.0)
    
    # 状态和费用
    status: Mapped[TradeStatus] = mapped_column(String(20), default=TradeStatus.PENDING)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    fee_currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # 外部ID
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 执行信息
    average_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 额外数据
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 关系
    strategy = relationship("Strategy", back_populates="trades")
    user = relationship("User", back_populates="trades")

class DepositWithdraw(Base):
    """充提记录模型"""
    __tablename__ = "deposit_withdraws"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transaction_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    
    # 基本信息
    transaction_type: Mapped[TransactionType] = mapped_column(String(10))
    currency: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    net_amount: Mapped[float] = mapped_column(Float)
    
    # 交易所信息
    exchange: Mapped[str] = mapped_column(String(50))
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    memo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 状态和ID
    status: Mapped[TransactionStatus] = mapped_column(String(20), default=TransactionStatus.PENDING)
    exchange_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    blockchain_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 网络信息
    network: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confirmations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    required_confirmations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 额外信息
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 关系
    user = relationship("User", back_populates="deposits_withdraws")

class RiskAlert(Base):
    """风险警报模型"""
    __tablename__ = "risk_alerts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # 关联
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("strategies.id"), nullable=True, index=True)
    
    # 警报信息
    alert_type: Mapped[AlertType] = mapped_column(String(50))
    risk_level: Mapped[RiskLevel] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    
    # 相关数据
    exchange: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    trading_pair: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    current_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="active")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 额外数据
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # 关系
    user = relationship("User", back_populates="risk_alerts")
    strategy = relationship("Strategy", back_populates="risk_alerts")

class SystemLog(Base):
    """系统日志模型"""
    __tablename__ = "system_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    log_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # 日志信息
    level: Mapped[str] = mapped_column(String(20), index=True)
    message: Mapped[str] = mapped_column(Text)
    module: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    function: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 关联信息
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 请求信息
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    # 额外数据
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class ApiKey(Base):
    """API密钥模型"""
    __tablename__ = "api_keys"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    
    # 密钥信息
    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(10))
    
    # 权限
    permissions: Mapped[List[str]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # 使用统计
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 限制
    rate_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 导出所有模型
__all__ = [
    "User", "Exchange", "TradingPair", "ArbitrageOpportunity", "Strategy",
    "Trade", "DepositWithdraw", "RiskAlert", "SystemLog", "ApiKey",
    "UserRole", "StrategyStatus", "TradeStatus", "TransactionType",
    "TransactionStatus", "RiskLevel", "AlertType"
]