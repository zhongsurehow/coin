from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
import redis.asyncio as redis
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from pathlib import Path
from alembic import command
from alembic.config import Config
import logging

from .core.config import settings

logger = logging.getLogger(__name__)

# Create base class for models
Base = declarative_base()

# Global variables
async_engine: Optional[AsyncEngine] = None
AsyncSessionLocal: Optional[async_sessionmaker] = None
sync_engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None


def get_database_url(async_mode: bool = True) -> str:
    """获取数据库连接URL"""
    if hasattr(settings, 'database_url') and settings.database_url:
        url = settings.database_url
        if async_mode and 'postgresql://' in url:
            return url.replace('postgresql://', 'postgresql+asyncpg://')
        elif async_mode and 'mysql://' in url:
            return url.replace('mysql://', 'mysql+aiomysql://')
        return url
    
    # 构建数据库URL
    if settings.DATABASE_TYPE == 'postgresql':
        driver = 'postgresql+asyncpg' if async_mode else 'postgresql+psycopg2'
        return (
            f"{driver}://{settings.DATABASE_USER}:{settings.DATABASE_PASSWORD}"
            f"@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
        )
    elif settings.DATABASE_TYPE == 'mysql':
        driver = 'mysql+aiomysql' if async_mode else 'mysql+pymysql'
        return (
            f"{driver}://{settings.DATABASE_USER}:{settings.DATABASE_PASSWORD}"
            f"@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
        )
    elif settings.DATABASE_TYPE == 'sqlite':
        db_path = Path(settings.DATABASE_NAME)
        if not db_path.is_absolute():
            db_path = Path.cwd() / 'data' / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        driver = 'sqlite+aiosqlite' if async_mode else 'sqlite'
        return f"{driver}:///{db_path}"
    else:
        # 默认使用配置中的database_url
        return settings.database_url


def create_sync_engine() -> Engine:
    """创建同步数据库引擎"""
    database_url = get_database_url(async_mode=False)
    
    engine_kwargs = {
        'echo': getattr(settings, 'database_echo', False),
        'pool_pre_ping': True,
    }
    
    # 根据数据库类型设置连接池
    if 'postgresql' in database_url or 'mysql' in database_url:
        engine_kwargs.update({
            'poolclass': QueuePool,
            'pool_size': getattr(settings, 'DATABASE_POOL_SIZE', 10),
            'max_overflow': getattr(settings, 'DATABASE_MAX_OVERFLOW', 20),
            'pool_timeout': getattr(settings, 'DATABASE_POOL_TIMEOUT', 30),
            'pool_recycle': getattr(settings, 'DATABASE_POOL_RECYCLE', 3600),
        })
    
    engine = create_engine(database_url, **engine_kwargs)
    
    # 添加SQLite优化
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if 'sqlite' in database_url:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()
    
    return engine


def create_async_engine_instance() -> AsyncEngine:
    """创建异步数据库引擎"""
    database_url = get_database_url(async_mode=True)
    
    engine_kwargs = {
        'echo': getattr(settings, 'database_echo', False),
        'pool_pre_ping': True,
    }
    
    # 根据数据库类型设置连接池
    if 'postgresql' in database_url or 'mysql' in database_url:
        if getattr(settings, 'debug', False):
            engine_kwargs['poolclass'] = NullPool
        else:
            engine_kwargs.update({
                'poolclass': QueuePool,
                'pool_size': getattr(settings, 'DATABASE_POOL_SIZE', 10),
                'max_overflow': getattr(settings, 'DATABASE_MAX_OVERFLOW', 20),
                'pool_timeout': getattr(settings, 'DATABASE_POOL_TIMEOUT', 30),
                'pool_recycle': getattr(settings, 'DATABASE_POOL_RECYCLE', 3600),
            })
    
    return create_async_engine(database_url, **engine_kwargs)


