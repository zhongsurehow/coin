from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import os
from .config import settings

# 创建Celery应用实例
celery_app = Celery(
    "arbitrage_trading",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.data_collection",
        "app.tasks.arbitrage_detection",
        "app.tasks.risk_monitoring",
        "app.tasks.strategy_execution",
        "app.tasks.notifications",
        "app.tasks.maintenance"
    ]
)

# Celery配置
celery_app.conf.update(
    # 时区设置
    timezone='UTC',
    enable_utc=True,
    
    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # 结果后端配置
    result_expires=3600,  # 1小时后过期
    result_backend_transport_options={
        'master_name': 'mymaster',
        'visibility_timeout': 3600,
    },
    
    # 任务路由
    task_routes={
        'app.tasks.data_collection.*': {'queue': 'data_collection'},
        'app.tasks.arbitrage_detection.*': {'queue': 'arbitrage'},
        'app.tasks.risk_monitoring.*': {'queue': 'risk'},
        'app.tasks.strategy_execution.*': {'queue': 'strategy'},
        'app.tasks.notifications.*': {'queue': 'notifications'},
        'app.tasks.maintenance.*': {'queue': 'maintenance'},
    },
    
    # 队列配置
    task_default_queue='default',
    task_queues=(
        Queue('default', routing_key='default'),
        Queue('data_collection', routing_key='data_collection'),
        Queue('arbitrage', routing_key='arbitrage'),
        Queue('risk', routing_key='risk'),
        Queue('strategy', routing_key='strategy'),
        Queue('notifications', routing_key='notifications'),
        Queue('maintenance', routing_key='maintenance'),
    ),
    
    # 工作进程配置
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    
    # 任务重试配置
    task_default_retry_delay=60,  # 60秒后重试
    task_max_retries=3,
    
    # 任务超时配置
    task_soft_time_limit=300,  # 5分钟软超时
    task_time_limit=600,       # 10分钟硬超时
    
    # 监控配置
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # 定时任务配置
    beat_schedule={
        # 数据收集任务
        'collect-market-data': {
            'task': 'app.tasks.data_collection.collect_market_data',
            'schedule': 30.0,  # 每30秒执行一次
            'options': {'queue': 'data_collection'}
        },
        'collect-orderbook-data': {
            'task': 'app.tasks.data_collection.collect_orderbook_data',
            'schedule': 10.0,  # 每10秒执行一次
            'options': {'queue': 'data_collection'}
        },
        
        # 套利检测任务
        'detect-arbitrage-opportunities': {
            'task': 'app.tasks.arbitrage_detection.detect_opportunities',
            'schedule': 5.0,  # 每5秒执行一次
            'options': {'queue': 'arbitrage'}
        },
        'calculate-arbitrage-profits': {
            'task': 'app.tasks.arbitrage_detection.calculate_profits',
            'schedule': 15.0,  # 每15秒执行一次
            'options': {'queue': 'arbitrage'}
        },
        
        # 风险监控任务
        'monitor-positions': {
            'task': 'app.tasks.risk_monitoring.monitor_positions',
            'schedule': 60.0,  # 每分钟执行一次
            'options': {'queue': 'risk'}
        },
        'check-risk-limits': {
            'task': 'app.tasks.risk_monitoring.check_risk_limits',
            'schedule': 30.0,  # 每30秒执行一次
            'options': {'queue': 'risk'}
        },
        'calculate-portfolio-metrics': {
            'task': 'app.tasks.risk_monitoring.calculate_portfolio_metrics',
            'schedule': 300.0,  # 每5分钟执行一次
            'options': {'queue': 'risk'}
        },
        
        # 策略执行任务
        'update-strategy-status': {
            'task': 'app.tasks.strategy_execution.update_strategy_status',
            'schedule': 60.0,  # 每分钟执行一次
            'options': {'queue': 'strategy'}
        },
        'sync-hummingbot-strategies': {
            'task': 'app.tasks.strategy_execution.sync_hummingbot_strategies',
            'schedule': 300.0,  # 每5分钟执行一次
            'options': {'queue': 'strategy'}
        },
        
        # 通知任务
        'send-daily-report': {
            'task': 'app.tasks.notifications.send_daily_report',
            'schedule': crontab(hour=9, minute=0),  # 每天上午9点
            'options': {'queue': 'notifications'}
        },
        'check-alert-conditions': {
            'task': 'app.tasks.notifications.check_alert_conditions',
            'schedule': 60.0,  # 每分钟执行一次
            'options': {'queue': 'notifications'}
        },
        
        # 维护任务
        'cleanup-old-data': {
            'task': 'app.tasks.maintenance.cleanup_old_data',
            'schedule': crontab(hour=2, minute=0),  # 每天凌晨2点
            'options': {'queue': 'maintenance'}
        },
        'backup-database': {
            'task': 'app.tasks.maintenance.backup_database',
            'schedule': crontab(hour=3, minute=0),  # 每天凌晨3点
            'options': {'queue': 'maintenance'}
        },
        'health-check': {
            'task': 'app.tasks.maintenance.health_check',
            'schedule': 300.0,  # 每5分钟执行一次
            'options': {'queue': 'maintenance'}
        },
        'update-exchange-info': {
            'task': 'app.tasks.maintenance.update_exchange_info',
            'schedule': crontab(hour=1, minute=0),  # 每天凌晨1点
            'options': {'queue': 'maintenance'}
        },
    },
    
    # 错误处理
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
    
    # 安全配置
    worker_hijack_root_logger=False,
    worker_log_color=False,
)

