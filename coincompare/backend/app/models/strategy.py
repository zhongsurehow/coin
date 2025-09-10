from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import BaseModel

class StrategyType(enum.Enum):
    ARBITRAGE = "arbitrage"
    MARKET_MAKING = "market_making"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    CUSTOM = "custom"

class StrategyStatus(enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

class ExecutionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Strategy(BaseModel):
    __tablename__ = "strategies"
    
    # Basic info
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    strategy_type = Column(Enum(StrategyType), nullable=False)
    
    # Configuration
    config = Column(JSON, nullable=False, default={})
    
    # Risk parameters
    max_position_size = Column(Float, default=1000.0)  # USD
    max_daily_volume = Column(Float, default=10000.0)  # USD
    stop_loss_percentage = Column(Float, default=5.0)  # 5%
    take_profit_percentage = Column(Float, default=10.0)  # 10%
    
    # Execution parameters
    min_profit_threshold = Column(Float, default=0.5)  # 0.5%
    max_slippage = Column(Float, default=0.1)  # 0.1%
    order_timeout = Column(Integer, default=30)  # seconds
    
    # Status and control
    status = Column(Enum(StrategyStatus), default=StrategyStatus.DRAFT)
    is_active = Column(Boolean, default=False)
    auto_execute = Column(Boolean, default=False)
    
    # Performance tracking
    total_trades = Column(Integer, default=0)
    successful_trades = Column(Integer, default=0)
    total_profit = Column(Float, default=0.0)
    total_fees = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    
    # Timing
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    last_execution_at = Column(DateTime)
    
    # Hummingbot integration
    hummingbot_strategy_id = Column(String(100))
    hummingbot_config = Column(JSON)
    
    # Relationships
    user = relationship("User", back_populates="strategies")
    executions = relationship("StrategyExecution", back_populates="strategy")
    trades = relationship("ArbitrageTrade", back_populates="strategy")
    
    def start(self):
        """Start the strategy"""
        self.status = StrategyStatus.ACTIVE
        self.is_active = True
        self.started_at = datetime.utcnow()
    
    def stop(self):
        """Stop the strategy"""
        self.status = StrategyStatus.STOPPED
        self.is_active = False
        self.stopped_at = datetime.utcnow()
    
    def pause(self):
        """Pause the strategy"""
        self.status = StrategyStatus.PAUSED
        self.is_active = False
    
    def resume(self):
        """Resume the strategy"""
        self.status = StrategyStatus.ACTIVE
        self.is_active = True
    
    def update_performance(self, trade_result: dict):
        """Update strategy performance metrics"""
        self.total_trades += 1
        
        if trade_result.get('success', False):
            self.successful_trades += 1
            self.total_profit += trade_result.get('profit', 0.0)
        
        self.total_fees += trade_result.get('fees', 0.0)
        self.last_execution_at = datetime.utcnow()
        
        # Update max drawdown if needed
        current_drawdown = trade_result.get('drawdown', 0.0)
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
    
    def get_success_rate(self) -> float:
        """Calculate strategy success rate"""
        if self.total_trades == 0:
            return 0.0
        return (self.successful_trades / self.total_trades) * 100
    
    def get_net_profit(self) -> float:
        """Calculate net profit after fees"""
        return self.total_profit - self.total_fees
    
    def get_roi(self) -> float:
        """Calculate return on investment"""
        if self.max_position_size == 0:
            return 0.0
        return (self.get_net_profit() / self.max_position_size) * 100
    
    def can_execute(self) -> bool:
        """Check if strategy can execute trades"""
        return (
            self.status == StrategyStatus.ACTIVE and
            self.is_active and
            self.user.can_trade()
        )
    
    def validate_config(self) -> dict:
        """Validate strategy configuration"""
        errors = []
        
        if self.strategy_type == StrategyType.ARBITRAGE:
            required_fields = ['exchanges', 'trading_pairs', 'min_profit']
            for field in required_fields:
                if field not in self.config:
                    errors.append(f"Missing required field: {field}")
        
        if self.max_position_size <= 0:
            errors.append("Max position size must be positive")
        
        if self.min_profit_threshold < 0:
            errors.append("Min profit threshold cannot be negative")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

class StrategyExecution(BaseModel):
    __tablename__ = "strategy_executions"
    
    # Foreign keys
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # Execution info
    execution_id = Column(String(100), unique=True, nullable=False)
    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)
    
    # Trigger info
    trigger_type = Column(String(50))  # 'manual', 'auto', 'scheduled'
    trigger_data = Column(JSON)
    
    # Execution details
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)
    
    # Results
    trades_executed = Column(Integer, default=0)
    total_volume = Column(Float, default=0.0)
    gross_profit = Column(Float, default=0.0)
    net_profit = Column(Float, default=0.0)
    fees_paid = Column(Float, default=0.0)
    
    # Error handling
    error_message = Column(Text)
    error_details = Column(JSON)
    
    # Metadata
    execution_log = Column(JSON, default=[])
    performance_metrics = Column(JSON, default={})
    
    # Relationships
    strategy = relationship("Strategy", back_populates="executions")
    
    def start_execution(self):
        """Mark execution as started"""
        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.utcnow()
    
    def complete_execution(self, success: bool = True):
        """Mark execution as completed"""
        self.status = ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED
        self.completed_at = datetime.utcnow()
        
        if self.started_at:
            duration = self.completed_at - self.started_at
            self.duration_seconds = duration.total_seconds()
    
    def add_log_entry(self, level: str, message: str, data: dict = None):
        """Add entry to execution log"""
        if not self.execution_log:
            self.execution_log = []
        
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message
        }
        
        if data:
            entry['data'] = data
        
        self.execution_log.append(entry)
    
    def update_metrics(self, metrics: dict):
        """Update performance metrics"""
        if not self.performance_metrics:
            self.performance_metrics = {}
        
        self.performance_metrics.update(metrics)
        self.performance_metrics['last_updated'] = datetime.utcnow().isoformat()
    
    def calculate_roi(self) -> float:
        """Calculate ROI for this execution"""
        if self.total_volume == 0:
            return 0.0
        return (self.net_profit / self.total_volume) * 100