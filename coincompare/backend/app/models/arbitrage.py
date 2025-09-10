from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import BaseModel

class ArbitrageStatus(enum.Enum):
    IDENTIFIED = "identified"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TradeStatus(enum.Enum):
    PENDING = "pending"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"

class ArbitrageOpportunity(BaseModel):
    __tablename__ = "arbitrage_opportunities"
    
    # Basic info
    symbol = Column(String(20), nullable=False, index=True)
    base_asset = Column(String(10), nullable=False)
    quote_asset = Column(String(10), nullable=False)
    
    # Exchange info
    buy_exchange = Column(String(20), nullable=False)
    sell_exchange = Column(String(20), nullable=False)
    
    # Price data
    buy_price = Column(Float, nullable=False)
    sell_price = Column(Float, nullable=False)
    price_difference = Column(Float, nullable=False)
    profit_percentage = Column(Float, nullable=False)
    profit_usd = Column(Float, nullable=False)
    
    # Volume and liquidity
    buy_volume = Column(Float, nullable=False)
    sell_volume = Column(Float, nullable=False)
    available_volume = Column(Float, nullable=False)  # Min of buy/sell volume
    recommended_amount = Column(Float, nullable=False)
    
    # Market data
    buy_order_book = Column(JSON)  # Top 5 levels
    sell_order_book = Column(JSON)  # Top 5 levels
    volume_24h = Column(Float)
    
    # Risk assessment
    risk_score = Column(Float, default=0.0)
    risk_factors = Column(JSON, default={})
    
    # Execution info
    status = Column(Enum(ArbitrageStatus), default=ArbitrageStatus.IDENTIFIED)
    execution_time_estimate = Column(Float)  # seconds
    slippage_estimate = Column(Float)  # percentage
    
    # Metadata
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    trades = relationship("ArbitrageTrade", back_populates="opportunity")
    
    def is_expired(self) -> bool:
        """Check if opportunity has expired"""
        return datetime.utcnow() > self.expires_at
    
    def is_profitable(self, min_profit: float = 0.5) -> bool:
        """Check if opportunity meets minimum profit threshold"""
        return self.profit_percentage >= min_profit
    
    def calculate_total_fees(self, trading_fees: dict) -> float:
        """Calculate total trading fees for this opportunity"""
        buy_fee = trading_fees.get(self.buy_exchange, {}).get('taker', 0.001)
        sell_fee = trading_fees.get(self.sell_exchange, {}).get('taker', 0.001)
        
        buy_fee_amount = self.buy_price * self.recommended_amount * buy_fee
        sell_fee_amount = self.sell_price * self.recommended_amount * sell_fee
        
        return buy_fee_amount + sell_fee_amount
    
    def net_profit(self, trading_fees: dict) -> float:
        """Calculate net profit after fees"""
        gross_profit = self.profit_usd
        total_fees = self.calculate_total_fees(trading_fees)
        return gross_profit - total_fees

class ArbitrageTrade(BaseModel):
    __tablename__ = "arbitrage_trades"
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    opportunity_id = Column(Integer, ForeignKey("arbitrage_opportunities.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    
    # Trade info
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # 'buy' or 'sell'
    exchange = Column(String(20), nullable=False)
    
    # Order details
    order_id = Column(String(100))  # Exchange order ID
    order_type = Column(String(20), default="market")  # market, limit
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    
    # Execution details
    filled_quantity = Column(Float, default=0.0)
    average_price = Column(Float)
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)
    
    # Fees and costs
    trading_fee = Column(Float, default=0.0)
    trading_fee_currency = Column(String(10))
    
    # Timing
    submitted_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # P&L
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    
    # Metadata
    error_message = Column(String(500))
    exchange_response = Column(JSON)
    
    # Relationships
    user = relationship("User", back_populates="trades")
    opportunity = relationship("ArbitrageOpportunity", back_populates="trades")
    strategy = relationship("Strategy", back_populates="trades")
    
    def is_filled(self) -> bool:
        """Check if trade is completely filled"""
        return self.status == TradeStatus.FILLED
    
    def fill_percentage(self) -> float:
        """Calculate fill percentage"""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100
    
    def calculate_pnl(self, current_price: float = None) -> dict:
        """Calculate P&L for this trade"""
        if not self.is_filled():
            return {"realized": 0.0, "unrealized": 0.0}
        
        # Realized P&L is already calculated
        realized = self.realized_pnl
        
        # Unrealized P&L if current price is provided
        unrealized = 0.0
        if current_price and self.side == "buy":
            unrealized = (current_price - self.average_price) * self.filled_quantity
        elif current_price and self.side == "sell":
            unrealized = (self.average_price - current_price) * self.filled_quantity
        
        return {"realized": realized, "unrealized": unrealized}
    
    def update_from_exchange_data(self, exchange_data: dict):
        """Update trade from exchange order data"""
        self.filled_quantity = exchange_data.get('filled', self.filled_quantity)
        self.average_price = exchange_data.get('average', self.average_price)
        self.trading_fee = exchange_data.get('fee', {}).get('cost', self.trading_fee)
        self.trading_fee_currency = exchange_data.get('fee', {}).get('currency', self.trading_fee_currency)
        
        # Update status based on exchange status
        exchange_status = exchange_data.get('status', '').lower()
        if exchange_status == 'closed':
            self.status = TradeStatus.FILLED
            self.filled_at = datetime.utcnow()
        elif exchange_status == 'canceled':
            self.status = TradeStatus.CANCELLED
            self.cancelled_at = datetime.utcnow()
        elif exchange_status == 'open' and self.filled_quantity > 0:
            self.status = TradeStatus.PARTIAL_FILLED
        
        self.exchange_response = exchange_data