# 任务装饰器配置
def task_with_retry(**kwargs):
    """带重试机制的任务装饰器"""
    default_kwargs = {
        'bind': True,
        'autoretry_for': (Exception,),
        'retry_kwargs': {'max_retries': 3, 'countdown': 60},
        'retry_backoff': True,
        'retry_jitter': True,
    }
    default_kwargs.update(kwargs)
    return celery_app.task(**default_kwargs)

# 高优先级任务装饰器
def urgent_task(**kwargs):
    """高优先级任务装饰器"""
    default_kwargs = {
        'bind': True,
        'priority': 9,
        'autoretry_for': (Exception,),
        'retry_kwargs': {'max_retries': 5, 'countdown': 10},
    }
    default_kwargs.update(kwargs)
    return celery_app.task(**default_kwargs)

# 低优先级任务装饰器
def background_task(**kwargs):
    """后台任务装饰器"""
    default_kwargs = {
        'bind': True,
        'priority': 1,
        'autoretry_for': (Exception,),
        'retry_kwargs': {'max_retries': 2, 'countdown': 300},
    }
    default_kwargs.update(kwargs)
    return celery_app.task(**default_kwargs)

# 任务状态回调
@celery_app.task(bind=True)
def task_success_callback(self, retval, task_id, args, kwargs):
    """任务成功回调"""
    print(f"Task {task_id} succeeded with result: {retval}")

@celery_app.task(bind=True)
def task_failure_callback(self, task_id, error, traceback, args, kwargs):
    """任务失败回调"""
    print(f"Task {task_id} failed with error: {error}")
    # 这里可以添加错误通知逻辑

# 自定义任务基类
class CallbackTask(celery_app.Task):
    """带回调的任务基类"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功时调用"""
        task_success_callback.delay(retval, task_id, args, kwargs)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败时调用"""
        task_failure_callback.delay(task_id, str(exc), str(einfo), args, kwargs)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试时调用"""
        print(f"Task {task_id} is being retried due to: {exc}")

# 设置默认任务基类
celery_app.Task = CallbackTask

# 信号处理
from celery.signals import worker_ready, worker_shutdown

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """工作进程就绪信号处理"""
    print(f"Worker {sender} is ready")

@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """工作进程关闭信号处理"""
    print(f"Worker {sender} is shutting down")

# 导出
__all__ = [
    "celery_app",
    "task_with_retry",
    "urgent_task",
    "background_task",
    "CallbackTask"
]