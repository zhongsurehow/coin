from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass
from enum import Enum
import asyncio
import logging
import json
from datetime import datetime, timedelta
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict
import uuid
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """WebSocket消息类型"""
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    ARBITRAGE = "arbitrage"
    ALERT = "alert"
    STATUS = "status"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    AUTH = "auth"
    STRATEGY_UPDATE = "strategy_update"
    PORTFOLIO_UPDATE = "portfolio_update"
    RISK_UPDATE = "risk_update"

@dataclass
class WebSocketMessage:
    """WebSocket消息"""
    type: MessageType
    data: Dict[str, Any]
    timestamp: datetime
    client_id: Optional[str] = None
    request_id: Optional[str] = None

@dataclass
class ClientConnection:
    """客户端连接信息"""
    client_id: str
    websocket: WebSocket
    connected_at: datetime
    last_heartbeat: datetime
    subscriptions: Set[str]
    user_id: Optional[str] = None
    is_authenticated: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.subscriptions is None:
            self.subscriptions = set()

class SubscriptionManager:
    """订阅管理器"""
    
    def __init__(self):
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)  # {topic: {client_ids}}
        self.client_subscriptions: Dict[str, Set[str]] = defaultdict(set)  # {client_id: {topics}}
    
    def subscribe(self, client_id: str, topic: str):
        """添加订阅"""
        self.subscriptions[topic].add(client_id)
        self.client_subscriptions[client_id].add(topic)
        logger.debug(f"Client {client_id} subscribed to {topic}")
    
    def unsubscribe(self, client_id: str, topic: str):
        """取消订阅"""
        self.subscriptions[topic].discard(client_id)
        self.client_subscriptions[client_id].discard(topic)
        
        # 清理空的订阅
        if not self.subscriptions[topic]:
            del self.subscriptions[topic]
        
        logger.debug(f"Client {client_id} unsubscribed from {topic}")
    
    def unsubscribe_all(self, client_id: str):
        """取消客户端的所有订阅"""
        topics = self.client_subscriptions.get(client_id, set()).copy()
        
        for topic in topics:
            self.unsubscribe(client_id, topic)
        
        if client_id in self.client_subscriptions:
            del self.client_subscriptions[client_id]
        
        logger.debug(f"Unsubscribed client {client_id} from all topics")
    
    def get_subscribers(self, topic: str) -> Set[str]:
        """获取主题的订阅者"""
        return self.subscriptions.get(topic, set()).copy()
    
    def get_client_subscriptions(self, client_id: str) -> Set[str]:
        """获取客户端的订阅"""
        return self.client_subscriptions.get(client_id, set()).copy()
    
    def get_subscription_stats(self) -> Dict[str, Any]:
        """获取订阅统计"""
        return {
            'total_topics': len(self.subscriptions),
            'total_clients': len(self.client_subscriptions),
            'topics': {
                topic: len(clients) for topic, clients in self.subscriptions.items()
            }
        }

