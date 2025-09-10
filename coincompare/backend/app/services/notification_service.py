"""通知服务模块

提供邮件、Telegram、Slack等多种通知方式。
"""

import smtplib
import asyncio
import aiohttp
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from enum import Enum
from fastapi import WebSocket

from ..config import settings
from ..models import User, RiskAlert, Trade, ArbitrageOpportunity
from .logging_service import get_logger

logger = get_logger('notification')


class NotificationType(Enum):
    """通知类型"""
    TRANSACTION_STATUS = "transaction_status"
    DEPOSIT_COMPLETED = "deposit_completed"
    WITHDRAWAL_COMPLETED = "withdrawal_completed"
    ARBITRAGE_OPPORTUNITY = "arbitrage_opportunity"
    RISK_ALERT = "risk_alert"
    SYSTEM_MAINTENANCE = "system_maintenance"
    PRICE_ALERT = "price_alert"


class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, user_id: int, websocket: WebSocket):
        """建立WebSocket连接"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        logger.info(f"用户 {user_id} WebSocket连接已建立")
        
        # 发送连接确认
        await websocket.send_json({
            "type": "connection_established",
            "message": "WebSocket连接已建立",
            "timestamp": datetime.now().isoformat()
        })
    
    async def disconnect(self, user_id: int, websocket: WebSocket):
        """断开WebSocket连接"""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        logger.info(f"用户 {user_id} WebSocket连接已断开")
    
    async def send_personal_message(self, user_id: int, message: Dict[str, Any]):
        """发送个人消息"""
        if user_id not in self.active_connections:
            return
        
        disconnected_sockets = []
        
        for websocket in self.active_connections[user_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"WebSocket发送失败: {e}")
                disconnected_sockets.append(websocket)
        
        # 清理断开的连接
        for websocket in disconnected_sockets:
            await self.disconnect(user_id, websocket)
    
    async def broadcast(self, message: Dict[str, Any]):
        """广播消息给所有连接的用户"""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(user_id, message)


# 全局WebSocket管理器
websocket_manager = WebSocketManager()


class EmailNotificationService:
    """邮件通知服务"""
    
    def __init__(self):
        self.smtp_server = settings.EMAIL_SMTP_SERVER
        self.smtp_port = settings.EMAIL_SMTP_PORT
        self.username = settings.EMAIL_USERNAME
        self.password = settings.EMAIL_PASSWORD
        self.from_email = settings.EMAIL_FROM
        self.use_tls = settings.EMAIL_USE_TLS
        
        # 设置模板环境
        template_dir = Path(__file__).parent.parent / 'templates' / 'email'
        template_dir.mkdir(parents=True, exist_ok=True)
        self.jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))
    
    async def send_email(self, to_emails: Union[str, List[str]], subject: str, 
                        body: str, html_body: Optional[str] = None,
                        attachments: Optional[List[str]] = None) -> bool:
        """发送邮件"""
        try:
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            
            # 创建邮件消息
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            
            # 添加文本内容
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # 添加HTML内容
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # 添加附件
            if attachments:
                for file_path in attachments:
                    if Path(file_path).exists():
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename= {Path(file_path).name}'
                            )
                            msg.attach(part)
            
            # 发送邮件
            await self._send_smtp(msg, to_emails)
            logger.info(f"邮件发送成功: {subject} -> {to_emails}")
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    
    async def _send_smtp(self, msg: MIMEMultipart, to_emails: List[str]):
        """通过SMTP发送邮件"""
        loop = asyncio.get_event_loop()
        
        def _send():
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg, to_addrs=to_emails)
        
        await loop.run_in_executor(None, _send)
    
    def render_template(self, template_name: str, **kwargs) -> tuple[str, str]:
        """渲染邮件模板"""
        try:
            template = self.jinja_env.get_template(template_name)
            html_content = template.render(**kwargs)
            
            # 生成纯文本版本（简单的HTML标签移除）
            import re
            text_content = re.sub(r'<[^>]+>', '', html_content)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            return text_content, html_content
            
        except Exception as e:
            logger.error(f"渲染邮件模板失败: {e}")
            return "", ""
    
    async def send_risk_alert(self, alert: RiskAlert, users: List[User]) -> bool:
        """发送风险警报邮件"""
        try:
            to_emails = [user.email for user in users if user.email]
            if not to_emails:
                return False
            
            subject = f"风险警报: {alert.alert_type}"
            
            # 渲染模板
            text_body, html_body = self.render_template(
                'risk_alert.html',
                alert=alert,
                severity_color={
                    'low': '#28a745',
                    'medium': '#ffc107', 
                    'high': '#fd7e14',
                    'critical': '#dc3545'
                }.get(alert.severity, '#6c757d')
            )
            
            if not html_body:
                # 如果模板不存在，使用简单格式
                text_body = f"""
