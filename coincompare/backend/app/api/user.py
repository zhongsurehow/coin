from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import jwt
from passlib.context import CryptContext

from ..models.user import User, UserRole
from ..database import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, EmailStr, validator

logger = logging.getLogger(__name__)
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()

# JWT settings
SECRET_KEY = "your-secret-key-here"  # Should be in config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Pydantic models for API
class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password")
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    
    @validator('username')
    def validate_username(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v

class UserLoginRequest(BaseModel):
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    email_verified: bool
    two_factor_enabled: bool
    created_at: datetime
    last_login: Optional[datetime]
    trading_settings: Dict[str, Any]
    preferences: Dict[str, Any]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse

class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    trading_settings: Optional[Dict[str, Any]] = Field(None, description="Trading settings")
    preferences: Optional[Dict[str, Any]] = Field(None, description="User preferences")

class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")

class TradingSettingsRequest(BaseModel):
    max_position_size: Optional[float] = Field(None, gt=0, description="Maximum position size")
    daily_loss_limit: Optional[float] = Field(None, gt=0, description="Daily loss limit")
    max_daily_trades: Optional[int] = Field(None, gt=0, description="Maximum daily trades")
    risk_level: Optional[str] = Field(None, description="Risk level (low, medium, high)")
    auto_stop_loss: Optional[bool] = Field(None, description="Enable auto stop loss")
    stop_loss_percentage: Optional[float] = Field(None, gt=0, le=100, description="Stop loss percentage")
    
    @validator('risk_level')
    def validate_risk_level(cls, v):
        if v is not None and v not in ['low', 'medium', 'high']:
            raise ValueError('Risk level must be low, medium, or high')
        return v

class ExchangeAPICredentials(BaseModel):
    exchange: str = Field(..., description="Exchange name")
    api_key: str = Field(..., description="API key")
    api_secret: str = Field(..., description="API secret")
    passphrase: Optional[str] = Field(None, description="API passphrase")
    sandbox: bool = Field(False, description="Use sandbox environment")

class TwoFactorSetupRequest(BaseModel):
    enable: bool = Field(..., description="Enable or disable 2FA")
    totp_code: Optional[str] = Field(None, description="TOTP code for verification")

class UserStatsResponse(BaseModel):
    total_trades: int
    total_profit: float
    win_rate: float
    active_strategies: int
    total_strategies: int
    account_age_days: int
    last_activity: Optional[datetime]

# Helper functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return int(user_id)

@router.post("/register", response_model=TokenResponse)
async def register_user(
    request: UserRegisterRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Register a new user"""
    try:
        # Check if username or email already exists
        existing_user_query = select(User).where(
            (User.username == request.username) | (User.email == request.email)
        )
        result = await db.execute(existing_user_query)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            if existing_user.username == request.username:
                raise HTTPException(status_code=400, detail="Username already registered")
            else:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create new user
        hashed_password = pwd_context.hash(request.password)
        user = User(
            username=request.username,
            email=request.email,
            full_name=request.full_name,
            hashed_password=hashed_password,
            role=UserRole.USER,
            is_active=True,
            email_verified=False,
            two_factor_enabled=False
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            email_verified=user.email_verified,
            two_factor_enabled=user.two_factor_enabled,
            created_at=user.created_at,
            last_login=user.last_login,
            trading_settings=user.trading_settings,
            preferences=user.preferences
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_response
        )
    
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", response_model=TokenResponse)
async def login_user(
    request: UserLoginRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Login user"""
    try:
        # Find user by username or email
        user_query = select(User).where(
            (User.username == request.username) | (User.email == request.username)
        )
        result = await db.execute(user_query)
        user = result.scalar_one_or_none()
        
        if not user or not user.verify_password(request.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        
        # Update last login
        user.last_login = datetime.utcnow()
        await db.commit()
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            email_verified=user.email_verified,
            two_factor_enabled=user.two_factor_enabled,
            created_at=user.created_at,
            last_login=user.last_login,
            trading_settings=user.trading_settings,
            preferences=user.preferences
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_response
        )
    
    except Exception as e:
        logger.error(f"Error logging in user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Get current user information"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            email_verified=user.email_verified,
            two_factor_enabled=user.two_factor_enabled,
            created_at=user.created_at,
            last_login=user.last_login,
            trading_settings=user.trading_settings,
            preferences=user.preferences
        )
    
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    request: UserUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Update current user information"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if email is already taken by another user
        if request.email and request.email != user.email:
            email_query = select(User).where(
                (User.email == request.email) & (User.id != user_id)
            )
            email_result = await db.execute(email_query)
            existing_email = email_result.scalar_one_or_none()
            if existing_email:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await db.commit()
        await db.refresh(user)
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            email_verified=user.email_verified,
            two_factor_enabled=user.two_factor_enabled,
            created_at=user.created_at,
            last_login=user.last_login,
            trading_settings=user.trading_settings,
            preferences=user.preferences
        )
    
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Change user password"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user.verify_password(request.current_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        user.hashed_password = pwd_context.hash(request.new_password)
        await db.commit()
        
        return {"message": "Password changed successfully"}
    
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/trading-settings", response_model=Dict[str, Any])
async def update_trading_settings(
    request: TradingSettingsRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Update user trading settings"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update trading settings
        current_settings = user.trading_settings or {}
        update_data = request.dict(exclude_unset=True)
        current_settings.update(update_data)
        user.trading_settings = current_settings
        
        await db.commit()
        
        return user.trading_settings
    
    except Exception as e:
        logger.error(f"Error updating trading settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/exchange-credentials")
async def add_exchange_credentials(
    request: ExchangeAPICredentials,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Add exchange API credentials"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Encrypt and store credentials
        encrypted_credentials = user.encrypt_api_credentials(
            exchange=request.exchange,
            api_key=request.api_key,
            api_secret=request.api_secret,
            passphrase=request.passphrase,
            sandbox=request.sandbox
        )
        
        # Update user's exchange credentials
        current_credentials = user.exchange_credentials or {}
        current_credentials[request.exchange] = encrypted_credentials
        user.exchange_credentials = current_credentials
        
        await db.commit()
        
        return {"message": f"Successfully added {request.exchange} credentials"}
    
    except Exception as e:
        logger.error(f"Error adding exchange credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/exchange-credentials")
async def get_exchange_credentials(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user's exchange credentials (without sensitive data)"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Return only exchange names and basic info, not the actual credentials
        credentials_info = {}
        if user.exchange_credentials:
            for exchange, creds in user.exchange_credentials.items():
                credentials_info[exchange] = {
                    "configured": True,
                    "sandbox": creds.get("sandbox", False),
                    "created_at": creds.get("created_at"),
                    "last_used": creds.get("last_used")
                }
        
        return {"exchanges": credentials_info}
    
    except Exception as e:
        logger.error(f"Error getting exchange credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/exchange-credentials/{exchange}")
async def remove_exchange_credentials(
    exchange: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Remove exchange API credentials"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user.exchange_credentials and exchange in user.exchange_credentials:
            del user.exchange_credentials[exchange]
            await db.commit()
            return {"message": f"Successfully removed {exchange} credentials"}
        else:
            raise HTTPException(status_code=404, detail="Exchange credentials not found")
    
    except Exception as e:
        logger.error(f"Error removing exchange credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/2fa/setup")
async def setup_two_factor(
    request: TwoFactorSetupRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Setup or disable two-factor authentication"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if request.enable:
            # Enable 2FA - would normally verify TOTP code here
            if not request.totp_code:
                # Generate QR code for initial setup
                import pyotp
                secret = pyotp.random_base32()
                totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
                    name=user.email,
                    issuer_name="CoinCompare"
                )
                
                return {
                    "qr_code_uri": totp_uri,
                    "secret": secret,
                    "message": "Scan QR code with authenticator app and provide TOTP code"
                }
            else:
                # Verify TOTP code and enable 2FA
                # This would normally verify the provided TOTP code
                user.two_factor_enabled = True
                user.two_factor_secret = "encrypted_secret_here"  # Would encrypt the secret
                await db.commit()
                
                return {"message": "Two-factor authentication enabled successfully"}
        else:
            # Disable 2FA
            user.two_factor_enabled = False
            user.two_factor_secret = None
            await db.commit()
            
            return {"message": "Two-factor authentication disabled successfully"}
    
    except Exception as e:
        logger.error(f"Error setting up 2FA: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=UserStatsResponse)
async def get_user_stats(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user statistics"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Calculate user statistics
        # This would normally query the database for actual stats
        account_age = (datetime.utcnow() - user.created_at).days
        
        return UserStatsResponse(
            total_trades=150,  # Mock data
            total_profit=2500.75,
            win_rate=0.68,
            active_strategies=3,
            total_strategies=8,
            account_age_days=account_age,
            last_activity=user.last_login
        )
    
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/logout")
async def logout_user(
    user_id: int = Depends(get_current_user_id)
):
    """Logout user (invalidate token)"""
    # In a real implementation, you would add the token to a blacklist
    # For now, just return success
    return {"message": "Successfully logged out"}

@router.get("/permissions")
async def get_user_permissions(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user permissions"""
    try:
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        permissions = {
            "can_trade": user.has_permission("trade"),
            "can_manage_strategies": user.has_permission("manage_strategies"),
            "can_view_analytics": user.has_permission("view_analytics"),
            "can_manage_api_keys": user.has_permission("manage_api_keys"),
            "can_withdraw": user.has_permission("withdraw"),
            "is_admin": user.role == UserRole.ADMIN
        }
        
        return {"permissions": permissions}
    
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))