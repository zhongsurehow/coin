import React, { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Badge,
  Table,
  Tag,
  Progress,
  Typography,
  Space,
  Button,
  Tooltip,
  Alert,
  Switch,
  Select,
  notification,
} from 'antd';
import {
  ReloadOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  WifiOutlined,
  DisconnectOutlined,
  TrendingUpOutlined,
  TrendingDownOutlined,
  SwapOutlined,
  DollarOutlined,
} from '@ant-design/icons';
import { io, Socket } from 'socket.io-client';
import './RealTimeDataPanel.css';

const { Title, Text } = Typography;
const { Option } = Select;

interface MarketData {
  symbol: string;
  exchange: string;
  price: number;
  change24h: number;
  volume24h: number;
  timestamp: string;
}

interface ArbitrageOpportunity {
  id: string;
  symbol: string;
  buyExchange: string;
  sellExchange: string;
  buyPrice: number;
  sellPrice: number;
  profit: number;
  profitPercent: number;
  volume: number;
  confidence: number;
  timestamp: string;
}

interface TransactionStatus {
  id: string;
  type: 'deposit' | 'withdrawal' | 'transfer' | 'arbitrage';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  amount: number;
  currency: string;
  exchange?: string;
  progress?: number;
  timestamp: string;
}

interface ConnectionStatus {
  connected: boolean;
  latency: number;
  lastUpdate: string;
}