async def init_database():
    """初始化数据库连接"""
    global async_engine, AsyncSessionLocal, sync_engine, SessionLocal
    
    try:
        # 创建异步引擎
        async_engine = create_async_engine_instance()
        AsyncSessionLocal = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )
        
        # 创建同步引擎（用于迁移等操作）
        sync_engine = create_sync_engine()
        SessionLocal = sessionmaker(
            bind=sync_engine,
            autoflush=True,
            autocommit=False
        )
        
        # 测试连接
        async with async_engine.begin() as conn:
            await conn.execute("SELECT 1")
        
        logger.info("数据库连接初始化成功")
        
    except Exception as e:
        logger.error(f"数据库连接初始化失败: {e}")
        raise


async def close_database():
    """关闭数据库连接"""
    global async_engine, sync_engine
    
    try:
        if async_engine:
            await async_engine.dispose()
            logger.info("异步数据库连接已关闭")
        
        if sync_engine:
            sync_engine.dispose()
            logger.info("同步数据库连接已关闭")
            
    except Exception as e:
        logger.error(f"关闭数据库连接失败: {e}")


# 兼容性：保持原有的engine变量
engine = None


async def init_engines():
    """初始化引擎（兼容性函数）"""
    global engine
    await init_database()
    engine = async_engine

# Redis connection
redis_client = None

async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    try:
        redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        # Test connection
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None

async def close_redis():
    """Close Redis connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection closed")

@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话的上下文管理器"""
    if AsyncSessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库会话异常: {e}")
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (兼容性函数)"""
    async with get_async_session() as session:
        yield session


def get_sync_session():
    """获取同步数据库会话"""
    if SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    
    return SessionLocal()

async def get_redis() -> redis.Redis:
    """Get Redis client"""
    global redis_client
    if redis_client is None:
        await init_redis()
    return redis_client

async def create_tables():
    """创建数据库表"""
    if async_engine is None:
        raise RuntimeError("数据库引擎未初始化")
    
    try:
        # 导入所有模型以确保它们被注册
        from . import models
        
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("数据库表创建成功")
        
    except Exception as e:
        logger.error(f"创建数据库表失败: {e}")
        raise


def run_migrations():
    """运行数据库迁移"""
    try:
        # 获取Alembic配置
        alembic_cfg_path = Path(__file__).parent.parent / 'alembic.ini'
        if not alembic_cfg_path.exists():
            logger.warning("未找到alembic.ini文件，跳过迁移")
            return
        
        alembic_cfg = Config(str(alembic_cfg_path))
        
        # 设置数据库URL
        database_url = get_database_url(async_mode=False)
        alembic_cfg.set_main_option('sqlalchemy.url', database_url)
        
        # 运行迁移
        command.upgrade(alembic_cfg, 'head')
        logger.info("数据库迁移完成")
        
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        raise


async def check_database_health() -> bool:
    """检查数据库健康状态"""
    try:
        if async_engine is None:
            return False
        
        async with async_engine.begin() as conn:
            result = await conn.execute("SELECT 1")
            return result.scalar() == 1
            
    except Exception as e:
        logger.error(f"数据库健康检查失败: {e}")
        return False


async def get_database_stats() -> dict:
    """获取数据库统计信息"""
    try:
        if async_engine is None:
            return {}
        
        stats = {
            'pool_size': async_engine.pool.size(),
            'checked_in': async_engine.pool.checkedin(),
            'checked_out': async_engine.pool.checkedout(),
            'overflow': async_engine.pool.overflow(),
            'invalid': async_engine.pool.invalid(),
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"获取数据库统计信息失败: {e}")
        return {}


class DatabaseManager:
    """数据库管理器类"""
    
    def __init__(self):
        self.async_engine = None
        self.sync_engine = None
        self.async_session_factory = None
        self.sync_session_factory = None
    
    async def initialize(self):
        """初始化数据库管理器"""
        await init_database()
        self.async_engine = async_engine
        self.sync_engine = sync_engine
        self.async_session_factory = AsyncSessionLocal
        self.sync_session_factory = SessionLocal
    
    async def close(self):
        """关闭数据库管理器"""
        await close_database()
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取数据库会话"""
        async with get_async_session() as session:
            yield session
    
    async def execute_raw_sql(self, sql: str, params: dict = None):
        """执行原始SQL"""
        async with self.get_session() as session:
            result = await session.execute(sql, params or {})
            await session.commit()
            return result
    
    async def backup_database(self, backup_path: str):
        """备份数据库"""
        database_url = get_database_url(async_mode=False)
        if 'sqlite' in database_url:
            import shutil
            db_path = database_url.replace('sqlite:///', '')
            shutil.copy2(db_path, backup_path)
            logger.info(f"SQLite数据库备份完成: {backup_path}")
        else:
            logger.warning(f"数据库类型不支持自动备份")
    
    async def optimize_database(self):
        """优化数据库"""
        try:
            database_url = get_database_url(async_mode=False)
            if 'sqlite' in database_url:
                async with self.get_session() as session:
                    await session.execute("VACUUM")
                    await session.execute("ANALYZE")
                    await session.commit()
                logger.info("SQLite数据库优化完成")
            elif 'postgresql' in database_url:
                async with self.get_session() as session:
                    await session.execute("VACUUM ANALYZE")
                    await session.commit()
                logger.info("PostgreSQL数据库优化完成")
            else:
                logger.info(f"数据库类型不需要优化")
                
        except Exception as e:
            logger.error(f"数据库优化失败: {e}")
    
    # 兼容性方法
    @staticmethod
    async def create_tables():
        """Create all database tables"""
        await create_tables()
    
    @staticmethod
    async def drop_tables():
        """Drop all database tables"""
        if async_engine is None:
            raise RuntimeError("数据库引擎未初始化")
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped")
    
    @staticmethod
    async def check_connection():
        """Check database connection"""
        return await check_database_health()