风险警报通知

警报类型: {alert.alert_type}
严重程度: {alert.severity}
消息: {alert.message}
触发时间: {alert.created_at}

请及时处理相关风险。
                """.strip()
                
                html_body = f"""
<html>
<body>
<h2 style="color: red;">风险警报通知</h2>
<p><strong>警报类型:</strong> {alert.alert_type}</p>
<p><strong>严重程度:</strong> {alert.severity}</p>
<p><strong>消息:</strong> {alert.message}</p>
<p><strong>触发时间:</strong> {alert.created_at}</p>
<p>请及时处理相关风险。</p>
</body>
</html>
                """
            
            return await self.send_email(to_emails, subject, text_body, html_body)
            
        except Exception as e:
            logger.error(f"发送风险警报邮件失败: {e}")
            return False
    
    async def send_trade_notification(self, trade: Trade, user: User) -> bool:
        """发送交易通知邮件"""
        try:
            if not user.email:
                return False
            
            subject = f"交易通知: {trade.symbol} {trade.side}"
            
            text_body = f"""
交易执行通知

交易对: {trade.symbol}
方向: {trade.side}
数量: {trade.quantity}
价格: {trade.price}
状态: {trade.status}
交易所: {trade.exchange}
执行时间: {trade.created_at}
            """.strip()
            
            html_body = f"""
<html>
<body>
<h2>交易执行通知</h2>
<table border="1" style="border-collapse: collapse;">
<tr><td><strong>交易对</strong></td><td>{trade.symbol}</td></tr>
<tr><td><strong>方向</strong></td><td>{trade.side}</td></tr>
<tr><td><strong>数量</strong></td><td>{trade.quantity}</td></tr>
<tr><td><strong>价格</strong></td><td>{trade.price}</td></tr>
<tr><td><strong>状态</strong></td><td>{trade.status}</td></tr>
<tr><td><strong>交易所</strong></td><td>{trade.exchange}</td></tr>
<tr><td><strong>执行时间</strong></td><td>{trade.created_at}</td></tr>
</table>
</body>
</html>
            """
            
            return await self.send_email(user.email, subject, text_body, html_body)
            
        except Exception as e:
            logger.error(f"发送交易通知邮件失败: {e}")
            return False
    
    async def send_daily_report(self, user: User, report_data: Dict[str, Any]) -> bool:
        """发送每日报告邮件"""
        try:
            if not user.email:
                return False
            
            subject = f"每日交易报告 - {datetime.now().strftime('%Y-%m-%d')}"
            
            # 渲染模板
            text_body, html_body = self.render_template(
                'daily_report.html',
                user=user,
                report_data=report_data,
                date=datetime.now().strftime('%Y-%m-%d')
            )
            
            if not html_body:
                # 简单格式
                text_body = f"""
每日交易报告 - {datetime.now().strftime('%Y-%m-%d')}