const RealTimeDataPanel: React.FC = () => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    connected: false,
    latency: 0,
    lastUpdate: '',
  });
  const [isAutoRefresh, setIsAutoRefresh] = useState(true);
  const [selectedExchanges, setSelectedExchanges] = useState<string[]>(['binance', 'okx', 'huobi']);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(['BTC/USDT', 'ETH/USDT', 'BNB/USDT']);
  
  // 数据状态
  const [marketData, setMarketData] = useState<MarketData[]>([]);
  const [arbitrageOpportunities, setArbitrageOpportunities] = useState<ArbitrageOpportunity[]>([]);
  const [transactionStatuses, setTransactionStatuses] = useState<TransactionStatus[]>([]);
  const [statistics, setStatistics] = useState({
    totalOpportunities: 0,
    avgProfitPercent: 0,
    activeTransactions: 0,
    successRate: 0,
  });

  // WebSocket 连接管理
  const connectWebSocket = useCallback(() => {
    const newSocket = io('ws://localhost:8000', {
      transports: ['websocket'],
      autoConnect: true,
    });

    newSocket.on('connect', () => {
      console.log('WebSocket connected');
      setConnectionStatus(prev => ({
        ...prev,
        connected: true,
        lastUpdate: new Date().toISOString(),
      }));
      
      // 订阅数据
      newSocket.emit('subscribe', {
        types: ['market_data', 'arbitrage_opportunities', 'transaction_status'],
        exchanges: selectedExchanges,
        symbols: selectedSymbols,
      });
    });

    newSocket.on('disconnect', () => {
      console.log('WebSocket disconnected');
      setConnectionStatus(prev => ({
        ...prev,
        connected: false,
      }));
    });

    newSocket.on('market_data', (data: MarketData[]) => {
      setMarketData(data);
      setConnectionStatus(prev => ({
        ...prev,
        lastUpdate: new Date().toISOString(),
      }));
    });

    newSocket.on('arbitrage_opportunities', (data: ArbitrageOpportunity[]) => {
      setArbitrageOpportunities(data);
      
      // 计算统计数据
      const totalOpportunities = data.length;
      const avgProfitPercent = data.length > 0 
        ? data.reduce((sum, opp) => sum + opp.profitPercent, 0) / data.length 
        : 0;
      
      setStatistics(prev => ({
        ...prev,
        totalOpportunities,
        avgProfitPercent,
      }));
      
      // 高利润机会通知
      const highProfitOpps = data.filter(opp => opp.profitPercent > 2);
      if (highProfitOpps.length > 0) {
        notification.success({
          message: '发现高利润套利机会',
          description: `${highProfitOpps.length} 个机会，最高利润 ${Math.max(...highProfitOpps.map(o => o.profitPercent)).toFixed(2)}%`,
          duration: 3,
        });
      }
    });

    newSocket.on('transaction_status', (data: TransactionStatus[]) => {
      setTransactionStatuses(data);
      
      const activeTransactions = data.filter(t => ['pending', 'processing'].includes(t.status)).length;
      const completedTransactions = data.filter(t => t.status === 'completed').length;
      const totalTransactions = data.length;
      const successRate = totalTransactions > 0 ? (completedTransactions / totalTransactions) * 100 : 0;
      
      setStatistics(prev => ({
        ...prev,
        activeTransactions,
        successRate,
      }));
    });

    newSocket.on('pong', (timestamp: number) => {
      const latency = Date.now() - timestamp;
      setConnectionStatus(prev => ({
        ...prev,
        latency,
      }));
    });

    setSocket(newSocket);

    return newSocket;
  }, [selectedExchanges, selectedSymbols]);

  const disconnectWebSocket = useCallback(() => {
    if (socket) {
      socket.disconnect();
      setSocket(null);
    }
  }, [socket]);

  const pingServer = useCallback(() => {
    if (socket && socket.connected) {
      socket.emit('ping', Date.now());
    }
  }, [socket]);

  useEffect(() => {
    if (isAutoRefresh) {
      connectWebSocket();
    } else {
      disconnectWebSocket();
    }

    return () => {
      disconnectWebSocket();
    };
  }, [isAutoRefresh, connectWebSocket, disconnectWebSocket]);

  // 定期ping服务器测试延迟
  useEffect(() => {
    const interval = setInterval(() => {
      pingServer();
    }, 5000);

    return () => clearInterval(interval);
  }, [pingServer]);

  // 表格列定义
  const marketDataColumns = [
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Text strong>{symbol}</Text>,
    },
    {
      title: '交易所',
      dataIndex: 'exchange',
      key: 'exchange',
      render: (exchange: string) => <Tag color="blue">{exchange.toUpperCase()}</Tag>,
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => <Text>${price.toFixed(4)}</Text>,
    },
    {
      title: '24h变化',
      dataIndex: 'change24h',
      key: 'change24h',
      render: (change: number) => (
        <Text type={change >= 0 ? 'success' : 'danger'}>
          {change >= 0 ? <TrendingUpOutlined /> : <TrendingDownOutlined />}
          {change.toFixed(2)}%
        </Text>
      ),
    },
    {
      title: '24h成交量',
      dataIndex: 'volume24h',
      key: 'volume24h',
      render: (volume: number) => <Text>{(volume / 1000000).toFixed(2)}M</Text>,
    },
  ];

  const arbitrageColumns = [
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Text strong>{symbol}</Text>,
    },
    {
      title: '买入',
      key: 'buy',
      render: (record: ArbitrageOpportunity) => (
        <Space direction="vertical" size="small">
          <Tag color="green">{record.buyExchange.toUpperCase()}</Tag>
          <Text>${record.buyPrice.toFixed(4)}</Text>
        </Space>
      ),
    },
    {
      title: '卖出',
      key: 'sell',
      render: (record: ArbitrageOpportunity) => (
        <Space direction="vertical" size="small">
          <Tag color="red">{record.sellExchange.toUpperCase()}</Tag>
          <Text>${record.sellPrice.toFixed(4)}</Text>
        </Space>
      ),
    },
    {
      title: '利润',
      key: 'profit',
      render: (record: ArbitrageOpportunity) => (
        <Space direction="vertical" size="small">
          <Text type="success">${record.profit.toFixed(2)}</Text>
          <Text type="success">{record.profitPercent.toFixed(2)}%</Text>
        </Space>
      ),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      render: (confidence: number) => (
        <Progress 
          percent={confidence * 100} 
          size="small" 
          status={confidence > 0.8 ? 'success' : confidence > 0.6 ? 'normal' : 'exception'}
        />
      ),
    },
  ];

  const transactionColumns = [
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => {
        const colors = {
          deposit: 'green',
          withdrawal: 'red',
          transfer: 'blue',
          arbitrage: 'purple',
        };
        return <Tag color={colors[type as keyof typeof colors]}>{type.toUpperCase()}</Tag>;
      },
    },
    {
      title: '金额',
      key: 'amount',
      render: (record: TransactionStatus) => (
        <Text>{record.amount} {record.currency}</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string, record: TransactionStatus) => {
        const colors = {
          pending: 'orange',
          processing: 'blue',
          completed: 'green',
          failed: 'red',
        };
        return (
          <Space>
            <Badge color={colors[status as keyof typeof colors]} />
            <Text>{status.toUpperCase()}</Text>
            {record.progress && (
              <Progress percent={record.progress} size="small" style={{ width: 60 }} />
            )}
          </Space>
        );
      },
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (timestamp: string) => (
        <Text>{new Date(timestamp).toLocaleTimeString()}</Text>
      ),
    },
  ];

  return (
    <div className="real-time-data-panel">
      {/* 控制面板 */}
      <Card className="control-panel" size="small">
        <Row gutter={16} align="middle">
          <Col>
            <Space>
              <Switch
                checked={isAutoRefresh}
                onChange={setIsAutoRefresh}
                checkedChildren={<PlayCircleOutlined />}
                unCheckedChildren={<PauseCircleOutlined />}
              />
              <Text>实时更新</Text>
            </Space>
          </Col>
          <Col>
            <Space>
              {connectionStatus.connected ? (
                <Badge status="success" text={<WifiOutlined />} />
              ) : (
                <Badge status="error" text={<DisconnectOutlined />} />
              )}
              <Text>延迟: {connectionStatus.latency}ms</Text>
            </Space>
          </Col>
          <Col>
            <Select
              mode="multiple"
              placeholder="选择交易所"
              value={selectedExchanges}
              onChange={setSelectedExchanges}
              style={{ width: 200 }}
            >
              <Option value="binance">Binance</Option>
              <Option value="okx">OKX</Option>
              <Option value="huobi">Huobi</Option>
              <Option value="coinbase">Coinbase</Option>
            </Select>
          </Col>
          <Col>
            <Select
              mode="multiple"
              placeholder="选择交易对"
              value={selectedSymbols}
              onChange={setSelectedSymbols}
              style={{ width: 200 }}
            >
              <Option value="BTC/USDT">BTC/USDT</Option>
              <Option value="ETH/USDT">ETH/USDT</Option>
              <Option value="BNB/USDT">BNB/USDT</Option>
              <Option value="ADA/USDT">ADA/USDT</Option>
            </Select>
          </Col>
          <Col>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                disconnectWebSocket();
                setTimeout(connectWebSocket, 1000);
              }}
            >
              重连
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="套利机会"
              value={statistics.totalOpportunities}
              prefix={<SwapOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均利润率"
              value={statistics.avgProfitPercent}
              precision={2}
              suffix="%"
              prefix={<TrendingUpOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="活跃交易"
              value={statistics.activeTransactions}
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="成功率"
              value={statistics.successRate}
              precision={1}
              suffix="%"
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 数据表格 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="实时市场数据" size="small">
            <Table
              columns={marketDataColumns}
              dataSource={marketData}
              rowKey={(record) => `${record.exchange}-${record.symbol}`}
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="套利机会" size="small">
            <Table
              columns={arbitrageColumns}
              dataSource={arbitrageOpportunities}
              rowKey="id"
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="交易状态" size="small">
            <Table
              columns={transactionColumns}
              dataSource={transactionStatuses}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              size="small"
            />
          </Card>
        </Col>
      </Row>

      {/* 连接状态提示 */}
      {!connectionStatus.connected && (
        <Alert
          message="WebSocket连接已断开"
          description="实时数据更新已暂停，请检查网络连接或点击重连按钮"
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );
};

export default RealTimeDataPanel;