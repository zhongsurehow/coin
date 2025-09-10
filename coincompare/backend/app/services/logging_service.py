"""日志服务模块

提供统一的日志记录功能，支持多种输出格式和存储方式。
"""

import logging
import logging.handlers
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_async_session
from ..models import SystemLog
from ..config import settings


class DatabaseLogHandler(logging.Handler):
    """数据库日志处理器"""
    
    def __init__(self):
        super().__init__()
        self.log_queue = asyncio.Queue(maxsize=1000)
        self._task = None
    
    def emit(self, record):
        """发送日志记录"""
        try:
            if self.log_queue.full():
                # 队列满时丢弃最旧的日志
                try:
                    self.log_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            self.log_queue.put_nowait(record)
            
            # 启动异步处理任务
            if self._task is None or self._task.done():
                loop = asyncio.get_event_loop()
                self._task = loop.create_task(self._process_logs())
                
        except Exception:
            # 避免日志记录本身出错
            pass
    
    async def _process_logs(self):
        """异步处理日志队列"""
        try:
            while not self.log_queue.empty():
                try:
                    record = await asyncio.wait_for(self.log_queue.get(), timeout=1.0)
                    await self._save_to_database(record)
                except asyncio.TimeoutError:
                    break
                except Exception as e:
                    # 记录到文件而不是数据库，避免循环错误
                    print(f"保存日志到数据库失败: {e}")
                    
        except Exception as e:
            print(f"处理日志队列失败: {e}")
    
    async def _save_to_database(self, record):
        """保存日志到数据库"""
        try:
            async with get_async_session() as session:
                log_entry = SystemLog(
                    level=record.levelname,
                    logger_name=record.name,
                    message=record.getMessage(),
                    module=record.module if hasattr(record, 'module') else None,
                    function=record.funcName if hasattr(record, 'funcName') else None,
                    line_number=record.lineno if hasattr(record, 'lineno') else None,
                    user_id=getattr(record, 'user_id', None),
                    request_id=getattr(record, 'request_id', None),
                    extra_data=getattr(record, 'extra_data', None)
                )
                session.add(log_entry)
                await session.commit()
                
        except Exception as e:
            # 避免日志记录循环错误
            print(f"保存日志记录失败: {e}")