class MessageQueue:
    """消息队列"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queues: Dict[str, asyncio.Queue] = {}  # {client_id: queue}
    
    async def put(self, client_id: str, message: WebSocketMessage):
        """添加消息到队列"""
        if client_id not in self.queues:
            self.queues[client_id] = asyncio.Queue(maxsize=self.max_size)
        
        try:
            await self.queues[client_id].put(message)
        except asyncio.QueueFull:
            # 队列满时，移除最旧的消息
            try:
                await self.queues[client_id].get_nowait()
                await self.queues[client_id].put(message)
            except asyncio.QueueEmpty:
                pass
    
    async def get(self, client_id: str) -> Optional[WebSocketMessage]:
        """从队列获取消息"""
        if client_id not in self.queues:
            return None
        
        try:
            return await asyncio.wait_for(self.queues[client_id].get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None
    
    def remove_client(self, client_id: str):
        """移除客户端队列"""
        if client_id in self.queues:
            del self.queues[client_id]

class WebSocketManager:
    """WebSocket管理器"""
    
    def __init__(self):
        self.connections: Dict[str, ClientConnection] = {}
        self.subscription_manager = SubscriptionManager()
        self.message_queue = MessageQueue()
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        self.connection_timeout = 60  # 连接超时（秒）
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 消息处理器
        self.message_handlers: Dict[MessageType, Callable] = {
            MessageType.SUBSCRIBE: self._handle_subscribe,
            MessageType.UNSUBSCRIBE: self._handle_unsubscribe,
            MessageType.HEARTBEAT: self._handle_heartbeat,
            MessageType.AUTH: self._handle_auth,
        }
    
    async def connect(self, websocket: WebSocket, client_id: str = None) -> str:
        """建立WebSocket连接"""
        await websocket.accept()
        
        if not client_id:
            client_id = str(uuid.uuid4())
        
        connection = ClientConnection(
            client_id=client_id,
            websocket=websocket,
            connected_at=datetime.utcnow(),
            last_heartbeat=datetime.utcnow(),
            subscriptions=set()
        )
        
        self.connections[client_id] = connection
        
        # 启动客户端消息处理任务
        asyncio.create_task(self._handle_client_messages(client_id))
        asyncio.create_task(self._send_client_messages(client_id))
        
        logger.info(f"WebSocket client {client_id} connected")
        
        # 发送连接确认消息
        await self.send_to_client(client_id, WebSocketMessage(
            type=MessageType.STATUS,
            data={
                'status': 'connected',
                'client_id': client_id,
                'server_time': datetime.utcnow().isoformat()
            },
            timestamp=datetime.utcnow()
        ))
        
        return client_id
    
    async def disconnect(self, client_id: str):
        """断开WebSocket连接"""
        if client_id in self.connections:
            connection = self.connections[client_id]
            
            # 取消所有订阅
            self.subscription_manager.unsubscribe_all(client_id)
            
            # 清理消息队列
            self.message_queue.remove_client(client_id)
            
            # 关闭WebSocket连接
            try:
                await connection.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket for client {client_id}: {e}")
            
            # 移除连接
            del self.connections[client_id]
            
            logger.info(f"WebSocket client {client_id} disconnected")
    
    async def _handle_client_messages(self, client_id: str):
        """处理客户端消息"""
        connection = self.connections.get(client_id)
        if not connection:
            return
        
        try:
            while client_id in self.connections:
                try:
                    # 接收消息
                    raw_message = await connection.websocket.receive_text()
                    
                    # 解析消息
                    try:
                        message_data = json.loads(raw_message)
                        message = WebSocketMessage(
                            type=MessageType(message_data.get('type')),
                            data=message_data.get('data', {}),
                            timestamp=datetime.utcnow(),
                            client_id=client_id,
                            request_id=message_data.get('request_id')
                        )
                        
                        # 处理消息
                        await self._process_message(message)
                        
                    except (json.JSONDecodeError, ValueError, KeyError) as e:
                        logger.warning(f"Invalid message from client {client_id}: {e}")
                        await self._send_error(client_id, f"Invalid message format: {e}")
                
                except WebSocketDisconnect:
                    logger.info(f"Client {client_id} disconnected")
                    break
                except Exception as e:
                    logger.error(f"Error handling message from client {client_id}: {e}")
                    break
        
        finally:
            await self.disconnect(client_id)
    
    async def _send_client_messages(self, client_id: str):
        """发送消息给客户端"""
        connection = self.connections.get(client_id)
        if not connection:
            return
        
        try:
            while client_id in self.connections:
                # 从队列获取消息
                message = await self.message_queue.get(client_id)
                
                if message:
                    try:
                        # 序列化消息
                        message_data = {
                            'type': message.type.value,
                            'data': message.data,
                            'timestamp': message.timestamp.isoformat()
                        }
                        
                        if message.request_id:
                            message_data['request_id'] = message.request_id
                        
                        # 发送消息
                        await connection.websocket.send_text(json.dumps(message_data))
                        
                    except Exception as e:
                        logger.error(f"Error sending message to client {client_id}: {e}")
                        break
        
        except Exception as e:
            logger.error(f"Error in message sender for client {client_id}: {e}")
    
    async def _process_message(self, message: WebSocketMessage):
        """处理收到的消息"""
        handler = self.message_handlers.get(message.type)
        
        if handler:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Error processing message {message.type}: {e}")
                await self._send_error(message.client_id, f"Error processing {message.type.value}: {e}")
        else:
            logger.warning(f"No handler for message type: {message.type}")
            await self._send_error(message.client_id, f"Unknown message type: {message.type.value}")
    
    async def _handle_subscribe(self, message: WebSocketMessage):
        """处理订阅消息"""
        client_id = message.client_id
        data = message.data
        
        topic = data.get('topic')
        if not topic:
            await self._send_error(client_id, "Missing topic in subscribe message")
            return
        
        # 添加订阅
        self.subscription_manager.subscribe(client_id, topic)
        
        # 更新连接信息
        if client_id in self.connections:
            self.connections[client_id].subscriptions.add(topic)
        
        # 发送确认
        await self.send_to_client(client_id, WebSocketMessage(
            type=MessageType.STATUS,
            data={
                'status': 'subscribed',
                'topic': topic
            },
            timestamp=datetime.utcnow(),
            request_id=message.request_id
        ))
    
    async def _handle_unsubscribe(self, message: WebSocketMessage):
        """处理取消订阅消息"""
        client_id = message.client_id
        data = message.data
        
        topic = data.get('topic')
        if not topic:
            await self._send_error(client_id, "Missing topic in unsubscribe message")
            return
        
        # 取消订阅
        self.subscription_manager.unsubscribe(client_id, topic)
        
        # 更新连接信息
        if client_id in self.connections:
            self.connections[client_id].subscriptions.discard(topic)
        
        # 发送确认
        await self.send_to_client(client_id, WebSocketMessage(
            type=MessageType.STATUS,
            data={
                'status': 'unsubscribed',
                'topic': topic
            },
            timestamp=datetime.utcnow(),
            request_id=message.request_id
        ))
    
    async def _handle_heartbeat(self, message: WebSocketMessage):
        """处理心跳消息"""
        client_id = message.client_id
        
        # 更新心跳时间
        if client_id in self.connections:
            self.connections[client_id].last_heartbeat = datetime.utcnow()
        
        # 发送心跳响应
        await self.send_to_client(client_id, WebSocketMessage(
            type=MessageType.HEARTBEAT,
            data={'pong': True},
            timestamp=datetime.utcnow(),
            request_id=message.request_id
        ))
    
    async def _handle_auth(self, message: WebSocketMessage):
        """处理认证消息"""
        client_id = message.client_id
        data = message.data
        
        # 这里应该实现实际的认证逻辑
        token = data.get('token')
        user_id = data.get('user_id')
        
        if token and user_id:
            # 简化的认证逻辑（实际应该验证token）
            if client_id in self.connections:
                self.connections[client_id].user_id = user_id
                self.connections[client_id].is_authenticated = True
            
            await self.send_to_client(client_id, WebSocketMessage(
                type=MessageType.STATUS,
                data={
                    'status': 'authenticated',
                    'user_id': user_id
                },
                timestamp=datetime.utcnow(),
                request_id=message.request_id
            ))
        else:
            await self._send_error(client_id, "Invalid authentication data")
    
    async def _send_error(self, client_id: str, error_message: str):
        """发送错误消息"""
        await self.send_to_client(client_id, WebSocketMessage(
            type=MessageType.ERROR,
            data={'error': error_message},
            timestamp=datetime.utcnow()
        ))
    
    async def send_to_client(self, client_id: str, message: WebSocketMessage):
        """发送消息给指定客户端"""
        if client_id in self.connections:
            await self.message_queue.put(client_id, message)
    
    async def broadcast_to_topic(self, topic: str, message: WebSocketMessage):
        """广播消息给订阅了指定主题的客户端"""
        subscribers = self.subscription_manager.get_subscribers(topic)
        
        for client_id in subscribers:
            await self.send_to_client(client_id, message)
    
    async def broadcast_to_all(self, message: WebSocketMessage):
        """广播消息给所有连接的客户端"""
        for client_id in self.connections:
            await self.send_to_client(client_id, message)
    
    async def send_ticker_update(self, exchange: str, symbol: str, ticker_data: Dict[str, Any]):
        """发送行情更新"""
        topic = f"ticker.{exchange}.{symbol}"
        
        message = WebSocketMessage(
            type=MessageType.TICKER,
            data={
                'exchange': exchange,
                'symbol': symbol,
                'ticker': ticker_data
            },
            timestamp=datetime.utcnow()
        )
        
        await self.broadcast_to_topic(topic, message)
    
    async def send_orderbook_update(self, exchange: str, symbol: str, orderbook_data: Dict[str, Any]):
        """发送订单簿更新"""
        topic = f"orderbook.{exchange}.{symbol}"
        
        message = WebSocketMessage(
            type=MessageType.ORDERBOOK,
            data={
                'exchange': exchange,
                'symbol': symbol,
                'orderbook': orderbook_data
            },
            timestamp=datetime.utcnow()
        )
        
        await self.broadcast_to_topic(topic, message)
    
    async def send_arbitrage_opportunity(self, opportunity: Dict[str, Any]):
        """发送套利机会"""
        topic = "arbitrage"
        
        message = WebSocketMessage(
            type=MessageType.ARBITRAGE,
            data=opportunity,
            timestamp=datetime.utcnow()
        )
        
        await self.broadcast_to_topic(topic, message)
    
    async def send_alert(self, alert_data: Dict[str, Any], user_id: str = None):
        """发送警报"""
        message = WebSocketMessage(
            type=MessageType.ALERT,
            data=alert_data,
            timestamp=datetime.utcnow()
        )
        
        if user_id:
            # 发送给特定用户
            for client_id, connection in self.connections.items():
                if connection.user_id == user_id:
                    await self.send_to_client(client_id, message)
        else:
            # 广播给所有订阅了alerts的客户端
            await self.broadcast_to_topic("alerts", message)
    
    async def send_strategy_update(self, strategy_id: str, update_data: Dict[str, Any]):
        """发送策略更新"""
        topic = f"strategy.{strategy_id}"
        
        message = WebSocketMessage(
            type=MessageType.STRATEGY_UPDATE,
            data={
                'strategy_id': strategy_id,
                'update': update_data
            },
            timestamp=datetime.utcnow()
        )
        
        await self.broadcast_to_topic(topic, message)
    
    async def send_portfolio_update(self, user_id: str, portfolio_data: Dict[str, Any]):
        """发送投资组合更新"""
        message = WebSocketMessage(
            type=MessageType.PORTFOLIO_UPDATE,
            data=portfolio_data,
            timestamp=datetime.utcnow()
        )
        
        # 发送给特定用户
        for client_id, connection in self.connections.items():
            if connection.user_id == user_id:
                await self.send_to_client(client_id, message)
    
    async def send_risk_update(self, risk_data: Dict[str, Any]):
        """发送风险更新"""
        topic = "risk"
        
        message = WebSocketMessage(
            type=MessageType.RISK_UPDATE,
            data=risk_data,
            timestamp=datetime.utcnow()
        )
        
        await self.broadcast_to_topic(topic, message)
    
    async def cleanup_stale_connections(self):
        """清理过期连接"""
        now = datetime.utcnow()
        stale_clients = []
        
        for client_id, connection in self.connections.items():
            # 检查心跳超时
            if (now - connection.last_heartbeat).total_seconds() > self.connection_timeout:
                stale_clients.append(client_id)
        
        for client_id in stale_clients:
            logger.info(f"Cleaning up stale connection: {client_id}")
            await self.disconnect(client_id)
    
    async def start_heartbeat_monitor(self):
        """启动心跳监控"""
        while self.running:
            try:
                await self.cleanup_stale_connections()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        now = datetime.utcnow()
        
        return {
            'total_connections': len(self.connections),
            'authenticated_connections': len([c for c in self.connections.values() if c.is_authenticated]),
            'subscription_stats': self.subscription_manager.get_subscription_stats(),
            'connections': [
                {
                    'client_id': client_id,
                    'connected_at': connection.connected_at.isoformat(),
                    'last_heartbeat': connection.last_heartbeat.isoformat(),
                    'is_authenticated': connection.is_authenticated,
                    'user_id': connection.user_id,
                    'subscriptions': list(connection.subscriptions),
                    'connection_duration': (now - connection.connected_at).total_seconds()
                }
                for client_id, connection in self.connections.items()
            ]
        }
    
    async def start(self):
        """启动WebSocket管理器"""
        self.running = True
        
        # 启动心跳监控
        asyncio.create_task(self.start_heartbeat_monitor())
        
        logger.info("WebSocket manager started")
    
    async def stop(self):
        """停止WebSocket管理器"""
        self.running = False
        
        # 断开所有连接
        client_ids = list(self.connections.keys())
        for client_id in client_ids:
            await self.disconnect(client_id)
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        logger.info("WebSocket manager stopped")

# 全局WebSocket管理器实例
websocket_manager: Optional[WebSocketManager] = None

def get_websocket_manager() -> WebSocketManager:
    """获取WebSocket管理器实例"""
    global websocket_manager
    if websocket_manager is None:
        websocket_manager = WebSocketManager()
    return websocket_manager