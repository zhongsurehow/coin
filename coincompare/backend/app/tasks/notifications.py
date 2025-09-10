from celery import current_app
from typing import List, Dict, Any, Optional
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

from ..celery_app import task_with_retry, urgent_task
from ..database import get_async_session
from ..models import User, RiskAlert, Trade, Strategy
from ..config import settings
from sqlalchemy import select, and_, desc

logger = logging.getLogger(__name__)

@urgent_task(name="app.tasks.notifications.send_risk_alert")
def send_risk_alert(self, alert_id: int, notification_types: List[str] = None):
    """发送风险警报通知任务（高优先级）"""
    try:
        if not notification_types:
            notification_types = ["email", "telegram"]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_send_risk_alert_async(alert_id, notification_types))
        loop.close()
        
        logger.info(f"Risk alert notification sent: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Risk alert notification failed: {str(e)}")
        raise self.retry(countdown=30, max_retries=5)

async def _send_risk_alert_async(alert_id: int, notification_types: List[str]):
    """异步发送风险警报通知"""
    try:
        async with get_async_session() as session:
            # 获取警报信息
            alert_result = await session.execute(
                select(RiskAlert).where(RiskAlert.id == alert_id)
            )
            alert = alert_result.scalar_one_or_none()
            
            if not alert:
                return {"error": "Alert not found"}
            
            # 获取用户信息
            user_result = await session.execute(
                select(User).where(User.id == alert.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return {"error": "User not found"}
            
            # 准备通知内容
            notification_content = _prepare_risk_alert_content(alert, user)
            
            # 发送通知
            notification_results = []
            
            for notification_type in notification_types:
                try:
                    if notification_type == "email" and user.email:
                        result = await _send_email_notification(user.email, notification_content)
                        notification_results.append({"type": "email", "result": result})
                    
                    elif notification_type == "telegram" and user.telegram_chat_id:
                        result = await _send_telegram_notification(user.telegram_chat_id, notification_content)
                        notification_results.append({"type": "telegram", "result": result})
                    
                    elif notification_type == "slack" and settings.slack_webhook_url:
                        result = await _send_slack_notification(notification_content)
                        notification_results.append({"type": "slack", "result": result})
                    
                except Exception as e:
                    logger.error(f"Failed to send {notification_type} notification: {str(e)}")
                    notification_results.append({"type": notification_type, "result": {"success": False, "error": str(e)}})
            
            # 更新警报状态
            alert.notification_sent = True
            alert.notification_sent_at = datetime.utcnow()
            await session.commit()
            
            return {
                "alert_id": alert_id,
                "user_id": user.id,
                "notification_results": notification_results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async risk alert notification failed: {str(e)}")
        raise

def _prepare_risk_alert_content(alert: RiskAlert, user: User) -> Dict[str, str]:
    """准备风险警报通知内容"""
    try:
        severity_emoji = {
            "low": "🟡",
            "medium": "🟠",
            "high": "🔴"
        }
        
        emoji = severity_emoji.get(alert.severity, "⚠️")
        
        subject = f"{emoji} 风险警报 - {alert.alert_type}"
        
        content = f"""
{emoji} **风险警报通知**

**用户**: {user.username}
**警报类型**: {alert.alert_type}
**严重程度**: {alert.severity.upper()}
**警报信息**: {alert.message}
**触发值**: {alert.value}
**阈值**: {alert.threshold}
**时间**: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}

请及时关注并采取相应措施。

---
CoinCompare 风险监控系统
        """.strip()
        
        return {
            "subject": subject,
            "content": content,
            "html_content": content.replace("\n", "<br>").replace("**", "<strong>").replace("**", "</strong>")
        }
        
    except Exception as e:
        logger.error(f"Failed to prepare risk alert content: {str(e)}")
        return {"subject": "风险警报", "content": "风险警报通知", "html_content": "风险警报通知"}

async def _send_email_notification(email: str, content: Dict[str, str]) -> Dict[str, Any]:
    """发送邮件通知"""
    try:
        if not settings.smtp_server or not settings.smtp_username:
            return {"success": False, "error": "SMTP not configured"}
        
        # 创建邮件
        msg = MIMEMultipart('alternative')
        msg['Subject'] = content["subject"]
        msg['From'] = settings.smtp_username
        msg['To'] = email
        
        # 添加文本和HTML内容
        text_part = MIMEText(content["content"], 'plain', 'utf-8')
        html_part = MIMEText(content["html_content"], 'html', 'utf-8')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        # 发送邮件
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        
        return {"success": True, "message": "Email sent successfully"}
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        return {"success": False, "error": str(e)}

async def _send_telegram_notification(chat_id: str, content: Dict[str, str]) -> Dict[str, Any]:
    """发送Telegram通知"""
    try:
        if not settings.telegram_bot_token:
            return {"success": False, "error": "Telegram bot token not configured"}
        
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": content["content"],
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        return {"success": True, "message": "Telegram message sent successfully"}
        
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {str(e)}")
        return {"success": False, "error": str(e)}

async def _send_slack_notification(content: Dict[str, str]) -> Dict[str, Any]:
    """发送Slack通知"""
    try:
        if not settings.slack_webhook_url:
            return {"success": False, "error": "Slack webhook URL not configured"}
        
        payload = {
            "text": content["subject"],
            "attachments": [
                {
                    "color": "danger",
                    "text": content["content"],
                    "ts": int(datetime.utcnow().timestamp())
                }
            ]
        }
        
        response = requests.post(settings.slack_webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        
        return {"success": True, "message": "Slack message sent successfully"}
        
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {str(e)}")
        return {"success": False, "error": str(e)}

@task_with_retry(name="app.tasks.notifications.send_trade_notification")
def send_trade_notification(self, trade_id: int, notification_types: List[str] = None):
    """发送交易通知任务"""
    try:
        if not notification_types:
            notification_types = ["email"]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_send_trade_notification_async(trade_id, notification_types))
        loop.close()
        
        logger.info(f"Trade notification sent: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Trade notification failed: {str(e)}")
        raise self.retry(countdown=60, max_retries=3)

async def _send_trade_notification_async(trade_id: int, notification_types: List[str]):
    """异步发送交易通知"""
    try:
        async with get_async_session() as session:
            # 获取交易信息
            trade_result = await session.execute(
                select(Trade).where(Trade.id == trade_id)
            )
            trade = trade_result.scalar_one_or_none()
            
            if not trade:
                return {"error": "Trade not found"}
            
            # 获取用户信息
            user_result = await session.execute(
                select(User).where(User.id == trade.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return {"error": "User not found"}
            
            # 获取策略信息
            strategy = None
            if trade.strategy_id:
                strategy_result = await session.execute(
                    select(Strategy).where(Strategy.id == trade.strategy_id)
                )
                strategy = strategy_result.scalar_one_or_none()
            
            # 准备通知内容
            notification_content = _prepare_trade_notification_content(trade, user, strategy)
            
            # 发送通知
            notification_results = []
            
            for notification_type in notification_types:
                try:
                    if notification_type == "email" and user.email:
                        result = await _send_email_notification(user.email, notification_content)
                        notification_results.append({"type": "email", "result": result})
                    
                    elif notification_type == "telegram" and user.telegram_chat_id:
                        result = await _send_telegram_notification(user.telegram_chat_id, notification_content)
                        notification_results.append({"type": "telegram", "result": result})
                    
                except Exception as e:
                    logger.error(f"Failed to send {notification_type} notification: {str(e)}")
                    notification_results.append({"type": notification_type, "result": {"success": False, "error": str(e)}})
            
            return {
                "trade_id": trade_id,
                "user_id": user.id,
                "notification_results": notification_results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async trade notification failed: {str(e)}")
        raise

def _prepare_trade_notification_content(trade: Trade, user: User, strategy: Strategy = None) -> Dict[str, str]:
    """准备交易通知内容"""
    try:
        profit_loss = float(trade.profit_loss or 0)
        emoji = "📈" if profit_loss > 0 else "📉" if profit_loss < 0 else "➡️"
        
        subject = f"{emoji} 交易通知 - {trade.symbol} {trade.side.upper()}"
        
        strategy_info = f"\n**策略**: {strategy.name}" if strategy else ""
        
        content = f"""
{emoji} **交易执行通知**

**用户**: {user.username}
**交易对**: {trade.symbol}
**交易所**: {trade.exchange}
**方向**: {trade.side.upper()}
**数量**: {trade.amount}
**价格**: ${trade.price}
**手续费**: ${trade.fee or 0}
**盈亏**: ${profit_loss:.2f}
**状态**: {trade.status}{strategy_info}
**时间**: {trade.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---
CoinCompare 交易系统
        """.strip()
        
        return {
            "subject": subject,
            "content": content,
            "html_content": content.replace("\n", "<br>").replace("**", "<strong>").replace("**", "</strong>")
        }
        
    except Exception as e:
        logger.error(f"Failed to prepare trade notification content: {str(e)}")
        return {"subject": "交易通知", "content": "交易执行通知", "html_content": "交易执行通知"}

@task_with_retry(name="app.tasks.notifications.send_daily_report")
def send_daily_report(self, user_id: int = None):
    """发送每日报告任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_send_daily_report_async(user_id))
        loop.close()
        
        logger.info(f"Daily report sent: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Daily report failed: {str(e)}")
        raise self.retry(countdown=300, max_retries=2)

async def _send_daily_report_async(user_id: Optional[int]):
    """异步发送每日报告"""
    try:
        async with get_async_session() as session:
            # 获取需要发送报告的用户
            if user_id:
                users_query = select(User).where(User.id == user_id)
            else:
                users_query = select(User).where(
                    and_(
                        User.is_active == True,
                        User.email_notifications == True
                    )
                )
            
            users_result = await session.execute(users_query)
            users = users_result.scalars().all()
            
            report_results = []
            
            for user in users:
                try:
                    # 生成用户日报
                    report_data = await _generate_daily_report_data(session, user)
                    
                    # 准备报告内容
                    report_content = _prepare_daily_report_content(user, report_data)
                    
                    # 发送邮件
                    if user.email:
                        email_result = await _send_email_notification(user.email, report_content)
                        report_results.append({
                            "user_id": user.id,
                            "email_result": email_result,
                            "report_data": report_data
                        })
                    
                except Exception as e:
                    logger.error(f"Failed to send daily report for user {user.id}: {str(e)}")
                    continue
            
            return {
                "users_processed": len(users),
                "reports_sent": len([r for r in report_results if r["email_result"]["success"]]),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Async daily report failed: {str(e)}")
        raise

async def _generate_daily_report_data(session, user: User) -> Dict[str, Any]:
    """生成用户日报数据"""
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        today = datetime.utcnow()
        
        # 获取昨日交易数据
        trades_result = await session.execute(
            select(Trade).where(
                and_(
                    Trade.user_id == user.id,
                    Trade.created_at >= yesterday,
                    Trade.created_at < today
                )
            )
        )
        trades = trades_result.scalars().all()
        
        # 获取活跃策略数据
        strategies_result = await session.execute(
            select(Strategy).where(
                and_(
                    Strategy.user_id == user.id,
                    Strategy.status == "active"
                )
            )
        )
        strategies = strategies_result.scalars().all()
        
        # 获取风险警报数据
        alerts_result = await session.execute(
            select(RiskAlert).where(
                and_(
                    RiskAlert.user_id == user.id,
                    RiskAlert.created_at >= yesterday,
                    RiskAlert.created_at < today
                )
            )
        )
        alerts = alerts_result.scalars().all()
        
        # 计算统计数据
        total_trades = len(trades)
        total_pnl = sum(float(trade.profit_loss or 0) for trade in trades)
        profitable_trades = len([trade for trade in trades if float(trade.profit_loss or 0) > 0])
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "date": yesterday.strftime('%Y-%m-%d'),
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "active_strategies": len(strategies),
            "risk_alerts": len(alerts),
            "high_risk_alerts": len([alert for alert in alerts if alert.severity == "high"]),
            "trades_by_symbol": _group_trades_by_symbol(trades),
            "top_performing_strategy": _get_top_performing_strategy(trades, strategies)
        }
        
    except Exception as e:
        logger.error(f"Failed to generate daily report data: {str(e)}")
        return {}

def _group_trades_by_symbol(trades: List[Trade]) -> Dict[str, Dict[str, Any]]:
    """按交易对分组交易数据"""
    try:
        symbol_data = {}
        
        for trade in trades:
            symbol = trade.symbol
            if symbol not in symbol_data:
                symbol_data[symbol] = {
                    "count": 0,
                    "total_pnl": 0,
                    "volume": 0
                }
            
            symbol_data[symbol]["count"] += 1
            symbol_data[symbol]["total_pnl"] += float(trade.profit_loss or 0)
            symbol_data[symbol]["volume"] += float(trade.amount)
        
        return symbol_data
        
    except Exception as e:
        logger.error(f"Failed to group trades by symbol: {str(e)}")
        return {}

def _get_top_performing_strategy(trades: List[Trade], strategies: List[Strategy]) -> Optional[Dict[str, Any]]:
    """获取表现最佳的策略"""
    try:
        strategy_performance = {}
        
        for trade in trades:
            if trade.strategy_id:
                if trade.strategy_id not in strategy_performance:
                    strategy_performance[trade.strategy_id] = {
                        "total_pnl": 0,
                        "trade_count": 0
                    }
                
                strategy_performance[trade.strategy_id]["total_pnl"] += float(trade.profit_loss or 0)
                strategy_performance[trade.strategy_id]["trade_count"] += 1
        
        if not strategy_performance:
            return None
        
        # 找到盈利最高的策略
        best_strategy_id = max(strategy_performance.keys(), key=lambda x: strategy_performance[x]["total_pnl"])
        best_strategy = next((s for s in strategies if s.id == best_strategy_id), None)
        
        if best_strategy:
            return {
                "name": best_strategy.name,
                "total_pnl": strategy_performance[best_strategy_id]["total_pnl"],
                "trade_count": strategy_performance[best_strategy_id]["trade_count"]
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get top performing strategy: {str(e)}")
        return None

def _prepare_daily_report_content(user: User, report_data: Dict[str, Any]) -> Dict[str, str]:
    """准备每日报告内容"""
    try:
        date = report_data.get("date", "今日")
        total_pnl = report_data.get("total_pnl", 0)
        pnl_emoji = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➡️"
        
        subject = f"📊 每日交易报告 - {date}"
        
        # 构建交易对统计
        symbol_stats = ""
        trades_by_symbol = report_data.get("trades_by_symbol", {})
        for symbol, data in list(trades_by_symbol.items())[:5]:  # 只显示前5个
            symbol_stats += f"  • {symbol}: {data['count']}笔交易, ${data['total_pnl']:.2f}\n"
        
        # 最佳策略信息
        top_strategy = report_data.get("top_performing_strategy")
        top_strategy_info = ""
        if top_strategy:
            top_strategy_info = f"\n**最佳策略**: {top_strategy['name']} (${top_strategy['total_pnl']:.2f})"
        
        content = f"""
📊 **每日交易报告** - {date}

**用户**: {user.username}

**交易概览**:
• 总交易数: {report_data.get('total_trades', 0)}笔
• 总盈亏: {pnl_emoji} ${total_pnl:.2f}
• 胜率: {report_data.get('win_rate', 0):.1f}%
• 活跃策略: {report_data.get('active_strategies', 0)}个

**风险警报**:
• 总警报数: {report_data.get('risk_alerts', 0)}个
• 高风险警报: {report_data.get('high_risk_alerts', 0)}个

**交易对统计**:
{symbol_stats.rstrip()}{top_strategy_info}

---
CoinCompare 每日报告系统
        """.strip()
        
        return {
            "subject": subject,
            "content": content,
            "html_content": content.replace("\n", "<br>").replace("**", "<strong>").replace("**", "</strong>")
        }
        
    except Exception as e:
        logger.error(f"Failed to prepare daily report content: {str(e)}")
        return {"subject": "每日报告", "content": "每日交易报告", "html_content": "每日交易报告"}

@task_with_retry(name="app.tasks.notifications.send_system_notification")
def send_system_notification(self, message: str, severity: str = "info", notification_types: List[str] = None):
    """发送系统通知任务"""
    try:
        if not notification_types:
            notification_types = ["slack"]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_send_system_notification_async(message, severity, notification_types))
        loop.close()
        
        logger.info(f"System notification sent: {result}")
        return result
        
    except Exception as e:
        logger.error(f"System notification failed: {str(e)}")
        raise self.retry(countdown=60, max_retries=3)

async def _send_system_notification_async(message: str, severity: str, notification_types: List[str]):
    """异步发送系统通知"""
    try:
        severity_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅"
        }
        
        emoji = severity_emoji.get(severity, "📢")
        
        notification_content = {
            "subject": f"{emoji} 系统通知 - {severity.upper()}",
            "content": f"{emoji} **系统通知**\n\n{message}\n\n时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\nCoinCompare 系统",
            "html_content": f"{emoji} <strong>系统通知</strong><br><br>{message}<br><br>时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}<br><br>---<br>CoinCompare 系统"
        }
        
        notification_results = []
        
        for notification_type in notification_types:
            try:
                if notification_type == "slack":
                    result = await _send_slack_notification(notification_content)
                    notification_results.append({"type": "slack", "result": result})
                
                elif notification_type == "telegram" and settings.telegram_admin_chat_id:
                    result = await _send_telegram_notification(settings.telegram_admin_chat_id, notification_content)
                    notification_results.append({"type": "telegram", "result": result})
                
            except Exception as e:
                logger.error(f"Failed to send {notification_type} system notification: {str(e)}")
                notification_results.append({"type": notification_type, "result": {"success": False, "error": str(e)}})
        
        return {
            "message": message,
            "severity": severity,
            "notification_results": notification_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Async system notification failed: {str(e)}")
        raise

# 导出任务函数
__all__ = [
    "send_risk_alert",
    "send_trade_notification",
    "send_daily_report",
    "send_system_notification"
]