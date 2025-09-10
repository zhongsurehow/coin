from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List, Optional, Dict, Any
import os
from pathlib import Path

class Settings(BaseSettings):
    """应用程序配置"""
    
    # 应用基本信息
    app_name: str = Field(default="Arbitrage Trading System", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    app_description: str = Field(
        default="Advanced cryptocurrency arbitrage trading platform with Hummingbot integration",
        description="应用描述"
    )
    
    # 环境配置
    environment: str = Field(default="development", description="运行环境")
    debug: bool = Field(default=True, description="调试模式")
    testing: bool = Field(default=False, description="测试模式")
    
    # 服务器配置
    host: str = Field(default="0.0.0.0", description="服务器主机")
    port: int = Field(default=8000, description="服务器端口")
    workers: int = Field(default=1, description="工作进程数")
    
    # 数据库配置
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/arbitrage_db",
        description="数据库连接URL"
    )
    database_echo: bool = Field(default=False, description="数据库SQL日志")
    database_pool_size: int = Field(default=10, description="数据库连接池大小")
    database_max_overflow: int = Field(default=20, description="数据库连接池最大溢出")
    
    # Redis配置
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis连接URL"
    )
    redis_password: Optional[str] = Field(default=None, description="Redis密码")
    redis_db: int = Field(default=0, description="Redis数据库编号")
    redis_cache_ttl: int = Field(default=300, description="Redis缓存TTL（秒）")
    
    # InfluxDB配置（时序数据库）
    influxdb_url: str = Field(
        default="http://localhost:8086",
        description="InfluxDB连接URL"
    )
    influxdb_token: Optional[str] = Field(default=None, description="InfluxDB访问令牌")
    influxdb_org: str = Field(default="arbitrage", description="InfluxDB组织")
    influxdb_bucket: str = Field(default="trading_data", description="InfluxDB存储桶")
    
    # JWT配置
    jwt_secret_key: str = Field(
        default="your-super-secret-jwt-key-change-this-in-production",
        description="JWT密钥"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT算法")
    jwt_access_token_expire_minutes: int = Field(default=30, description="访问令牌过期时间（分钟）")
    jwt_refresh_token_expire_days: int = Field(default=7, description="刷新令牌过期时间（天）")
    
    # 加密配置
    encryption_key: str = Field(
        default="your-encryption-key-32-characters-long",
        description="数据加密密钥"
    )
    password_salt: str = Field(
        default="your-password-salt",
        description="密码盐值"
    )
    
    # CORS配置
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001"
        ],
        description="CORS允许的源"
    )
    cors_allow_credentials: bool = Field(default=True, description="CORS允许凭据")
    cors_allow_methods: List[str] = Field(default=["*"], description="CORS允许的方法")
    cors_allow_headers: List[str] = Field(default=["*"], description="CORS允许的头部")
    
    # 交易所API配置
    # Binance
    binance_api_key: Optional[str] = Field(default=None, description="Binance API密钥")
    binance_api_secret: Optional[str] = Field(default=None, description="Binance API密钥")
    binance_testnet: bool = Field(default=True, description="Binance测试网")
    
    # OKX
    okx_api_key: Optional[str] = Field(default=None, description="OKX API密钥")
    okx_api_secret: Optional[str] = Field(default=None, description="OKX API密钥")
    okx_passphrase: Optional[str] = Field(default=None, description="OKX API密码")
    okx_testnet: bool = Field(default=True, description="OKX测试网")
    
    # Huobi
    huobi_api_key: Optional[str] = Field(default=None, description="Huobi API密钥")
    huobi_api_secret: Optional[str] = Field(default=None, description="Huobi API密钥")
    huobi_testnet: bool = Field(default=True, description="Huobi测试网")
    
    # Hummingbot配置
    hummingbot_enabled: bool = Field(default=True, description="启用Hummingbot集成")
    hummingbot_host: str = Field(default="localhost", description="Hummingbot主机")
    hummingbot_port: int = Field(default=8080, description="Hummingbot端口")
    hummingbot_username: Optional[str] = Field(default=None, description="Hummingbot用户名")
    hummingbot_password: Optional[str] = Field(default=None, description="Hummingbot密码")
    hummingbot_strategies_path: str = Field(
        default="./hummingbot_strategies",
        description="Hummingbot策略文件路径"
    )
    
    # 风险管理配置
    risk_max_position_size: float = Field(default=10000.0, description="最大仓位大小")
    risk_max_daily_loss: float = Field(default=1000.0, description="最大日损失")
    risk_max_drawdown: float = Field(default=0.1, description="最大回撤比例")
    risk_volatility_threshold: float = Field(default=0.05, description="波动率阈值")
    risk_liquidity_threshold: float = Field(default=1000.0, description="流动性阈值")
    max_position_size: float = Field(default=10000.0, description="最大仓位大小（兼容性）")
    max_daily_volume: float = Field(default=100000.0, description="最大日交易量")
    min_profit_threshold: float = Field(default=0.5, description="最小利润阈值（%）")
    max_slippage: float = Field(default=0.1, description="最大滑点（%）")
    
    # API配置
    api_prefix: str = Field(default="/api/v1", description="API前缀")
    api_rate_limit: int = Field(default=100, description="API速率限制（每分钟请求数）")
    api_rate_limit_period: int = Field(default=60, description="API速率限制周期（秒）")
    exchange_rate_limit: int = Field(default=10, description="交易所速率限制（每秒请求数）")
    
    # 监控配置
    monitoring_enabled: bool = Field(default=True, description="启用监控")
    monitoring_interval: int = Field(default=60, description="监控间隔（秒）")
    health_check_interval: int = Field(default=30, description="健康检查间隔（秒）")
    enable_prometheus: bool = Field(default=True, description="启用Prometheus监控")
    
    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="logs/app.log", description="日志文件")
    log_max_size: int = Field(default=10485760, description="日志文件最大大小（字节）")
    log_backup_count: int = Field(default=5, description="日志文件备份数量")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    
    # WebSocket配置
    websocket_enabled: bool = Field(default=True, description="启用WebSocket")
    websocket_heartbeat_interval: int = Field(default=30, description="WebSocket心跳间隔（秒）")
    websocket_max_connections: int = Field(default=1000, description="WebSocket最大连接数")
    websocket_message_queue_size: int = Field(default=1000, description="WebSocket消息队列大小")
    
    # 缓存配置
    cache_enabled: bool = Field(default=True, description="启用缓存")
    cache_ttl: int = Field(default=300, description="缓存TTL（秒）")
    cache_max_size: int = Field(default=1000, description="缓存最大大小")
    
    # 通知配置
    notifications_enabled: bool = Field(default=True, description="启用通知")
    
    # 邮件通知
    email_enabled: bool = Field(default=False, description="启用邮件通知")
    email_smtp_host: Optional[str] = Field(default=None, description="SMTP主机")
    email_smtp_port: int = Field(default=587, description="SMTP端口")
    email_username: Optional[str] = Field(default=None, description="邮件用户名")
    email_password: Optional[str] = Field(default=None, description="邮件密码")
    email_from: Optional[str] = Field(default=None, description="发件人邮箱")
    
    # Telegram通知
    telegram_enabled: bool = Field(default=False, description="启用Telegram通知")
    telegram_bot_token: Optional[str] = Field(default=None, description="Telegram机器人令牌")
    telegram_chat_id: Optional[str] = Field(default=None, description="Telegram聊天ID")
    
    # Slack通知
    slack_enabled: bool = Field(default=False, description="启用Slack通知")
    slack_webhook_url: Optional[str] = Field(default=None, description="Slack Webhook URL")
    
    # 性能配置
    max_concurrent_requests: int = Field(default=100, description="最大并发请求数")
    request_timeout: int = Field(default=30, description="请求超时时间（秒）")
    connection_pool_size: int = Field(default=100, description="连接池大小")
    
    # 数据保留配置
    data_retention_days: int = Field(default=90, description="数据保留天数")
    log_retention_days: int = Field(default=30, description="日志保留天数")
    trade_history_retention_days: int = Field(default=365, description="交易历史保留天数")
    
    @validator('environment')
    def validate_environment(cls, v):
        allowed_envs = ['development', 'staging', 'production']
        if v not in allowed_envs:
            raise ValueError(f'Environment must be one of {allowed_envs}')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'Log level must be one of {allowed_levels}')
        return v.upper()
    
    @validator('jwt_secret_key')
    def validate_jwt_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError('JWT secret key must be at least 32 characters long')
        return v
    
    @validator('encryption_key')
    def validate_encryption_key(cls, v):
        if len(v) != 32:
            raise ValueError('Encryption key must be exactly 32 characters long')
        return v
    
    def get_exchange_config(self, exchange: str) -> Dict[str, Any]:
        """获取交易所配置"""
        configs = {
            'binance': {
                'api_key': self.binance_api_key,
                'api_secret': self.binance_api_secret,
                'testnet': self.binance_testnet,
                'enabled': bool(self.binance_api_key and self.binance_api_secret)
            },
            'okx': {
                'api_key': self.okx_api_key,
                'api_secret': self.okx_api_secret,
                'passphrase': self.okx_passphrase,
                'testnet': self.okx_testnet,
                'enabled': bool(self.okx_api_key and self.okx_api_secret and self.okx_passphrase)
            },
            'huobi': {
                'api_key': self.huobi_api_key,
                'api_secret': self.huobi_api_secret,
                'testnet': self.huobi_testnet,
                'enabled': bool(self.huobi_api_key and self.huobi_api_secret)
            }
        }
        return configs.get(exchange.lower(), {})
    
    def get_notification_config(self) -> Dict[str, Any]:
        """获取通知配置"""
        return {
            'enabled': self.notifications_enabled,
            'email': {
                'enabled': self.email_enabled,
                'smtp_host': self.email_smtp_host,
                'smtp_port': self.email_smtp_port,
                'username': self.email_username,
                'password': self.email_password,
                'from': self.email_from
            },
            'telegram': {
                'enabled': self.telegram_enabled,
                'bot_token': self.telegram_bot_token,
                'chat_id': self.telegram_chat_id
            },
            'slack': {
                'enabled': self.slack_enabled,
                'webhook_url': self.slack_webhook_url
            }
        }
    
    def get_risk_config(self) -> Dict[str, Any]:
        """获取风险管理配置"""
        return {
            'max_position_size': self.risk_max_position_size,
            'max_daily_loss': self.risk_max_daily_loss,
            'max_drawdown': self.risk_max_drawdown,
            'volatility_threshold': self.risk_volatility_threshold,
            'liquidity_threshold': self.risk_liquidity_threshold
        }
    
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.environment == 'production'
    
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self.environment == 'development'
    
    def is_testing(self) -> bool:
        """是否为测试环境"""
        return self.testing or self.environment == 'testing'
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

# 创建全局设置实例
settings = Settings()

# 确保必要的目录存在
def ensure_directories():
    """确保必要的目录存在"""
    directories = [
        "logs",
        "data",
        "backups",
        settings.hummingbot_strategies_path,
        "temp"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)

# 初始化时创建目录
ensure_directories()

# 导出
__all__ = ["settings", "Settings", "ensure_directories"]