class JSONFormatter(logging.Formatter):
    """JSON格式化器"""
    
    def format(self, record):
        """格式化日志记录为JSON"""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': getattr(record, 'module', record.module if hasattr(record, 'module') else None),
            'function': getattr(record, 'funcName', record.funcName if hasattr(record, 'funcName') else None),
            'line': getattr(record, 'lineno', record.lineno if hasattr(record, 'lineno') else None),
        }
        
        # 添加额外字段
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'extra_data'):
            log_data['extra_data'] = record.extra_data
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class LoggingService:
    """日志服务类"""
    
    def __init__(self):
        self.logger = None
        self.db_handler = None
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志配置"""
        # 创建主日志器
        self.logger = logging.getLogger('coincompare')
        self.logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        
        # 清除现有处理器
        self.logger.handlers.clear()
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        json_formatter = JSONFormatter()
        
        # 控制台处理器
        if settings.LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # 文件处理器
        if settings.LOG_TO_FILE:
            # 确保日志目录存在
            log_dir = Path(settings.LOG_FILE_PATH).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 普通日志文件
            file_handler = logging.handlers.RotatingFileHandler(
                settings.LOG_FILE_PATH,
                maxBytes=settings.LOG_MAX_SIZE,
                backupCount=settings.LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
            # JSON格式日志文件
            json_log_path = str(settings.LOG_FILE_PATH).replace('.log', '.json')
            json_handler = logging.handlers.RotatingFileHandler(
                json_log_path,
                maxBytes=settings.LOG_MAX_SIZE,
                backupCount=settings.LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
            json_handler.setLevel(logging.DEBUG)
            json_handler.setFormatter(json_formatter)
            self.logger.addHandler(json_handler)
        
        # 数据库处理器
        if settings.LOG_TO_DATABASE:
            self.db_handler = DatabaseLogHandler()
            self.db_handler.setLevel(logging.WARNING)  # 只记录警告及以上级别到数据库
            self.logger.addHandler(self.db_handler)
        
        # 错误日志文件
        error_log_path = str(settings.LOG_FILE_PATH).replace('.log', '_error.log')
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_path,
            maxBytes=settings.LOG_MAX_SIZE,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)
        
        # 设置第三方库日志级别
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        logging.getLogger('aiohttp').setLevel(logging.WARNING)
        logging.getLogger('websockets').setLevel(logging.WARNING)
        
        self.logger.info("日志服务初始化完成")
    
    def get_logger(self, name: str = None) -> logging.Logger:
        """获取日志器"""
        if name:
            return logging.getLogger(f'coincompare.{name}')
        return self.logger
    
    def log_with_context(self, level: str, message: str, 
                        user_id: Optional[int] = None,
                        request_id: Optional[str] = None,
                        extra_data: Optional[Dict[str, Any]] = None,
                        logger_name: str = None):
        """带上下文的日志记录"""
        logger = self.get_logger(logger_name)
        
        # 创建日志记录
        record = logger.makeRecord(
            logger.name,
            getattr(logging, level.upper()),
            '',  # pathname
            0,   # lineno
            message,
            (),  # args
            None  # exc_info
        )
        
        # 添加上下文信息
        if user_id:
            record.user_id = user_id
        if request_id:
            record.request_id = request_id
        if extra_data:
            record.extra_data = extra_data
        
        logger.handle(record)
    
    def log_api_request(self, method: str, url: str, status_code: int,
                       response_time: float, user_id: Optional[int] = None,
                       request_id: Optional[str] = None):
        """记录API请求日志"""
        extra_data = {
            'type': 'api_request',
            'method': method,
            'url': url,
            'status_code': status_code,
            'response_time': response_time
        }
        
        level = 'INFO'
        if status_code >= 500:
            level = 'ERROR'
        elif status_code >= 400:
            level = 'WARNING'
        
        message = f"{method} {url} - {status_code} ({response_time:.3f}s)"
        
        self.log_with_context(
            level, message, user_id, request_id, extra_data, 'api'
        )
    
    def log_trade_execution(self, trade_id: int, symbol: str, side: str,
                           quantity: float, price: float, status: str,
                           user_id: Optional[int] = None):
        """记录交易执行日志"""
        extra_data = {
            'type': 'trade_execution',
            'trade_id': trade_id,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'status': status
        }
        
        level = 'INFO'
        if status in ['failed', 'cancelled']:
            level = 'WARNING'
        elif status == 'error':
            level = 'ERROR'
        
        message = f"交易执行: {symbol} {side} {quantity}@{price} - {status}"
        
        self.log_with_context(
            level, message, user_id, None, extra_data, 'trading'
        )
    
    def log_arbitrage_opportunity(self, opportunity_id: int, symbol: str,
                                 buy_exchange: str, sell_exchange: str,
                                 profit_rate: float, status: str):
        """记录套利机会日志"""
        extra_data = {
            'type': 'arbitrage_opportunity',
            'opportunity_id': opportunity_id,
            'symbol': symbol,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'profit_rate': profit_rate,
            'status': status
        }
        
        level = 'INFO'
        if profit_rate > 0.05:  # 5%以上利润率
            level = 'WARNING'  # 可能是异常数据
        
        message = f"套利机会: {symbol} {buy_exchange}->{sell_exchange} {profit_rate:.2%} - {status}"
        
        self.log_with_context(
            level, message, None, None, extra_data, 'arbitrage'
        )
    
    def log_risk_alert(self, alert_type: str, message: str, severity: str,
                      user_id: Optional[int] = None, extra_data: Optional[Dict[str, Any]] = None):
        """记录风险警报日志"""
        log_extra_data = {
            'type': 'risk_alert',
            'alert_type': alert_type,
            'severity': severity
        }
        
        if extra_data:
            log_extra_data.update(extra_data)
        
        level_map = {
            'low': 'INFO',
            'medium': 'WARNING',
            'high': 'ERROR',
            'critical': 'CRITICAL'
        }
        
        level = level_map.get(severity, 'WARNING')
        log_message = f"风险警报 [{alert_type}]: {message}"
        
        self.log_with_context(
            level, log_message, user_id, None, log_extra_data, 'risk'
        )
    
    def log_system_event(self, event_type: str, message: str, 
                        extra_data: Optional[Dict[str, Any]] = None):
        """记录系统事件日志"""
        log_extra_data = {
            'type': 'system_event',
            'event_type': event_type
        }
        
        if extra_data:
            log_extra_data.update(extra_data)
        
        level = 'INFO'
        if event_type in ['error', 'failure', 'crash']:
            level = 'ERROR'
        elif event_type in ['warning', 'degraded']:
            level = 'WARNING'
        
        log_message = f"系统事件 [{event_type}]: {message}"
        
        self.log_with_context(
            level, log_message, None, None, log_extra_data, 'system'
        )
    
    async def cleanup_old_logs(self, days: int = 30):
        """清理旧日志记录"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with get_async_session() as session:
                # 删除旧的数据库日志
                result = await session.execute(
                    "DELETE FROM system_logs WHERE created_at < :cutoff_date",
                    {'cutoff_date': cutoff_date}
                )
                deleted_count = result.rowcount
                await session.commit()
                
                self.logger.info(f"清理了 {deleted_count} 条旧日志记录")
                
        except Exception as e:
            self.logger.error(f"清理旧日志失败: {e}")
    
    def close(self):
        """关闭日志服务"""
        if self.db_handler:
            self.db_handler.close()
        
        for handler in self.logger.handlers:
            handler.close()
        
        self.logger.info("日志服务已关闭")


# 全局日志服务实例
logging_service = LoggingService()
logger = logging_service.get_logger()


# 便捷函数
def get_logger(name: str = None) -> logging.Logger:
    """获取日志器的便捷函数"""
    return logging_service.get_logger(name)


def log_api_request(method: str, url: str, status_code: int, response_time: float,
                   user_id: Optional[int] = None, request_id: Optional[str] = None):
    """记录API请求的便捷函数"""
    logging_service.log_api_request(method, url, status_code, response_time, user_id, request_id)


def log_trade_execution(trade_id: int, symbol: str, side: str, quantity: float,
                       price: float, status: str, user_id: Optional[int] = None):
    """记录交易执行的便捷函数"""
    logging_service.log_trade_execution(trade_id, symbol, side, quantity, price, status, user_id)


def log_arbitrage_opportunity(opportunity_id: int, symbol: str, buy_exchange: str,
                             sell_exchange: str, profit_rate: float, status: str):
    """记录套利机会的便捷函数"""
    logging_service.log_arbitrage_opportunity(
        opportunity_id, symbol, buy_exchange, sell_exchange, profit_rate, status
    )


def log_risk_alert(alert_type: str, message: str, severity: str,
                  user_id: Optional[int] = None, extra_data: Optional[Dict[str, Any]] = None):
    """记录风险警报的便捷函数"""
    logging_service.log_risk_alert(alert_type, message, severity, user_id, extra_data)


def log_system_event(event_type: str, message: str, extra_data: Optional[Dict[str, Any]] = None):
    """记录系统事件的便捷函数"""
    logging_service.log_system_event(event_type, message, extra_data)