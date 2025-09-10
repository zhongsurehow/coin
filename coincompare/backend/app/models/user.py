from sqlalchemy import Column, String, Boolean, Float, JSON, Enum
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
import enum
from .base import BaseModel

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRole(enum.Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"

class UserStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class User(BaseModel):
    __tablename__ = "users"
    
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    
    # User status and role
    role = Column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
    is_verified = Column(Boolean, default=False)
    
    # Trading settings
    max_position_size = Column(Float, default=1000.0)  # USD
    max_daily_volume = Column(Float, default=10000.0)  # USD
    risk_tolerance = Column(Float, default=0.5)  # 0-1 scale
    
    # Exchange API credentials (encrypted)
    exchange_credentials = Column(JSON, default={})
    
    # User preferences
    preferences = Column(JSON, default={
        "notifications": {
            "email": True,
            "push": True,
            "arbitrage_alerts": True,
            "risk_alerts": True
        },
        "dashboard": {
            "default_view": "overview",
            "refresh_interval": 30,
            "favorite_pairs": []
        }
    })
    
    # Relationships
    strategies = relationship("Strategy", back_populates="user")
    trades = relationship("ArbitrageTrade", back_populates="user")
    risk_assessments = relationship("RiskAssessment", back_populates="user")
    
    def verify_password(self, password: str) -> bool:
        """Verify user password"""
        return pwd_context.verify(password, self.hashed_password)
    
    def set_password(self, password: str):
        """Set user password"""
        self.hashed_password = pwd_context.hash(password)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        permissions = {
            UserRole.ADMIN: ["read", "write", "execute", "admin"],
            UserRole.TRADER: ["read", "write", "execute"],
            UserRole.VIEWER: ["read"]
        }
        return permission in permissions.get(self.role, [])
    
    def can_trade(self) -> bool:
        """Check if user can execute trades"""
        return (
            self.status == UserStatus.ACTIVE and
            self.is_verified and
            self.has_permission("execute")
        )
    
    def get_exchange_credentials(self, exchange: str) -> dict:
        """Get decrypted exchange credentials"""
        # In production, implement proper encryption/decryption
        return self.exchange_credentials.get(exchange, {})
    
    def set_exchange_credentials(self, exchange: str, credentials: dict):
        """Set encrypted exchange credentials"""
        # In production, implement proper encryption
        if not self.exchange_credentials:
            self.exchange_credentials = {}
        self.exchange_credentials[exchange] = credentials
    
    def to_dict(self, include_sensitive=False):
        """Convert to dictionary, optionally excluding sensitive data"""
        data = super().to_dict()
        if not include_sensitive:
            data.pop('hashed_password', None)
            data.pop('exchange_credentials', None)
        return data