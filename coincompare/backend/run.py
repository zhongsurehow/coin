#!/usr/bin/env python3
"""
CoinCompare Backend Server
启动脚本 - 用于开发和生产环境
"""

import os
import sys
import asyncio
import uvicorn
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.main import app
from app.core.config import settings
from app.core.database import create_tables, check_database_connection
from app.services.hummingbot_client import hummingbot_manager
from app.services.arbitrage_service import arbitrage_service
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

async def startup_tasks():
    """执行启动时的初始化任务"""
    try:
        logger.info("Starting CoinCompare Backend Server...")
        
        # 1. 检查数据库连接
        logger.info("Checking database connection...")
        await check_database_connection()
        
        # 2. 创建数据库表
        logger.info("Creating database tables...")
        await create_tables()
        
        # 3. 初始化服务
        logger.info("Initializing services...")
        
        # 初始化套利服务
        await arbitrage_service.initialize()
        logger.info("Arbitrage service initialized")
        
        # 初始化Hummingbot管理器
        await hummingbot_manager.initialize()
        logger.info("Hummingbot manager initialized")
        
        logger.info("All startup tasks completed successfully")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

def create_directories():
    """创建必要的目录"""
    directories = [
        'logs',
        'data',
        'backups',
        'uploads'
    ]
    
    for directory in directories:
        dir_path = project_root / directory
        dir_path.mkdir(exist_ok=True)
        logger.info(f"Directory created/verified: {dir_path}")

def main():
    """主函数"""
    # 创建必要目录
    create_directories()
    
    # 设置环境变量
    os.environ.setdefault('PYTHONPATH', str(project_root))
    
    # 运行启动任务
    try:
        asyncio.run(startup_tasks())
    except Exception as e:
        logger.error(f"Failed to complete startup tasks: {e}")
        sys.exit(1)
    
    # 启动服务器
    logger.info(f"Starting server on {settings.HOST}:{settings.PORT}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else settings.WORKERS,
        log_level="info" if settings.DEBUG else "warning",
        access_log=settings.DEBUG,
        loop="asyncio",
        # SSL配置（生产环境）
        ssl_keyfile=settings.SSL_KEYFILE if settings.SSL_KEYFILE else None,
        ssl_certfile=settings.SSL_CERTFILE if settings.SSL_CERTFILE else None,
    )

if __name__ == "__main__":
    main()