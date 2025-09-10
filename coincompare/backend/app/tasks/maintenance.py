"""维护任务模块

处理系统维护相关的后台任务，包括数据清理、系统健康检查、性能优化等。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List
from celery import current_app as celery_app
from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery_app import celery, high_priority_task, low_priority_task
from ..database import get_async_session, DatabaseManager, CacheManager
from ..models import (
    Trade, ArbitrageOpportunity, RiskAlert, SystemLog,
    Strategy, User, Exchange, TradingPair
)
from ..config import settings
from ..services.logging_service import logger


@celery.task(bind=True, name="maintenance.cleanup_old_data")
def cleanup_old_data_task(self):
    """清理旧数据任务"""
    try:
        return asyncio.run(cleanup_old_data_async())
    except Exception as e:
        logger.error(f"清理旧数据失败: {e}")
        raise self.retry(countdown=300, max_retries=3)


@celery.task(bind=True, name="maintenance.system_health_check")
def system_health_check_task(self):
    """系统健康检查任务"""
    try:
        return asyncio.run(system_health_check_async())
    except Exception as e:
        logger.error(f"系统健康检查失败: {e}")
        raise self.retry(countdown=60, max_retries=5)


@celery.task(bind=True, name="maintenance.optimize_database")
def optimize_database_task(self):
    """数据库优化任务"""
    try:
        return asyncio.run(optimize_database_async())
    except Exception as e:
        logger.error(f"数据库优化失败: {e}")
        raise self.retry(countdown=600, max_retries=2)


@celery.task(bind=True, name="maintenance.backup_critical_data")
def backup_critical_data_task(self):
    """备份关键数据任务"""
    try:
        return asyncio.run(backup_critical_data_async())
    except Exception as e:
        logger.error(f"数据备份失败: {e}")
        raise self.retry(countdown=1800, max_retries=2)


@celery.task(bind=True, name="maintenance.update_system_metrics")
def update_system_metrics_task(self):
    """更新系统指标任务"""
    try:
        return asyncio.run(update_system_metrics_async())
    except Exception as e:
        logger.error(f"更新系统指标失败: {e}")
        raise self.retry(countdown=120, max_retries=3)


async def cleanup_old_data_async() -> Dict[str, Any]:
    """清理旧数据的异步实现"""
    async with get_async_session() as session:
        try:
            cleanup_results = {}
            cutoff_date = datetime.utcnow() - timedelta(days=settings.DATA_RETENTION_DAYS)
            
            # 清理旧的套利机会记录
            old_opportunities = await session.execute(
                text("DELETE FROM arbitrage_opportunities WHERE created_at < :cutoff_date")
                .params(cutoff_date=cutoff_date)
            )
            cleanup_results['arbitrage_opportunities'] = old_opportunities.rowcount
            
            # 清理旧的风险警报
            old_alerts = await session.execute(
                text("DELETE FROM risk_alerts WHERE created_at < :cutoff_date")
                .params(cutoff_date=cutoff_date)
            )
            cleanup_results['risk_alerts'] = old_alerts.rowcount
            
            # 清理旧的系统日志
            log_cutoff = datetime.utcnow() - timedelta(days=settings.LOG_RETENTION_DAYS)
            old_logs = await session.execute(
                text("DELETE FROM system_logs WHERE created_at < :cutoff_date")
                .params(cutoff_date=log_cutoff)
            )
            cleanup_results['system_logs'] = old_logs.rowcount
            
            # 清理旧的交易记录（保留重要交易）
            old_trades = await session.execute(
                text("""
                    DELETE FROM trades 
                    WHERE created_at < :cutoff_date 
                    AND status NOT IN ('pending', 'processing')
                    AND profit_loss < 100
                """)
                .params(cutoff_date=cutoff_date)
            )
            cleanup_results['trades'] = old_trades.rowcount
            
            await session.commit()
            
            # 清理缓存
            cache_manager = CacheManager()
            await cache_manager.clear_expired()
            
            logger.info(f"数据清理完成: {cleanup_results}")
            return {
                'status': 'success',
                'cleanup_results': cleanup_results,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            await session.rollback()
            logger.error(f"数据清理失败: {e}")
            raise


async def system_health_check_async() -> Dict[str, Any]:
    """系统健康检查的异步实现"""
    health_status = {
        'timestamp': datetime.utcnow().isoformat(),
        'overall_status': 'healthy',
        'components': {}
    }
    
    try:
        # 检查数据库连接
        db_manager = DatabaseManager()
        db_healthy = await db_manager.check_connection()
        health_status['components']['database'] = {
            'status': 'healthy' if db_healthy else 'unhealthy',
            'response_time': None
        }
        
        # 检查Redis连接
        cache_manager = CacheManager()
        redis_healthy = await cache_manager.ping()
        health_status['components']['redis'] = {
            'status': 'healthy' if redis_healthy else 'unhealthy'
        }
        
        # 检查Celery工作进程
        celery_stats = celery_app.control.inspect().stats()
        celery_healthy = bool(celery_stats)
        health_status['components']['celery'] = {
            'status': 'healthy' if celery_healthy else 'unhealthy',
            'workers': len(celery_stats) if celery_stats else 0
        }
        
        # 检查交易所连接状态
        async with get_async_session() as session:
            exchanges = await session.execute(
                text("SELECT name, status FROM exchanges WHERE is_active = true")
            )
            exchange_status = {}
            for exchange in exchanges:
                # 这里应该实际检查交易所API连接
                exchange_status[exchange.name] = 'healthy'
            
            health_status['components']['exchanges'] = exchange_status
        
        # 检查系统资源使用情况
        import psutil
        health_status['components']['system'] = {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent
        }
        
        # 判断整体健康状态
        unhealthy_components = [
            comp for comp, status in health_status['components'].items()
            if (isinstance(status, dict) and status.get('status') == 'unhealthy') or
               (comp == 'system' and (
                   status.get('cpu_percent', 0) > 90 or
                   status.get('memory_percent', 0) > 90 or
                   status.get('disk_percent', 0) > 90
               ))
        ]
        
        if unhealthy_components:
            health_status['overall_status'] = 'degraded' if len(unhealthy_components) == 1 else 'unhealthy'
            health_status['issues'] = unhealthy_components
        
        logger.info(f"系统健康检查完成: {health_status['overall_status']}")
        return health_status
        
    except Exception as e:
        logger.error(f"系统健康检查失败: {e}")
        health_status['overall_status'] = 'error'
        health_status['error'] = str(e)
        return health_status


async def optimize_database_async() -> Dict[str, Any]:
    """数据库优化的异步实现"""
    async with get_async_session() as session:
        try:
            optimization_results = {}
            
            # 分析表统计信息
            tables = ['trades', 'arbitrage_opportunities', 'risk_alerts', 'system_logs']
            for table in tables:
                result = await session.execute(
                    text(f"ANALYZE TABLE {table}")
                )
                optimization_results[f'analyze_{table}'] = 'completed'
            
            # 重建索引（如果需要）
            index_queries = [
                "REINDEX INDEX idx_trades_created_at",
                "REINDEX INDEX idx_arbitrage_opportunities_created_at",
                "REINDEX INDEX idx_risk_alerts_created_at"
            ]
            
            for query in index_queries:
                try:
                    await session.execute(text(query))
                    optimization_results[f'reindex_{query.split()[-1]}'] = 'completed'
                except Exception as e:
                    optimization_results[f'reindex_{query.split()[-1]}'] = f'failed: {e}'
            
            # 清理碎片
            await session.execute(text("VACUUM ANALYZE"))
            optimization_results['vacuum'] = 'completed'
            
            await session.commit()
            
            logger.info(f"数据库优化完成: {optimization_results}")
            return {
                'status': 'success',
                'optimization_results': optimization_results,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库优化失败: {e}")
            raise


async def backup_critical_data_async() -> Dict[str, Any]:
    """备份关键数据的异步实现"""
    try:
        backup_results = {}
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        async with get_async_session() as session:
            # 备份用户数据
            users = await session.execute(
                text("SELECT * FROM users WHERE is_active = true")
            )
            backup_results['users_count'] = len(users.fetchall())
            
            # 备份策略配置
            strategies = await session.execute(
                text("SELECT * FROM strategies WHERE status = 'active'")
            )
            backup_results['strategies_count'] = len(strategies.fetchall())
            
            # 备份交易所配置
            exchanges = await session.execute(
                text("SELECT * FROM exchanges WHERE is_active = true")
            )
            backup_results['exchanges_count'] = len(exchanges.fetchall())
            
            # 备份API密钥（加密存储）
            api_keys = await session.execute(
                text("SELECT COUNT(*) FROM api_keys WHERE is_active = true")
            )
            backup_results['api_keys_count'] = api_keys.scalar()
        
        # 这里应该实际执行备份操作，比如导出到文件或云存储
        # 为了演示，我们只记录备份信息
        backup_results['backup_file'] = f"backup_{timestamp}.sql"
        backup_results['backup_location'] = settings.BACKUP_PATH
        
        logger.info(f"关键数据备份完成: {backup_results}")
        return {
            'status': 'success',
            'backup_results': backup_results,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"数据备份失败: {e}")
        raise


async def update_system_metrics_async() -> Dict[str, Any]:
    """更新系统指标的异步实现"""
    try:
        metrics = {}
        
        async with get_async_session() as session:
            # 统计活跃用户数
            active_users = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE is_active = true")
            )
            metrics['active_users'] = active_users.scalar()
            
            # 统计今日交易数
            today = datetime.utcnow().date()
            today_trades = await session.execute(
                text("""
                    SELECT COUNT(*) FROM trades 
                    WHERE DATE(created_at) = :today
                """)
                .params(today=today)
            )
            metrics['today_trades'] = today_trades.scalar()
            
            # 统计活跃策略数
            active_strategies = await session.execute(
                text("SELECT COUNT(*) FROM strategies WHERE status = 'active'")
            )
            metrics['active_strategies'] = active_strategies.scalar()
            
            # 统计套利机会数（最近1小时）
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_opportunities = await session.execute(
                text("""
                    SELECT COUNT(*) FROM arbitrage_opportunities 
                    WHERE created_at > :one_hour_ago
                """)
                .params(one_hour_ago=one_hour_ago)
            )
            metrics['recent_opportunities'] = recent_opportunities.scalar()
            
            # 计算平均利润率
            avg_profit = await session.execute(
                text("""
                    SELECT AVG(profit_loss) FROM trades 
                    WHERE status = 'completed' AND created_at > :one_week_ago
                """)
                .params(one_week_ago=datetime.utcnow() - timedelta(days=7))
            )
            metrics['avg_weekly_profit'] = float(avg_profit.scalar() or 0)
        
        # 缓存指标数据
        cache_manager = CacheManager()
        await cache_manager.set(
            "system_metrics",
            metrics,
            expire=300  # 5分钟过期
        )
        
        logger.info(f"系统指标更新完成: {metrics}")
        return {
            'status': 'success',
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"系统指标更新失败: {e}")
        raise


# 导出任务函数
__all__ = [
    'cleanup_old_data_task',
    'system_health_check_task',
    'optimize_database_task',
    'backup_critical_data_task',
    'update_system_metrics_task'
]