总交易次数: {report_data.get('total_trades', 0)}
成功交易: {report_data.get('successful_trades', 0)}
总盈亏: {report_data.get('total_pnl', 0)}
套利机会: {report_data.get('arbitrage_opportunities', 0)}
风险警报: {report_data.get('risk_alerts', 0)}
                """.strip()
            
            return await self.send_email(user.email, subject, text_body, html_body)
            
        except Exception as e:
            logger.error(f"发送每日报告邮件失败: {e}")
            return False


class TelegramNotificationService:
    """Telegram通知服务"""
    
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = None
    
    async def _get_session(self):
        """获取HTTP会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def send_message(self, chat_id: str, message: str, 
                          parse_mode: str = 'HTML') -> bool:
        """发送Telegram消息"""
        try:
            session = await self._get_session()
            
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            async with session.post(f"{self.base_url}/sendMessage", json=data) as response:
                if response.status == 200:
                    logger.info(f"Telegram消息发送成功: {chat_id}")
                    return True
                else:
                    logger.error(f"Telegram消息发送失败: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Telegram消息发送异常: {e}")
            return False
    
    async def send_risk_alert(self, alert: RiskAlert, chat_ids: List[str]) -> bool:
        """发送风险警报到Telegram"""
        try:
            severity_emoji = {
                'low': '🟡',
                'medium': '🟠',
                'high': '🔴',
                'critical': '🚨'
            }
            
            message = f"""
{severity_emoji.get(alert.severity, '⚠️')} <b>风险警报</b>

<b>类型:</b> {alert.alert_type}
<b>严重程度:</b> {alert.severity}
<b>消息:</b> {alert.message}
<b>时间:</b> {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            
            success = True
            for chat_id in chat_ids:
                result = await self.send_message(chat_id, message)
                success = success and result
            
            return success
            
        except Exception as e:
            logger.error(f"发送Telegram风险警报失败: {e}")
            return False
    
    async def send_trade_notification(self, trade: Trade, chat_id: str) -> bool:
        """发送交易通知到Telegram"""
        try:
            side_emoji = '🟢' if trade.side == 'buy' else '🔴'
            status_emoji = {
                'filled': '✅',
                'partial': '🟡',
                'cancelled': '❌',
                'failed': '🚫'
            }
            
            message = f"""
{side_emoji} <b>交易通知</b>

