"""WebSocket API端点

提供实时数据推送和通知功能。
"""

import asyncio
import logging
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer

from ..services.notification_service import websocket_manager
from ..core.auth import get_user_id_from_token
from ..services.logging_service import logging_service

logger = logging.getLogger(__name__)
security = HTTPBearer()

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/notifications/{token}")
async def websocket_notifications(websocket: WebSocket, token: str):
    """WebSocket通知端点"""
    try:
        # 验证token并获取用户ID
        user_id = get_user_id_from_token(token)
        
        # 建立WebSocket连接
        await websocket_manager.connect(user_id, websocket)
        
        # 记录连接日志
        await logging_service.log_websocket_connection(
            user_id=user_id,
            action="connect",
            ip_address=websocket.client.host if websocket.client else "unknown"
        )
        
        try:
            # 保持连接并处理消息
            while True:
                # 接收客户端消息
                data = await websocket.receive_text()
                
                # 处理心跳包
                if data == "ping":
                    await websocket.send_text("pong")
                    continue
                
                # 处理其他消息类型
                try:
                    import json
                    message = json.loads(data)
                    await handle_websocket_message(user_id, message, websocket)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid JSON format"
                    })
                
        except WebSocketDisconnect:
            logger.info(f"用户 {user_id} WebSocket连接断开")
        
    except Exception as e:
        logger.error(f"WebSocket连接错误: {e}")
        try:
            await websocket.close(code=1000)
        except:
            pass
    
    finally:
        # 清理连接
        try:
            await websocket_manager.disconnect(user_id, websocket)
            await logging_service.log_websocket_connection(
                user_id=user_id,
                action="disconnect",
                ip_address=websocket.client.host if websocket.client else "unknown"
            )
        except:
            pass


async def handle_websocket_message(
    user_id: int,
    message: Dict[str, Any],
    websocket: WebSocket
):
    """处理WebSocket消息"""
    try:
        message_type = message.get("type")
        
        if message_type == "subscribe":
            # 订阅特定类型的通知
            await handle_subscription(user_id, message, websocket)
        
        elif message_type == "unsubscribe":
            # 取消订阅
            await handle_unsubscription(user_id, message, websocket)
        
        elif message_type == "get_status":
            # 获取实时状态
            await handle_status_request(user_id, message, websocket)
        
        else:
            await websocket.send_json({
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            })
    
    except Exception as e:
        logger.error(f"处理WebSocket消息失败: {e}")
        await websocket.send_json({
            "type": "error",
            "message": "Message processing failed"
        })


async def handle_subscription(
    user_id: int,
    message: Dict[str, Any],
    websocket: WebSocket
):
    """处理订阅请求"""
    subscription_type = message.get("subscription_type")
    
    # 这里可以实现更细粒度的订阅控制
    # 例如：只订阅特定交易所的通知、特定币种的价格更新等
    
    await websocket.send_json({
        "type": "subscription_confirmed",
        "subscription_type": subscription_type,
        "message": f"已订阅 {subscription_type} 通知"
    })


async def handle_unsubscription(
    user_id: int,
    message: Dict[str, Any],
    websocket: WebSocket
):
    """处理取消订阅请求"""
    subscription_type = message.get("subscription_type")
    
    await websocket.send_json({
        "type": "unsubscription_confirmed",
        "subscription_type": subscription_type,
        "message": f"已取消订阅 {subscription_type} 通知"
    })


async def handle_status_request(
    user_id: int,
    message: Dict[str, Any],
    websocket: WebSocket
):
    """处理状态查询请求"""
    try:
        from ..services.enhanced_deposit_withdrawal_service import enhanced_deposit_withdrawal_service
        
        transaction_id = message.get("transaction_id")
        if not transaction_id:
            await websocket.send_json({
                "type": "error",
                "message": "Missing transaction_id"
            })
            return
        
        # 获取实时状态
        status = await enhanced_deposit_withdrawal_service.get_real_time_status(
            user_id=user_id,
            transaction_id=transaction_id
        )
        
        if status:
            await websocket.send_json({
                "type": "transaction_status",
                "data": {
                    "transaction_id": status.transaction_id,
                    "current_status": status.current_status.value if hasattr(status.current_status, 'value') else str(status.current_status),
                    "confirmations": status.confirmations,
                    "required_confirmations": status.required_confirmations,
                    "estimated_completion": status.estimated_completion.isoformat(),
                    "last_updated": status.last_updated.isoformat(),
                    "blockchain_url": status.blockchain_url
                }
            })
        else:
            await websocket.send_json({
                "type": "error",
                "message": "Transaction not found"
            })
    
    except Exception as e:
        logger.error(f"处理状态查询失败: {e}")
        await websocket.send_json({
            "type": "error",
            "message": "Status query failed"
        })


@router.websocket("/market-data/{token}")
async def websocket_market_data(websocket: WebSocket, token: str):
    """市场数据WebSocket端点"""
    try:
        # 验证token
        user_id = get_user_id_from_token(token)
        
        await websocket.accept()
        logger.info(f"用户 {user_id} 连接到市场数据WebSocket")
        
        try:
            while True:
                # 这里可以推送实时市场数据
                # 例如：价格更新、套利机会、交易量变化等
                
                # 模拟数据推送
                await asyncio.sleep(5)
                
                # 发送心跳
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time()
                })
                
        except WebSocketDisconnect:
            logger.info(f"用户 {user_id} 市场数据WebSocket连接断开")
    
    except Exception as e:
        logger.error(f"市场数据WebSocket错误: {e}")
        try:
            await websocket.close()
        except:
            pass


@router.websocket("/arbitrage/{token}")
async def websocket_arbitrage(websocket: WebSocket, token: str):
    """套利机会WebSocket端点"""
    try:
        # 验证token
        user_id = get_user_id_from_token(token)
        
        await websocket.accept()
        logger.info(f"用户 {user_id} 连接到套利WebSocket")
        
        try:
            while True:
                # 这里可以推送实时套利机会
                await asyncio.sleep(10)
                
                # 发送心跳
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time()
                })
                
        except WebSocketDisconnect:
            logger.info(f"用户 {user_id} 套利WebSocket连接断开")
    
    except Exception as e:
        logger.error(f"套利WebSocket错误: {e}")
        try:
            await websocket.close()
        except:
            pass


# 广播函数
async def broadcast_market_update(data: Dict[str, Any]):
    """广播市场更新"""
    message = {
        "type": "market_update",
        "data": data,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    await websocket_manager.broadcast(message)


async def broadcast_arbitrage_opportunity(data: Dict[str, Any]):
    """广播套利机会"""
    message = {
        "type": "arbitrage_opportunity",
        "data": data,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    await websocket_manager.broadcast(message)


async def broadcast_system_notification(title: str, message: str, level: str = "info"):
    """广播系统通知"""
    notification = {
        "type": "system_notification",
        "title": title,
        "message": message,
        "level": level,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    await websocket_manager.broadcast(notification)