class CacheManager:
    """Redis cache management utilities"""
    
    @staticmethod
    async def set(key: str, value: str, ttl: int = None) -> bool:
        """Set cache value"""
        try:
            redis_conn = await get_redis()
            if redis_conn:
                if ttl:
                    await redis_conn.setex(key, ttl, value)
                else:
                    await redis_conn.set(key, value)
                return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
        return False
    
    @staticmethod
    async def get(key: str) -> str:
        """Get cache value"""
        try:
            redis_conn = await get_redis()
            if redis_conn:
                return await redis_conn.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
        return None
    
    @staticmethod
    async def delete(key: str) -> bool:
        """Delete cache value"""
        try:
            redis_conn = await get_redis()
            if redis_conn:
                await redis_conn.delete(key)
                return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
        return False
    
    @staticmethod
    async def exists(key: str) -> bool:
        """Check if cache key exists"""
        try:
            redis_conn = await get_redis()
            if redis_conn:
                return await redis_conn.exists(key)
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
        return False
    
    @staticmethod
    async def clear_pattern(pattern: str) -> int:
        """Clear cache keys matching pattern"""
        try:
            redis_conn = await get_redis()
            if redis_conn:
                keys = await redis_conn.keys(pattern)
                if keys:
                    return await redis_conn.delete(*keys)
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")
        return 0

# 全局数据库管理器实例
db_manager = DatabaseManager()


# 依赖注入函数（用于FastAPI）
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI依赖注入：获取数据库会话"""
    async with get_async_session() as session:
        yield session


async def get_redis_client() -> redis.Redis:
    """Dependency for FastAPI to get Redis client"""
    return await get_redis()


# 便捷函数
async def execute_query(query: str, params: dict = None):
    """执行查询的便捷函数"""
    async with get_async_session() as session:
        result = await session.execute(query, params or {})
        return result


async def execute_transaction(func, *args, **kwargs):
    """执行事务的便捷函数"""
    async with get_async_session() as session:
        try:
            result = await func(session, *args, **kwargs)
            await session.commit()
            return result
        except Exception as e:
            await session.rollback()
            raise e