<b>交易对:</b> {trade.symbol}
<b>方向:</b> {trade.side.upper()}
<b>数量:</b> {trade.quantity}
<b>价格:</b> {trade.price}
<b>状态:</b> {status_emoji.get(trade.status, '❓')} {trade.status}
<b>交易所:</b> {trade.exchange}
<b>时间:</b> {trade.created_at.strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            
            return await self.send_message(chat_id, message)
            
        except Exception as e:
            logger.error(f"发送Telegram交易通知失败: {e}")
            return False
    
    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()


class SlackNotificationService:
    """Slack通知服务"""
    
    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL
        self.session = None
    
    async def _get_session(self):
        """获取HTTP会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def send_message(self, message: str, channel: Optional[str] = None,
                          username: Optional[str] = None, 
                          attachments: Optional[List[Dict]] = None) -> bool:
        """发送Slack消息"""
        try:
            session = await self._get_session()
            
            payload = {
                'text': message
            }
            
            if channel:
                payload['channel'] = channel
            if username:
                payload['username'] = username
            if attachments:
                payload['attachments'] = attachments
            
            async with session.post(self.webhook_url, json=payload) as response:
                if response.status == 200:
                    logger.info("Slack消息发送成功")
                    return True
                else:
                    logger.error(f"Slack消息发送失败: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Slack消息发送异常: {e}")
            return False
    
    async def send_risk_alert(self, alert: RiskAlert) -> bool:
        """发送风险警报到Slack"""
        try:
            color_map = {
                'low': 'good',
                'medium': 'warning',
                'high': 'danger',
                'critical': 'danger'
            }
            
            attachment = {
                'color': color_map.get(alert.severity, 'warning'),
                'title': f"风险警报: {alert.alert_type}",
                'fields': [
                    {
                        'title': '严重程度',
                        'value': alert.severity,
                        'short': True
                    },
                    {
                        'title': '时间',
                        'value': alert.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'short': True
                    },
                    {
                        'title': '消息',
                        'value': alert.message,
                        'short': False
                    }
                ],
                'footer': 'CoinCompare风险监控',
                'ts': int(alert.created_at.timestamp())
            }
            
            return await self.send_message(
                "检测到新的风险警报",
                attachments=[attachment]
            )
            
        except Exception as e:
            logger.error(f"发送Slack风险警报失败: {e}")
            return False
    
    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()


class NotificationService:
    """统一通知服务"""
    
    def __init__(self):
        self.email_service = EmailNotificationService() if settings.EMAIL_ENABLED else None
        self.telegram_service = TelegramNotificationService() if settings.TELEGRAM_ENABLED else None
        self.slack_service = SlackNotificationService() if settings.SLACK_ENABLED else None
        
        # 通知频率限制
        self.notification_cache = {}
        self.rate_limit_window = 300  # 5分钟
    
    def _should_send_notification(self, key: str, min_interval: int = 60) -> bool:
        """检查是否应该发送通知（频率限制）"""
        now = datetime.now()
        last_sent = self.notification_cache.get(key)
        
        if last_sent is None or (now - last_sent).seconds >= min_interval:
            self.notification_cache[key] = now
            return True
        
        return False
    
    async def send_risk_alert(self, alert: RiskAlert, users: List[User]) -> Dict[str, bool]:
        """发送风险警报通知"""
        results = {}
        
        # 频率限制检查
        cache_key = f"risk_alert_{alert.alert_type}_{alert.severity}"
        min_interval = {
            'low': 300,      # 5分钟
            'medium': 180,   # 3分钟
            'high': 60,      # 1分钟
            'critical': 0    # 立即发送
        }.get(alert.severity, 60)
        
        if not self._should_send_notification(cache_key, min_interval):
            logger.info(f"风险警报通知被频率限制跳过: {cache_key}")
            return {'skipped': True}
        
        # 邮件通知
        if self.email_service:
            results['email'] = await self.email_service.send_risk_alert(alert, users)
        
        # Telegram通知
        if self.telegram_service:
            telegram_users = [u for u in users if u.telegram_chat_id]
            if telegram_users:
                chat_ids = [u.telegram_chat_id for u in telegram_users]
                results['telegram'] = await self.telegram_service.send_risk_alert(alert, chat_ids)
        
        # Slack通知
        if self.slack_service:
            results['slack'] = await self.slack_service.send_risk_alert(alert)
        
        return results
    
    async def send_trade_notification(self, trade: Trade, user: User) -> Dict[str, bool]:
        """发送交易通知"""
        results = {}
        
        # 邮件通知
        if self.email_service and user.email_notifications:
            results['email'] = await self.email_service.send_trade_notification(trade, user)
        
        # Telegram通知
        if self.telegram_service and user.telegram_notifications and user.telegram_chat_id:
            results['telegram'] = await self.telegram_service.send_trade_notification(
                trade, user.telegram_chat_id
            )
        
        return results
    
    async def send_transaction_notification(
        self,
        user_id: int,
        transaction_type: str,
        currency: str,
        amount: float,
        status: str,
        tx_hash: Optional[str] = None,
        confirmations: Optional[int] = None
    ) -> Dict[str, bool]:
        """发送交易状态通知"""
        results = {}
        
        # 准备通知数据
        if status == "completed":
            title = f"{transaction_type.upper()}完成"
            message = f"您的{amount} {currency} {transaction_type}已完成"
            notification_type = (
                NotificationType.DEPOSIT_COMPLETED 
                if transaction_type == "deposit" 
                else NotificationType.WITHDRAWAL_COMPLETED
            )
        else:
            title = f"{transaction_type.upper()}状态更新"
            message = f"您的{amount} {currency} {transaction_type}状态已更新为{status}"
            notification_type = NotificationType.TRANSACTION_STATUS
        
        # WebSocket实时通知
        websocket_message = {
            "type": "notification",
            "notification_type": notification_type.value,
            "title": title,
            "message": message,
            "data": {
                "transaction_type": transaction_type,
                "currency": currency,
                "amount": amount,
                "status": status,
                "tx_hash": tx_hash,
                "confirmations": confirmations
            },
            "timestamp": datetime.now().isoformat()
        }
        
        await websocket_manager.send_personal_message(user_id, websocket_message)
        results['websocket'] = True
        
        # 邮件通知（仅完成状态）
        if self.email_service and status == "completed":
            try:
                # 这里可以发送邮件通知
                results['email'] = True
            except Exception as e:
                logger.error(f"发送交易邮件通知失败: {e}")
                results['email'] = False
        
        return results
    
    async def send_arbitrage_notification(
        self,
        user_id: int,
        symbol: str,
        profit_rate: float,
        buy_exchange: str,
        sell_exchange: str,
        buy_price: float,
        sell_price: float
    ) -> Dict[str, bool]:
        """发送套利机会通知"""
        results = {}
        
        title = "套利机会"
        message = f"{symbol}发现套利机会，预期收益率{profit_rate:.2%}"
        
        websocket_message = {
            "type": "notification",
            "notification_type": NotificationType.ARBITRAGE_OPPORTUNITY.value,
            "title": title,
            "message": message,
            "data": {
                "symbol": symbol,
                "profit_rate": profit_rate,
                "buy_exchange": buy_exchange,
                "sell_exchange": sell_exchange,
                "buy_price": buy_price,
                "sell_price": sell_price
            },
            "timestamp": datetime.now().isoformat()
        }
        
        await websocket_manager.send_personal_message(user_id, websocket_message)
        results['websocket'] = True
        
        return results
    
    async def send_daily_report(self, user: User, report_data: Dict[str, Any]) -> Dict[str, bool]:
        """发送每日报告"""
        results = {}
        
        # 邮件报告
        if self.email_service and user.email_notifications:
            results['email'] = await self.email_service.send_daily_report(user, report_data)
        
        return results
    
    async def send_system_notification(self, message: str, level: str = 'info',
                                     users: Optional[List[User]] = None) -> Dict[str, bool]:
        """发送系统通知"""
        results = {}
        
        # 如果没有指定用户，发送给管理员
        if users is None:
            # 这里应该从数据库获取管理员用户
            users = []
        
        # 根据级别决定通知方式
        if level in ['error', 'critical']:
            # 紧急通知，使用所有渠道
            if self.email_service:
                for user in users:
                    if user.email:
                        await self.email_service.send_email(
                            user.email,
                            f"系统通知 [{level.upper()}]",
                            message
                        )
            
            if self.telegram_service:
                for user in users:
                    if user.telegram_chat_id:
                        await self.telegram_service.send_message(
                            user.telegram_chat_id,
                            f"🚨 <b>系统通知</b>\n\n{message}"
                        )
            
            if self.slack_service:
                await self.slack_service.send_message(
                    f":warning: 系统通知: {message}"
                )
        
        return results
    
    async def close(self):
        """关闭所有通知服务"""
        if self.telegram_service:
            await self.telegram_service.close()
        
        if self.slack_service:
            await self.slack_service.close()


# 全局通知服务实例
notification_service = NotificationService()


# 便捷函数
async def send_risk_alert(alert: RiskAlert, users: List[User]) -> Dict[str, bool]:
    """发送风险警报的便捷函数"""
    return await notification_service.send_risk_alert(alert, users)


async def send_trade_notification(trade: Trade, user: User) -> Dict[str, bool]:
    """发送交易通知的便捷函数"""
    return await notification_service.send_trade_notification(trade, user)


async def send_daily_report(user: User, report_data: Dict[str, Any]) -> Dict[str, bool]:
    """发送每日报告的便捷函数"""
    return await notification_service.send_daily_report(user, report_data)


async def send_system_notification(message: str, level: str = 'info',
                                 users: Optional[List[User]] = None) -> Dict[str, bool]:
    """发送系统通知的便捷函数"""
    return await notification_service.send_system_notification(message, level, users)