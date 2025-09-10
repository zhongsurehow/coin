"""认证和授权模块

提供JWT token验证、用户认证等功能。
"""

import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from passlib.context import CryptContext

from ..core.config import settings
from ..services.logging_service import logging_service

logger = logging.getLogger(__name__)

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """认证服务"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        self.refresh_token_expire_days = 7
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """获取密码哈希"""
        return pwd_context.hash(password)
    
    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        return encoded_jwt
    
    def create_refresh_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建刷新令牌"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.JWTError as e:
            logger.warning(f"Token验证失败: {e}")
            return None
    
    def get_user_id_from_token(self, token: str) -> Optional[int]:
        """从令牌中获取用户ID"""
        payload = self.verify_token(token)
        if payload:
            return payload.get("user_id")
        return None
    
    async def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """认证用户"""
        try:
            # 这里应该从数据库查询用户信息
            # 暂时使用模拟数据
            if username == "admin" and password == "admin123":
                user_data = {
                    "user_id": 1,
                    "username": "admin",
                    "email": "admin@example.com",
                    "is_active": True,
                    "role": "admin"
                }
                
                # 记录登录日志
                await logging_service.log_user_action(
                    user_id=1,
                    action="login",
                    details={"username": username}
                )
                
                return user_data
            
            # 记录失败的登录尝试
            await logging_service.log_user_action(
                user_id=None,
                action="login_failed",
                details={"username": username}
            )
            
            return None
            
        except Exception as e:
            logger.error(f"用户认证失败: {e}")
            return None
    
    async def create_user_tokens(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """为用户创建令牌"""
        access_token_data = {
            "user_id": user_data["user_id"],
            "username": user_data["username"],
            "role": user_data.get("role", "user")
        }
        
        refresh_token_data = {
            "user_id": user_data["user_id"],
            "username": user_data["username"]
        }
        
        access_token = self.create_access_token(access_token_data)
        refresh_token = self.create_refresh_token(refresh_token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """刷新访问令牌"""
        payload = self.verify_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            return None
        
        # 创建新的访问令牌
        access_token_data = {
            "user_id": payload["user_id"],
            "username": payload["username"],
            "role": payload.get("role", "user")
        }
        
        new_access_token = self.create_access_token(access_token_data)
        
        # 记录令牌刷新日志
        await logging_service.log_user_action(
            user_id=payload["user_id"],
            action="token_refresh",
            details={"username": payload["username"]}
        )
        
        return new_access_token


# 全局认证服务实例
auth_service = AuthService()


# 便捷函数
def get_user_id_from_token(token: str) -> int:
    """从令牌获取用户ID（用于WebSocket等场景）"""
    user_id = auth_service.get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return user_id


def verify_token(token: str) -> Dict[str, Any]:
    """验证令牌"""
    payload = auth_service.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return payload


async def get_current_user(token: str) -> Dict[str, Any]:
    """获取当前用户信息"""
    payload = verify_token(token)
    
    # 这里应该从数据库查询完整的用户信息
    # 暂时返回令牌中的信息
    user_data = {
        "user_id": payload["user_id"],
        "username": payload["username"],
        "role": payload.get("role", "user")
    }
    
    return user_data


class RoleChecker:
    """角色检查器"""
    
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles
    
    def __call__(self, current_user: Dict[str, Any]) -> bool:
        if current_user.get("role") in self.allowed_roles:
            return True
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )


# 角色检查器实例
require_admin = RoleChecker(["admin"])
require_user = RoleChecker(["user", "admin"])
require_trader = RoleChecker(["trader", "admin"])