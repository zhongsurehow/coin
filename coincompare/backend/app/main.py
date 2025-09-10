from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import logging
from typing import List

from .core.config import settings
from .database import (
    init_database,
    close_database,
    init_redis,
    close_redis,
    create_tables,
    db_manager
)
from .api import api_router
from .services.logging_service import logging_service
from .celery_app import celery_app
from .services.exchange_service import exchange_service
from .services.risk_service import risk_service
from .services.hummingbot_service import hummingbot_service
from .services.notification_service import notification_service
from .core.exceptions import (
    APIException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    ExternalServiceException
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global services will be initialized in lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Crypto Arbitrage Platform...")
    
    # 初始化数据库和Redis
    await init_database()
    await init_redis()
    
    # 创建数据库表
    await create_tables()
    
    # 初始化服务
    try:
        # 初始化日志服务
        await logging_service.setup()
        
        # 初始化Hummingbot服务
        await hummingbot_service.connect()
        
        # 启动Celery worker（如果需要）
        if settings.START_CELERY_WORKER:
            logger.info("启动Celery worker...")
        
        # 启动后台任务
        asyncio.create_task(background_monitoring_tasks())
        
        logger.info("所有服务启动成功")
        
        yield
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise
    finally:
        # 清理资源
        try:
            # 关闭日志服务
            await logging_service.close()
            
            # 关闭Hummingbot连接
            await hummingbot_service.disconnect()
            
            # 关闭数据库连接
            await close_redis()
            await close_database()
            
            logger.info("所有服务已停止")
        except Exception as e:
            logger.error(f"关闭服务时出错: {e}")

async def background_monitoring_tasks():
    """启动后台监控任务"""
    logger.info("启动后台监控任务")
    
    # 启动风险监控
    asyncio.create_task(risk_monitoring_loop())
    
    # 启动套利监控
    asyncio.create_task(arbitrage_monitoring_loop())
    
    # 启动数据流监控
    asyncio.create_task(data_streaming_loop())

async def risk_monitoring_loop():
    """后台风险监控"""
    while True:
        try:
            # 使用Celery任务进行风险监控
            from .tasks.risk_monitoring import monitor_portfolio_risk
            monitor_portfolio_risk.delay()
            
            await asyncio.sleep(60)  # 每分钟检查一次
        except Exception as e:
            logger.error(f"风险监控错误: {e}")
            await asyncio.sleep(60)

async def arbitrage_monitoring_loop():
    """后台套利监控"""
    while True:
        try:
            # 使用Celery任务进行套利检测
            from .tasks.arbitrage_detection import detect_arbitrage_opportunities
            detect_arbitrage_opportunities.delay()
            
            await asyncio.sleep(30)  # 每30秒检查一次
        except Exception as e:
            logger.error(f"套利监控错误: {e}")
            await asyncio.sleep(30)

async def data_streaming_loop():
    """后台数据流处理"""
    while True:
        try:
            # 使用Celery任务进行数据收集
            from .tasks.data_collection import collect_market_data
            collect_market_data.delay()
            
            await asyncio.sleep(10)  # 每10秒收集一次数据
        except Exception as e:
            logger.error(f"数据流处理错误: {e}")
            await asyncio.sleep(10)

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="加密货币套利交易平台API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# 注册API路由
app.include_router(api_router)

# 异常处理器
@app.exception_handler(APIException)
async def api_exception_handler(request, exc: APIException):
    """API异常处理器"""
    await logging_service.log_error(
        error=str(exc),
        context={
            "url": str(request.url),
            "method": request.method,
            "error_code": exc.error_code
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "detail": exc.detail
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """通用异常处理器"""
    await logging_service.log_error(
        error=f"Unexpected error: {exc}",
        context={
            "url": str(request.url),
            "method": request.method,
            "exception_type": type(exc).__name__
        }
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误",
            "detail": str(exc) if settings.DEBUG else None
        }
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查数据库连接
        db_status = await db_manager.check_health()
        
        return {
            "status": "healthy",
            "database": "connected" if db_status else "disconnected",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )

# WebSocket端点将通过API路由处理

# Root endpoint
@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "加密货币套利交易平台API",
        "version": "1.0.0",
        "docs": "/docs" if settings.DEBUG else "文档已禁用"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )